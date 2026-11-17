"""Regras de alerta e montagem das mensagens do Telegram."""
from __future__ import annotations

from datetime import date

from .mercado import indice_por_ticker
from .telegram import esc, link
from .util import agora, fmt_num, fmt_pct, fmt_reais, hoje_str

ORDEM_CHANCE = {"baixa": 0, "media": 1, "alta": 2}
ICONE_DIRECAO = {"alta": "📈", "queda": "📉", "incerto": "❔"}
NOME_CHANCE = {"baixa": "baixa", "media": "média", "alta": "alta"}
NOME_PRAZO = {"dias": "próximos dias", "semanas": "próximas semanas", "meses": "próximos meses"}
NOME_NO_PRECO = {"sim": "o preço provavelmente já reagiu", "talvez": "o preço pode já ter reagido em parte",
                 "nao": "o preço ainda não parece ter reagido", "nao_sei": ""}
RODAPE = "<i>Dados públicos com atraso de até 30 min. Possibilidades, não certezas. Não é recomendação de investimento.</i>"


class Controle:
    """Lembra o que já foi enviado para não repetir o mesmo alerta."""

    def __init__(self, estado: dict):
        self.estado = estado
        self.enviados: dict[str, str] = estado.setdefault("enviados", {})

    def ja_enviado(self, chave: str, dias: int = 0) -> bool:
        quando = self.enviados.get(chave)
        if not quando:
            return False
        return (date.fromisoformat(hoje_str()) - date.fromisoformat(quando)).days <= dias

    def marcar(self, chave: str) -> None:
        self.enviados[chave] = hoje_str()

    def limpar_antigos(self, dias: int = 15) -> None:
        hoje = date.fromisoformat(hoje_str())
        for k in [k for k, v in self.enviados.items() if (hoje - date.fromisoformat(v)).days > dias]:
            del self.enviados[k]


def _nome(a: dict) -> str:
    return f'<b>{esc(a["ticker"])}</b> ({esc(a.get("nome", ""))})'


