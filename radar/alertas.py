"""Regras de alerta e montagem das mensagens do Telegram.

As mensagens são feitas para ler "batendo o olho": no máximo 2 linhas curtas por
ativo, um número por ideia, sem siglas. Os detalhes (P/L, dividendos etc.) ficam no app.
"""
from __future__ import annotations

import re
from datetime import date

from .mercado import indice_por_ticker
from .telegram import esc, link
from .util import agora, fmt_reais, hoje_str

ORDEM_CHANCE = {"baixa": 0, "media": 1, "alta": 2}
NOME_CHANCE = {"baixa": "baixa", "media": "média", "alta": "alta"}
NOME_PRAZO = {"dias": "nos próximos dias", "semanas": "nas próximas semanas", "meses": "nos próximos meses"}
RODAPE = "<i>Não é recomendação de investimento.</i>"

# Avisos longos do app → versão curta para o celular
AVISO_CURTO = {
    "Dividendos muito altos": "dividendo alto demais, pode não se repetir",
    "P/L muito baixo": "lucro pode ter sido pontual",
    "Teve prejuízo": "teve prejuízo",
    "Dívida alta": "dívida alta",
    "Rendimento muito alto": "rendimento alto demais, pode não se repetir",
    "Vacância alta": "muitos imóveis vazios",
    "Desconto muito grande": "desconto grande demais, pode ter risco",
    "Poucos imóveis": "poucos imóveis",
}


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


# ---------------------------------------------------------------------------
# Textos simples
# ---------------------------------------------------------------------------

_SOBRA = re.compile(
    r"\b(Participa[cç][oõ]es|Holding|Cia\.?|Companhia|Empreendimentos?|Imobili[aá]rios?|Desenvolvimento|"
    r"Engenharia|Brazil Realty|Fundo de Investimento|Consultoria e Corretora de Seguros|Ltda\.?)\b",
    re.IGNORECASE)
_CONECTORES = {"de", "do", "da", "dos", "das", "e", "&"}


def nome_curto(nome: str | None, ticker: str) -> str:
    """'Cia Paranaense de Energia - Copel' → 'Copel'; 'Construtora Tenda S.A.' → 'Construtora Tenda'."""
    if not nome or nome == ticker:
        return ticker
    partes = [p.strip() for p in nome.split(" - ") if p.strip()]
    n = min(partes, key=len) if len(partes) > 1 else partes[0]
    antes, *depois = re.split(r"\s+S[./]?A\b\.?", n, maxsplit=1, flags=re.IGNORECASE)
    resto = depois[0].strip(" .") if depois else ""
    n = resto if (resto.isalpha() and len(resto) >= 4) else antes  # "Petroleo Brasileiro S.A. Petrobras"
    n = re.sub(r"\s+", " ", _SOBRA.sub("", n)).strip(" .-&,")
    saida = []
    for p in n.split():
        if len(" ".join(saida + [p])) > 22:
            break
        saida.append(p)
    while saida and saida[-1].lower() in _CONECTORES:
        saida.pop()
    return " ".join(saida) or ticker


def _cab(a: dict) -> str:
    return f'<b>{esc(a["ticker"])}</b> · {esc(nome_curto(a.get("nome"), a["ticker"]))}'


def _pct(v: float | None) -> str:
    """Percentual sem sinal e curto: 38% ou 4,4%."""
    if v is None:
        return "–"
    v = round(abs(v), 1)
    texto = f"{v:.0f}" if v >= 10 else f"{v:.1f}".replace(".", ",").removesuffix(",0")
    return texto + "%"


def _pct_sinal(v: float | None) -> str:
    if v is None:
        return "–"
    return ("+" if v > 0 else "−" if v < 0 else "") + _pct(v)


def _nota(n: float) -> str:
    """9.5 → '9,5'; 10.0 → '10'."""
    return f"{n:.1f}".replace(".", ",").removesuffix(",0")


def _bola(v: float | None) -> str:
    return "🟢" if (v or 0) > 0.05 else "🔴" if (v or 0) < -0.05 else "⚪"


def _aviso(a: dict) -> str | None:
    for t in a.get("avisos", []):
        for inicio, curto in AVISO_CURTO.items():
            if t.startswith(inicio):
                return curto
    return None


