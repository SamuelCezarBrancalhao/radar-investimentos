"""Análise das notícias com IA (Claude, da Anthropic).

A IA lê SOMENTE as notícias coletadas pelo robô (sites confiáveis) e devolve
"possibilidades": o que pode subir ou cair, com que chance, por quê, o que pode
dar errado e quais notícias sustentam isso (com link).
"""
from __future__ import annotations

import json
import os

import anthropic

from .mercado import indice_por_ticker
from .util import agora, fmt_pct, log

MODELOS_COM_FALLBACK = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-opus-5"}
PRECO_POR_MILHAO = {  # US$ (entrada, saída), só para mostrar o custo estimado no log
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

SISTEMA = """\
Você é o analista de notícias de um aplicativo pessoal que acompanha a bolsa brasileira (B3).
Quem lê é um investidor iniciante e muito curioso, que quer entender o que as notícias podem \
causar nos preços de ações, fundos imobiliários (FIIs) e ETFs. Ele sabe que ninguém prevê o \
mercado com certeza e quer ver possibilidades, explicadas com honestidade.

Como trabalhar:
- Use somente as notícias fornecidas na mensagem. Não invente fatos, números ou eventos. Cada \
possibilidade precisa citar os números [id] das notícias que a sustentam.
- Uma possibilidade descreve um efeito plausível no preço (alta ou queda) de um ativo, setor ou do \
mercado como um todo, com uma chance qualitativa:
  - "alta": vários fatos concretos apontam na mesma direção e o efeito é direto (ex.: empresa \
anunciou resultado muito acima do esperado, corte de dividendos confirmado, rebaixamento de rating).
  - "media": há um fato concreto, mas o efeito depende de outras coisas ou ainda não está claro.
  - "baixa": boato, opinião de colunista, efeito indireto ou notícia ambígua.
  Seja calibrado. A maioria das notícias não muda nada e é melhor trazer poucas possibilidades \
boas do que muitas fracas. Ele pode tomar decisões com dinheiro real a partir disto, então \
excesso de confiança custa caro.
- Veja os dados de mercado fornecidos. Se o preço já caiu ou subiu muito, o mercado provavelmente \
já reagiu à notícia; diga isso em "ja_no_preco".
- Sempre escreva um contraponto real: o que poderia fazer a possibilidade não acontecer.
- Não diga "compre" nem "venda" e não dê recomendação. Explique a possibilidade e o que observar \
daqui pra frente; a decisão é dele.
- Use os códigos de negociação da B3 (ex.: PETR4, BBAS3, HGLG11). Se a notícia é sobre um setor \
inteiro ou sobre a economia, use categoria "setor" ou "macro", deixe "ativo" vazio e diga em \
"titulo" quais ativos costumam ser afetados.
- Linguagem simples, como quem explica para um amigo. Explique termos técnicos rapidamente \
quando aparecerem.
- No máximo 12 possibilidades, ordenadas da mais relevante para a menos relevante, priorizando \
os ativos da lista do usuário quando houver notícia relevante sobre eles.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "resumo": {
            "type": "string",
            "description": "Panorama do momento em 4 a 6 frases simples: o que está movendo o mercado.",
        },
        "humor_mercado": {"type": "string", "enum": ["otimista", "neutro", "pessimista", "incerto"]},
        "possibilidades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ativo": {"type": "string", "description": "Código B3, ou vazio para setor/macro"},
                    "nome": {"type": "string", "description": "Nome da empresa, fundo, setor ou tema"},
                    "categoria": {"type": "string", "enum": ["acao", "fii", "etf", "bdr", "setor", "macro"]},
                    "direcao": {"type": "string", "enum": ["alta", "queda", "incerto"]},
                    "chance": {"type": "string", "enum": ["baixa", "media", "alta"]},
                    "prazo": {"type": "string", "enum": ["dias", "semanas", "meses"]},
                    "titulo": {"type": "string", "description": "Frase curta, até 90 caracteres"},
                    "explicacao": {"type": "string", "description": "2 a 4 frases: o que aconteceu e por que pode mexer no preço"},
                    "contraponto": {"type": "string", "description": "1 a 2 frases: o que pode fazer isso não acontecer"},
                    "o_que_observar": {"type": "string", "description": "1 frase: o próximo sinal a acompanhar"},
                    "ja_no_preco": {"type": "string", "enum": ["sim", "talvez", "nao", "nao_sei"]},
                    "noticias": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["ativo", "nome", "categoria", "direcao", "chance", "prazo", "titulo",
                             "explicacao", "contraponto", "o_que_observar", "ja_no_preco", "noticias"],
                "additionalProperties": False,
            },
        },
        "agenda": {
            "type": "array",
            "description": "Eventos futuros citados nas notícias (Copom, balanços, dividendos, votações).",
            "items": {
                "type": "object",
                "properties": {
                    "quando": {"type": "string"},
                    "evento": {"type": "string"},
                },
                "required": ["quando", "evento"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["resumo", "humor_mercado", "possibilidades", "agenda"],
    "additionalProperties": False,
}


def _linha_ativo(a: dict) -> str:
    partes = [f'{a["ticker"]} ({a.get("nome", "")})', f'R$ {a.get("preco")}',
              f'dia {fmt_pct(a.get("var_dia"))}', f'30d {fmt_pct(a.get("var_30d"))}',
              f'12m {fmt_pct(a.get("var_12m"))}']
    if a.get("nota") is not None:
        partes.append(f'nota fundamentos {a["nota"]}/10')
    return " | ".join(partes)


def _montar_mensagem(noticias: list[dict], mercado: dict) -> str:
    idx = indice_por_ticker(mercado)
    m = mercado.get("macro", {})
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    agora_txt = f"{dias[agora().weekday()]}, {agora().strftime('%d/%m/%Y %H:%M')}"
    linhas = [f"Agora: {agora_txt} (horário de Brasília)", "", "## Indicadores"]
    if m.get("ibov"):
        linhas.append(f'Ibovespa: {m["ibov"]["valor"]:.0f} pontos ({fmt_pct(m["ibov"].get("var_dia"))} no dia)')
    if m.get("dolar"):
        linhas.append(f'Dólar: R$ {m["dolar"]["valor"]:.2f} ({fmt_pct(m["dolar"].get("var_dia"))})')
    if m.get("selic") is not None:
        linhas.append(f'Selic: {m["selic"]}% ao ano | IPCA 12 meses: {m.get("ipca_12m")}%')

    linhas += ["", "## Lista do usuário"]
    for tk in mercado.get("minha_lista", []):
        if tk in idx:
            linhas.append(_linha_ativo(idx[tk]))

    acoes_fiis = mercado.get("acoes", []) + mercado.get("fiis", [])
    com_var = [a for a in acoes_fiis if a.get("var_dia") is not None]
    linhas += ["", "## Maiores altas do dia (ações e FIIs líquidos)"]
    linhas += [_linha_ativo(a) for a in sorted(com_var, key=lambda a: -a["var_dia"])[:8]]
    linhas += ["", "## Maiores quedas do dia"]
    linhas += [_linha_ativo(a) for a in sorted(com_var, key=lambda a: a["var_dia"])[:8]]

    linhas += ["", "## Ativos acompanhados (código e nome, para você identificar empresas citadas)"]
    nomes = [f'{a["ticker"]} {a.get("nome", "")}' for c in ("acoes", "fiis", "etfs") for a in mercado.get(c, [])]
    linhas.append("; ".join(nomes))

    linhas += ["", "## Notícias (use os números [id] para citar)"]
    for n in noticias:
        quando = (n.get("quando") or "")[:16].replace("T", " ")
        sobre = f' [busca: {n["sobre"]}]' if n.get("sobre") else ""
        resumo = f' | {n["resumo"]}' if n.get("resumo") else ""
        linhas.append(f'[{n["id"]}] ({n["fonte"]}, {quando}){sobre} {n["titulo"]}{resumo}')

    linhas += ["", "Analise as notícias e devolva o panorama, as possibilidades e a agenda."]
    return "\n".join(linhas)


def _chamar_claude(modelo: str, mensagem: str):
    client = anthropic.Anthropic(max_retries=3)
    kwargs = {
        "model": modelo,
        "max_tokens": 16000,
        "system": SISTEMA,
        "messages": [{"role": "user", "content": mensagem}],
        "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
    }
    if modelo in MODELOS_COM_FALLBACK:
        # Se o modelo recusar por engano, a própria API tenta de novo com outro modelo.
        try:
            return client.beta.messages.create(
                **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        except anthropic.BadRequestError as e:
            log.warning("Pedido com fallback recusado (%s); tentando sem fallback", e.message)
    return client.beta.messages.create(**kwargs)


def analisar(noticias: list[dict], mercado: dict, config: dict) -> dict | None:
    cfg = config.get("ia", {})
    if not cfg.get("ligada", True):
        log.info("IA desligada no config.yaml")
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.info("Sem ANTHROPIC_API_KEY: pulando a análise com IA")
        return None
    if not noticias:
        log.info("Nenhuma notícia para analisar")
        return None

    modelo = cfg.get("modelo", "claude-opus-5-5")
    mensagem = _montar_mensagem(noticias, mercado)
    try:
        resp = _chamar_claude(modelo, mensagem)
    except anthropic.AuthenticationError:
        log.error("Chave da Anthropic inválida (confira o segredo ANTHROPIC_API_KEY)")
        return None
    except anthropic.PermissionDeniedError as e:
        log.error("Sem permissão na Anthropic (créditos acabaram?): %s", e.message)
        return None
    except anthropic.RateLimitError:
        log.error("Limite de uso da Anthropic atingido; tento de novo na próxima rodada")
        return None
    except anthropic.APIStatusError as e:
        log.error("Erro da Anthropic (%s): %s", e.status_code, e.message)
        return None
    except anthropic.APIConnectionError:
        log.error("Sem conexão com a Anthropic")
        return None

    if resp.stop_reason == "refusal":
        log.error("A IA recusou esta análise; tento de novo na próxima rodada")
        return None
    if resp.stop_reason == "max_tokens":
        log.error("Resposta da IA ficou longa demais e foi cortada")
        return None
    texto = next((b.text for b in resp.content if b.type == "text"), None)
    if not texto:
        log.error("A IA não devolveu texto")
        return None
    dados = json.loads(texto)

    u = resp.usage
    ent, sai = PRECO_POR_MILHAO.get(resp.model, (0, 0))
    custo = (u.input_tokens * ent + u.output_tokens * sai) / 1e6
    log.info("IA (%s): %d tokens de entrada, %d de saída, custo ~US$ %.3f",
             resp.model, u.input_tokens, u.output_tokens, custo)
    return _validar(dados, noticias, mercado, resp.model)


def _validar(dados: dict, noticias: list[dict], mercado: dict, modelo: str) -> dict:
    """Garante que toda possibilidade aponta para notícias reais e ativos que existem."""
    por_id = {n["id"]: n for n in noticias}
    idx = indice_por_ticker(mercado)
    lista = set(mercado.get("minha_lista", []))
    validas = []
    for p in dados.get("possibilidades", []):
        fontes = [por_id[i] for i in p.get("noticias", []) if i in por_id]
        if not fontes:
            continue  # sem notícia real por trás → descarta
        tk = (p.get("ativo") or "").upper().strip()
        if tk and tk not in idx:
            # código desconhecido: vira um sinal de tema, sem ticker
            p["nome"] = f'{p.get("nome") or tk} ({tk})'
            tk = ""
            if p.get("categoria") in ("acao", "fii", "etf", "bdr"):
                p["categoria"] = "setor"
        p["ativo"] = tk
        p["fontes"] = [{"fonte": f["fonte"], "titulo": f["titulo"], "link": f["link"],
                        "quando": f.get("quando")} for f in fontes[:4]]
        p.pop("noticias", None)
        if tk:
            a = idx[tk]
            p["mercado"] = {k: a.get(k) for k in ("preco", "var_dia", "var_30d", "var_12m", "nota")}
            p["na_minha_lista"] = tk in lista
        validas.append(p)
    return {
        "gerado": agora().isoformat(timespec="minutes"),
        "modelo": modelo,
        "resumo": dados.get("resumo", ""),
        "humor_mercado": dados.get("humor_mercado"),
        "possibilidades": validas,
        "agenda": dados.get("agenda", [])[:10],
    }