def alertas_de_mercado(mercado: dict, config: dict, ctrl: Controle) -> list[str]:
    cfg = config.get("alertas", {})
    idx = indice_por_ticker(mercado)
    hoje = hoje_str()
    lista_cfg = {i["ticker"].upper(): i for i in config.get("minha_lista", [])}
    da_lista, mercado_msgs = [], []

    # 1) Sua lista: variação forte no dia (avisa de novo se piorar/melhorar mais um degrau)
    limite = float(cfg.get("variacao_dia_minha_lista", 3) or 0)
    for tk, conf in lista_cfg.items():
        a = idx.get(tk)
        if not a or a.get("var_dia") is None:
            continue
        v = a["var_dia"]
        if limite and abs(v) >= limite:
            degrau = int(abs(v) // limite)
            chave = f"lista:{tk}:{hoje}:{'+' if v > 0 else '-'}{degrau}"
            if not ctrl.ja_enviado(chave):
                ctrl.marcar(chave)
                icone = "🟢" if v > 0 else "🔴"
                verbo = "sobe" if v > 0 else "cai"
                da_lista.append(f"{icone} {_nome(a)} {verbo} <b>{fmt_pct(v)}</b> hoje, a {fmt_reais(a['preco'])}.")
        # Preço-alvo definido por você
        for campo, cond, texto in (("avisar_abaixo", lambda p, x: p <= x, "ficou abaixo de"),
                                   ("avisar_acima", lambda p, x: p >= x, "passou de")):
            alvo = conf.get(campo)
            if alvo and a.get("preco") and cond(a["preco"], float(alvo)):
                chave = f"alvo:{tk}:{campo}:{alvo}:{hoje}"
                if not ctrl.ja_enviado(chave):
                    ctrl.marcar(chave)
                    da_lista.append(f"🎯 {_nome(a)} {texto} {fmt_reais(float(alvo))}: está a {fmt_reais(a['preco'])}.")

    # 2) Mercado: altas/quedas muito fortes no dia
    limite_m = float(cfg.get("variacao_dia_mercado", 0) or 0)
    if limite_m:
        fortes = [a for c in ("acoes", "fiis") for a in mercado.get(c, [])
                  if a.get("var_dia") is not None and abs(a["var_dia"]) >= limite_m and a["ticker"] not in lista_cfg]
        for a in sorted(fortes, key=lambda x: -abs(x["var_dia"])):
            chave = f"forte:{a['ticker']}:{hoje}"
            if ctrl.ja_enviado(chave):
                continue
            ctrl.marcar(chave)
            icone = "🚀" if a["var_dia"] > 0 else "⚠️"
            mercado_msgs.append(f"{icone} {_nome(a)} {fmt_pct(a['var_dia'])} hoje, a {fmt_reais(a['preco'])}.")

    maximo = int(cfg.get("maximo_por_mensagem", 12))
    if len(mercado_msgs) > maximo:
        resto = len(mercado_msgs) - maximo
        mercado_msgs = mercado_msgs[:maximo] + [f"… e mais {resto} no app."]
    blocos = []
    if da_lista:
        blocos.append("⭐ <b>Sua lista</b>\n" + "\n".join(da_lista))
    if mercado_msgs:
        blocos.append("🔎 <b>Mercado</b>\n" + "\n".join(mercado_msgs))
    return blocos


def alertas_de_filtros(mercado: dict, config: dict, ctrl: Controle, por_filtro: int = 5) -> list[str]:
    """Filtros de 'oportunidade a estudar'. Roda uma vez por dia (no resumo).

    Cada ativo só é avisado de novo depois de 7 dias. No máximo `por_filtro` por dia;
    o resto aparece no app.
    """
    cfg = config.get("alertas", {})
    blocos = []

    c = cfg.get("caiu_mas_solida", {})
    if c.get("ligado"):
        achados = [a for a in mercado.get("acoes", [])
                   if a.get("var_30d") is not None and a["var_30d"] <= float(c.get("queda_30_dias", -12))
                   and (a.get("nota") or 0) >= float(c.get("nota_minima", 7))]
        novos = [a for a in sorted(achados, key=lambda a: (-(a["nota"] or 0), a["var_30d"]))
                 if not ctrl.ja_enviado(f"solida:{a['ticker']}", dias=7)][:por_filtro]
        linhas = []
        for a in novos:
            ctrl.marcar(f"solida:{a['ticker']}")
            cuidado = [t for t in a.get("avisos", []) if "mínima" not in t and "máxima" not in t]
            linhas.append(f"• {_nome(a)} caiu {fmt_pct(a['var_30d'])} em 30 dias; nota <b>{fmt_num(a['nota'], 1)}</b>, "
                          f"P/L {fmt_num(a.get('pl'), 1)}, dividendos {fmt_pct(a.get('dy'), sinal=False)}."
                          + (f" ⚠️ {esc(cuidado[0])}." if cuidado else ""))
        if linhas:
            blocos.append(f"💡 <b>Caíram, mas os números são bons</b> ({len(achados)} no filtro)\n" + "\n".join(linhas)
                          + "\n<i>Vale estudar o motivo da queda: pode ser exagero do mercado ou um problema real que ainda não aparece no balanço.</i>")

    f = cfg.get("fii_com_desconto", {})
    if f.get("ligado"):
        achados = [a for a in mercado.get("fiis", [])
                   if a.get("pvp") and a["pvp"] <= float(f.get("pvp_maximo", 0.92))
                   and (a.get("dy") or 0) >= float(f.get("dy_minimo", 9))
                   and (a.get("nota") or 0) >= float(f.get("nota_minima", 7))]
        novos = [a for a in sorted(achados, key=lambda a: (-(a["nota"] or 0), a["pvp"]))
                 if not ctrl.ja_enviado(f"fii:{a['ticker']}", dias=7)][:por_filtro]
        linhas = []
        for a in novos:
            ctrl.marcar(f"fii:{a['ticker']}")
            linhas.append(f"• {_nome(a)} P/VP {fmt_num(a['pvp'])}, rendimento {fmt_pct(a['dy'], sinal=False)} ao ano, "
                          f"nota <b>{fmt_num(a['nota'], 1)}</b>.")
        if linhas:
            blocos.append(f"🏢 <b>FIIs com desconto</b> ({len(achados)} no filtro)\n" + "\n".join(linhas)
                          + "\n<i>Desconto pode ser oportunidade ou sinal de risco (vacância, inadimplência).</i>")
    return blocos


def texto_possibilidade(p: dict) -> str:
    alvo = f'<b>{esc(p["ativo"])}</b> ({esc(p["nome"])})' if p.get("ativo") else f'<b>{esc(p["nome"])}</b>'
    cab = (f'{ICONE_DIRECAO.get(p["direcao"], "")} {alvo}: possível <b>{esc(p["direcao"])}</b> · '
           f'chance {NOME_CHANCE.get(p["chance"], p["chance"])} · {NOME_PRAZO.get(p["prazo"], p["prazo"])}')
    linhas = [cab, f'<b>{esc(p["titulo"])}</b>', esc(p["explicacao"]), f'⚖️ <i>Contraponto:</i> {esc(p["contraponto"])}']
    if p.get("o_que_observar"):
        linhas.append(f'👀 {esc(p["o_que_observar"])}')
    no_preco = NOME_NO_PRECO.get(p.get("ja_no_preco"), "")
    mk = p.get("mercado")
    if mk:
        extra = f'Hoje {fmt_pct(mk.get("var_dia"))}, 30 dias {fmt_pct(mk.get("var_30d"))}'
        linhas.append(f'📊 {extra}' + (f'; {no_preco}.' if no_preco else "."))
    elif no_preco:
        linhas.append(f'📊 {no_preco.capitalize()}.')
    fontes = " · ".join(link(f["fonte"], f.get("link")) for f in p.get("fontes", []))
    if fontes:
        linhas.append(f"📰 {fontes}")
    return "\n".join(linhas)


def alertas_de_ia(analise: dict | None, config: dict, ctrl: Controle) -> list[str]:
    if not analise:
        return []
    cfg = config.get("alertas", {})
    min_lista = ORDEM_CHANCE.get(cfg.get("ia_chance_minima_minha_lista", "media"), 1)
    min_mercado = ORDEM_CHANCE.get(cfg.get("ia_chance_minima_mercado", "alta"), 2)
    hoje = hoje_str()
    blocos = []
    for p in analise.get("possibilidades", []):
        chance = ORDEM_CHANCE.get(p.get("chance"), 0)
        exigido = min_lista if p.get("na_minha_lista") else min_mercado
        if chance < exigido:
            continue
        ident = p.get("ativo") or p.get("titulo", "")[:40]
        chave = f"ia:{ident}:{p.get('direcao')}:{hoje}"
        if ctrl.ja_enviado(chave):
            continue
        ctrl.marcar(chave)
        blocos.append(texto_possibilidade(p))
    if blocos:
        blocos.insert(0, "🧠 <b>Possibilidades a partir das notícias</b>")
    return blocos


def montar_mensagem(blocos: list[str], titulo: str, site_url: str | None) -> str | None:
    if not blocos:
        return None
    partes = [f"📡 <b>{esc(titulo)}</b> · {agora().strftime('%d/%m %H:%M')}"] + blocos
    if site_url:
        partes.append(link("Abrir o Radar", site_url))
    partes.append(RODAPE)
    return "\n\n".join(partes)


def resumo_do_dia(mercado: dict, analise: dict | None, site_url: str | None) -> str:
    m = mercado.get("macro", {})
    idx = indice_por_ticker(mercado)
    linhas = []
    ind = []
    if m.get("ibov"):
        pontos = f'{m["ibov"]["valor"]:,.0f}'.replace(",", ".")
        ind.append(f'Ibovespa <b>{pontos}</b> ({fmt_pct(m["ibov"].get("var_dia"))})')
    if m.get("dolar"):
        ind.append(f'Dólar <b>{fmt_reais(m["dolar"]["valor"])}</b> ({fmt_pct(m["dolar"].get("var_dia"))})')
    if m.get("selic") is not None:
        ind.append(f'Selic {str(m["selic"]).replace(".", ",")}%')
    if ind:
        linhas.append(" · ".join(ind))

    lista = [idx[t] for t in mercado.get("minha_lista", []) if t in idx]
    if lista:
        itens = [f'{"🟢" if (a.get("var_dia") or 0) >= 0 else "🔴"} {esc(a["ticker"])} {fmt_pct(a.get("var_dia"))}'
                 for a in sorted(lista, key=lambda a: -(a.get("var_dia") or 0))]
        linhas.append("⭐ <b>Sua lista</b>\n" + "\n".join(itens))

    acoes = [a for a in mercado.get("acoes", []) if a.get("var_dia") is not None]
    if acoes:
        altas = sorted(acoes, key=lambda a: -a["var_dia"])[:5]
        quedas = sorted(acoes, key=lambda a: a["var_dia"])[:5]
        linhas.append("📈 <b>Maiores altas</b>\n" + "\n".join(f'{esc(a["ticker"])} {fmt_pct(a["var_dia"])} · {esc(a["nome"])}' for a in altas))
        linhas.append("📉 <b>Maiores quedas</b>\n" + "\n".join(f'{esc(a["ticker"])} {fmt_pct(a["var_dia"])} · {esc(a["nome"])}' for a in quedas))

    if analise and analise.get("resumo"):
        linhas.append(f'🧠 <b>Panorama</b>\n{esc(analise["resumo"])}')
        principais = analise.get("possibilidades", [])[:3]
        if principais:
            linhas.append("<b>Possibilidades em destaque</b>\n" + "\n".join(
                f'{ICONE_DIRECAO.get(p["direcao"], "")} {esc(p.get("ativo") or p["nome"])}: {esc(p["titulo"])} '
                f'(chance {NOME_CHANCE.get(p["chance"], p["chance"])})' for p in principais))
        if analise.get("agenda"):
            linhas.append("🗓️ <b>Agenda</b>\n" + "\n".join(f'{esc(e["quando"])}: {esc(e["evento"])}' for e in analise["agenda"][:5]))
    return montar_mensagem(linhas, "Resumo do dia", site_url)