# ---------------------------------------------------------------------------
# Alertas do pregão
# ---------------------------------------------------------------------------

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
                verbo = "subiu" if v > 0 else "caiu"
                da_lista.append(f"{_bola(v)} <b>{esc(tk)}</b> {verbo} {_pct(v)} hoje")
        # Preço-alvo definido por você
        for campo, cond, texto in (("avisar_abaixo", lambda p, x: p <= x, "abaixo de"),
                                   ("avisar_acima", lambda p, x: p >= x, "acima de")):
            alvo = conf.get(campo)
            if alvo and a.get("preco") and cond(a["preco"], float(alvo)):
                chave = f"alvo:{tk}:{campo}:{alvo}:{hoje}"
                if not ctrl.ja_enviado(chave):
                    ctrl.marcar(chave)
                    da_lista.append(f"🎯 <b>{esc(tk)}</b> chegou {texto} {fmt_reais(float(alvo))}")

    # 2) Mercado: altas/quedas muito fortes no dia
    limite_m = float(cfg.get("variacao_dia_mercado", 0) or 0)
    nota_m = float(cfg.get("variacao_dia_mercado_nota", 0) or 0)
    if limite_m:
        fortes = [a for c in ("acoes", "fiis") for a in mercado.get(c, [])
                  if a.get("var_dia") is not None and abs(a["var_dia"]) >= limite_m and a["ticker"] not in lista_cfg
                  and (a.get("nota") or 0) >= nota_m]
        for a in sorted(fortes, key=lambda x: -abs(x["var_dia"])):
            chave = f"forte:{a['ticker']}:{hoje}"
            if ctrl.ja_enviado(chave):
                continue
            ctrl.marcar(chave)
            mercado_msgs.append(f"{_bola(a['var_dia'])} {_cab(a)} {_pct_sinal(a['var_dia'])} · nota {_nota(a['nota'])}")

    maximo = int(cfg.get("maximo_por_mensagem", 12))
    if len(mercado_msgs) > maximo:
        resto = len(mercado_msgs) - maximo
        mercado_msgs = mercado_msgs[:maximo] + [f"… e mais {resto} no app"]
    blocos = []
    if da_lista:
        blocos.append("⭐ <b>Sua lista</b>\n" + "\n".join(da_lista))
    if mercado_msgs:
        blocos.append("⚡ <b>Boas empresas que mexeram forte hoje</b>\n" + "\n".join(mercado_msgs))
    return blocos


# ---------------------------------------------------------------------------
# Filtros "para estudar" (uma vez por dia, no resumo)
# ---------------------------------------------------------------------------

def alertas_de_filtros(mercado: dict, config: dict, ctrl: Controle) -> list[str]:
    """Cada ativo só é avisado de novo depois de 7 dias. Só os melhores de cada grupo
    (config: alertas.quantidade_por_grupo); o resto aparece no app."""
    cfg = config.get("alertas", {})
    por_filtro = int(cfg.get("quantidade_por_grupo", 3))
    blocos = []

    c = cfg.get("caiu_mas_solida", {})
    if c.get("ligado"):
        achados = [a for a in mercado.get("acoes", [])
                   if a.get("var_30d") is not None and a["var_30d"] <= float(c.get("queda_30_dias", -12))
                   and (a.get("nota") or 0) >= float(c.get("nota_minima", 7))]
        novos = [a for a in sorted(achados, key=lambda a: (-(a["nota"] or 0), a["var_30d"]))
                 if not ctrl.ja_enviado(f"solida:{a['ticker']}", dias=7)][:por_filtro]
        itens = []
        for a in novos:
            ctrl.marcar(f"solida:{a['ticker']}")
            linha2 = f"caiu {_pct(a['var_30d'])} no mês · nota {_nota(a['nota'])}"
            aviso = _aviso(a)
            itens.append(f"{_cab(a)}\n{linha2}" + (f"\n⚠️ {aviso}" if aviso else ""))
        if itens:
            resto = len(achados) - len(itens)
            blocos.append(
                "💡 <b>Caíram muito, mas a empresa vai bem</b>\n\n" + "\n\n".join(itens)
                + "\n\n<i>Pesquise o motivo da queda antes de decidir.</i>"
                + (f"\n+{resto} no app" if resto > 0 else ""))

    f = cfg.get("fii_com_desconto", {})
    if f.get("ligado"):
        achados = [a for a in mercado.get("fiis", [])
                   if a.get("pvp") and a["pvp"] <= float(f.get("pvp_maximo", 0.92))
                   and (a.get("dy") or 0) >= float(f.get("dy_minimo", 9))
                   and (a.get("nota") or 0) >= float(f.get("nota_minima", 7))]
        novos = [a for a in sorted(achados, key=lambda a: (-(a["nota"] or 0), a["pvp"]))
                 if not ctrl.ja_enviado(f"fii:{a['ticker']}", dias=7)][:por_filtro]
        itens = []
        for a in novos:
            ctrl.marcar(f"fii:{a['ticker']}")
            por_mes = fmt_reais(a["dy"] * 10 / 12)  # rendimento anual % → R$ por mês a cada R$ 1.000
            linha2 = f"{_pct((1 - a['pvp']) * 100)} de desconto · rende {por_mes}/mês por R$ 1 mil"
            aviso = _aviso(a)
            itens.append(f"{_cab(a)}\n{linha2}" + (f"\n⚠️ {aviso}" if aviso else ""))
        if itens:
            resto = len(achados) - len(itens)
            blocos.append(
                "🏢 <b>Fundos imobiliários em promoção</b>\n\n" + "\n\n".join(itens)
                + "\n\n<i>Desconto pode ser oportunidade ou sinal de problema.</i>"
                + (f"\n+{resto} no app" if resto > 0 else ""))
    return blocos


# ---------------------------------------------------------------------------
# Possibilidades da IA
# ---------------------------------------------------------------------------

def texto_possibilidade(p: dict) -> str:
    icone = {"alta": "📈", "queda": "📉"}.get(p["direcao"], "❔")
    direcao = {"alta": "Pode subir", "queda": "Pode cair"}.get(p["direcao"], "Efeito incerto")
    alvo = f'<b>{esc(p["ativo"])}</b> · {esc(p.get("nome", ""))}' if p.get("ativo") else f'<b>{esc(p.get("nome", ""))}</b>'
    linhas = [
        f"{icone} {alvo}",
        f"{direcao} {NOME_PRAZO.get(p['prazo'], '')} · chance {NOME_CHANCE.get(p['chance'], p['chance'])}",
        "",
        esc(p["explicacao"]),
        "",
        f"⚖️ <i>Por outro lado:</i> {esc(p['contraponto'])}",
    ]
    fontes = " · ".join(link(f["fonte"], f.get("link")) for f in p.get("fontes", [])[:3])
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
        blocos.insert(0, "🧠 <b>O que as notícias podem causar</b>")
    return blocos


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------

def montar_mensagem(blocos: list[str], titulo: str, site_url: str | None) -> str | None:
    if not blocos:
        return None
    partes = [f"📡 <b>{esc(titulo)}</b> · {agora().strftime('%d/%m %H:%M')}"] + blocos
    rodape = "👉 " + link("Abrir o Radar", site_url) + "\n" + RODAPE if site_url else RODAPE
    partes.append(rodape)
    return "\n\n".join(partes)


def resumo_do_dia(mercado: dict, analise: dict | None, site_url: str | None) -> str:
    m = mercado.get("macro", {})
    idx = indice_por_ticker(mercado)
    blocos = []

    dia = []
    if m.get("ibov"):
        v = m["ibov"].get("var_dia")
        dia.append(f"{_bola(v)} Bolsa {_pct_sinal(v)}")
    if m.get("dolar"):
        dia.append(f"💵 Dólar {fmt_reais(m['dolar']['valor'])}")
    if m.get("selic") is not None:
        dia.append(f"🏦 Juros {str(m['selic']).replace('.', ',')}% ao ano")
    if dia:
        blocos.append("📊 <b>Hoje</b>\n" + "\n".join(dia))

    lista = [idx[t] for t in mercado.get("minha_lista", []) if t in idx]
    if lista:
        itens = [f"{_bola(a.get('var_dia'))} <b>{esc(a['ticker'])}</b> {_pct_sinal(a.get('var_dia'))}"
                 for a in sorted(lista, key=lambda a: -(a.get("var_dia") or 0))]
        blocos.append("⭐ <b>Sua lista</b>\n" + "\n".join(itens))

    acoes = [a for a in mercado.get("acoes", []) if a.get("var_dia") is not None]
    if acoes:
        altas = sorted(acoes, key=lambda a: -a["var_dia"])[:3]
        quedas = sorted(acoes, key=lambda a: a["var_dia"])[:3]
        blocos.append("📈 <b>Mais subiram</b>\n" + "\n".join(f"{_cab(a)} {_pct_sinal(a['var_dia'])}" for a in altas))
        blocos.append("📉 <b>Mais caíram</b>\n" + "\n".join(f"{_cab(a)} {_pct_sinal(a['var_dia'])}" for a in quedas))

    if analise and analise.get("resumo"):
        blocos.append(f"🧠 <b>O que mexeu no mercado</b>\n{esc(analise['resumo'])}")
        if analise.get("agenda"):
            blocos.append("🗓️ <b>Fique de olho</b>\n"
                          + "\n".join(f'• {esc(e["quando"])}: {esc(e["evento"])}' for e in analise["agenda"][:3]))
    return montar_mensagem(blocos, "Resumo do dia", site_url)
