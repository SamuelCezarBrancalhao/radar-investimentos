"""Coleta de dados de mercado (dados reais e públicos).

Fontes:
  - brapi.dev        → todas as cotações da B3 (preço, variação do dia, nome, setor)
  - Fundamentus      → indicadores das empresas e FIIs (P/L, P/VP, dividendos...)
  - Yahoo Finance    → histórico de 1 ano (variação em 7 dias, 30 dias, 12 meses)
  - Banco Central    → Selic, IPCA e dólar
"""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

from .util import agora, arred, hoje_str, ler_json, log, num_br, salvar_json, sessao

# ---------------------------------------------------------------------------
# brapi: lista de todos os ativos da B3
# ---------------------------------------------------------------------------

TIPOS_BRAPI = {
    ("stock", "stock"): "acao",
    ("stock", "unit"): "acao",
    ("fund", "fii"): "fii",
    ("fund", "fi-agro"): "fii",
    ("fund", "fi-infra"): "fii",
    ("fund", "etf"): "etf",
    ("bdr", "bdr"): "bdr",
}

_CORTES_NOME = [
    " - FUNDO DE INVESTIMENTO", " FUNDO DE INVESTIMENTO", " - FII", " FII ",
    " CLASSE DE", " - RESPONSABILIDADE", " RESPONSABILIDADE LIMITADA", " - FIAGRO",
    " FIAGRO", " FI-INFRA", " FUNDO DE ÍNDICE", " FUNDO DE INDICE", " FUNDO DE ÍNDICES",
]
_SIGLAS = {"S.A.", "S.A", "SA", "S/A", "BB", "FII", "ETF", "BTG", "XP", "CSHG", "BTGP", "TRX", "VBI",
           "HSI", "RBR", "KNRI", "VGIA", "CPTS", "TG", "JS", "BR", "S&P", "IE", "BM&FBOVESPA", "IMA-B",
           "IDIV", "BRL", "USD", "ESG", "IT"}
_MINUSCULAS = {"DE", "DO", "DA", "DOS", "DAS", "E", "EM", "PARA"}


def limpar_nome(nome: str | None, ticker: str) -> str:
    if not nome or nome.strip() == ticker:
        return ticker
    n = nome.strip()
    up = n.upper()
    for corte in _CORTES_NOME:
        i = up.find(corte)
        if i > 3:
            n = n[:i]
            up = up[:i]
    n = re.sub(r"\s+", " ", n).strip(" -")
    palavras = []
    for i, p in enumerate(n.split(" ")):
        if p.upper() in _MINUSCULAS and i > 0:
            palavras.append(p.lower())
        elif p.upper() in _SIGLAS:
            palavras.append(p.upper())
        else:
            palavras.append(p.capitalize())
    n = " ".join(palavras).replace("Bco ", "Banco ")
    return n[:60]


def brapi_lista() -> dict[str, dict]:
    ativos: dict[str, dict] = {}
    pagina = 1
    while pagina <= 10:
        r = sessao().get("https://brapi.dev/api/quote/list",
                         params={"limit": 2000, "page": pagina}, timeout=40)
        r.raise_for_status()
        d = r.json()
        for x in d.get("stocks", []):
            tipo = TIPOS_BRAPI.get((x.get("type"), x.get("subType")))
            if not tipo or not x.get("close"):
                continue
            tk = x["stock"].upper()
            sub = x.get("subType")
            ativos[tk] = {
                "ticker": tk,
                "tipo": tipo,
                "nome": limpar_nome(x.get("name"), tk),
                "preco": arred(x.get("close")),
                "var_dia": arred(x.get("change")),
                "volume_hoje": (x.get("volume") or 0) * (x.get("close") or 0),
                "valor_mercado": x.get("market_cap"),
                "setor": x.get("subsector") or None,
                "logo": x.get("logo"),
                "subtipo": {"fi-agro": "Fiagro", "fi-infra": "FI-Infra"}.get(sub),
            }
        if not d.get("hasNextPage"):
            break
        pagina += 1
    log.info("brapi: %d ativos", len(ativos))
    return ativos


# ---------------------------------------------------------------------------
# Fundamentus: indicadores (1 página com todas as ações e 1 com todos os FIIs)
# ---------------------------------------------------------------------------

def _tabela_fundamentus(url: str) -> tuple[list[str], list[list[str]]]:
    r = sessao().get(url, timeout=40)
    r.raise_for_status()
    s = BeautifulSoup(r.content, "lxml")  # a página declara o próprio charset
    tab = s.find("table", id="resultado") or s.find("table", id="tabelaResultado") or s.find("table")
    cab = [th.get_text(strip=True) for th in tab.find("thead").find_all("th")]
    linhas = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in tab.find("tbody").find_all("tr")]
    return cab, linhas


def _coluna(cab: list[str], *nomes: str) -> int | None:
    norm = [c.lower().replace(" ", "") for c in cab]
    for nome in nomes:
        n = nome.lower().replace(" ", "")
        for i, c in enumerate(norm):
            if c.startswith(n):
                return i
    return None


def fundamentus_acoes() -> dict[str, dict]:
    cab, linhas = _tabela_fundamentus("https://www.fundamentus.com.br/resultado.php")
    idx = {
        "cotacao_ref": _coluna(cab, "Cotação"),
        "pl": _coluna(cab, "P/L"),
        "pvp": _coluna(cab, "P/VP"),
        "dy": _coluna(cab, "Div.Yield"),
        "ev_ebitda": _coluna(cab, "EV/EBITDA"),
        "margem_liq": _coluna(cab, "Mrg. Líq", "Mrg.Líq"),
        "liq_corrente": _coluna(cab, "Liq. Corr"),
        "roic": _coluna(cab, "ROIC"),
        "roe": _coluna(cab, "ROE"),
        "liq_2m": _coluna(cab, "Liq.2meses"),
        "patrimonio": _coluna(cab, "Patrim. Líq"),
        "div_liq_pl": _coluna(cab, "Dív.Líq/ Patrim", "Dív.Brut/ Patrim"),
        "cresc_5a": _coluna(cab, "Cresc. Rec"),
    }
    out = {}
    for ln in linhas:
        if not ln:
            continue
        d = {k: (num_br(ln[i]) if i is not None and i < len(ln) else None) for k, i in idx.items()}
        out[ln[0].upper()] = d
    log.info("Fundamentus ações: %d", len(out))
    return out


def fundamentus_fiis() -> dict[str, dict]:
    cab, linhas = _tabela_fundamentus("https://www.fundamentus.com.br/fii_resultado.php")
    idx_seg = _coluna(cab, "Segmento")
    idx = {
        "cotacao_ref": _coluna(cab, "Cotação"),
        "ffo_yield": _coluna(cab, "FFO Yield"),
        "dy": _coluna(cab, "Dividend Yield"),
        "pvp": _coluna(cab, "P/VP"),
        "valor_mercado": _coluna(cab, "Valor de Mercado"),
        "liq_2m": _coluna(cab, "Liquidez"),
        "imoveis": _coluna(cab, "Qtd de imóveis"),
        "cap_rate": _coluna(cab, "Cap Rate"),
        "vacancia": _coluna(cab, "Vacância"),
    }
    out = {}
    for ln in linhas:
        if not ln:
            continue
        d = {k: (num_br(ln[i]) if i is not None and i < len(ln) else None) for k, i in idx.items()}
        d["segmento"] = ln[idx_seg] if idx_seg is not None and idx_seg < len(ln) else None
        out[ln[0].upper()] = d
    log.info("Fundamentus FIIs: %d", len(out))
    return out


# ---------------------------------------------------------------------------
# Yahoo Finance: histórico diário de ~1 ano
# ---------------------------------------------------------------------------

def yahoo_historico(tickers: list[str]) -> tuple[dict, dict]:
    """Retorna (referencias, semanal).

    referencias[ticker] = preços de 5, 21 e 252 pregões atrás, máxima/mínima de
    12 meses e liquidez média de 21 pregões.
    semanal[ticker] = lista de fechamentos semanais (para o mini-gráfico).
    """
    import yfinance as yf

    refs, semanal = {}, {}
    for i in range(0, len(tickers), 80):
        lote = tickers[i:i + 80]
        try:
            df = yf.download([t + ".SA" for t in lote], period="13mo", interval="1d",
                             auto_adjust=False, group_by="ticker", progress=False, threads=True)
        except Exception as e:  # Yahoo às vezes bloqueia; seguimos sem histórico
            log.warning("Yahoo falhou no lote %d: %s", i, e)
            continue
        for t in lote:
            try:
                sub = df[t + ".SA"]
                fech = sub["Close"].dropna()
                vol = sub["Volume"].reindex(fech.index).fillna(0)
            except KeyError:
                continue
            if len(fech) < 10:
                continue

            def atras(n):
                return arred(fech.iloc[-1 - n]) if len(fech) > n else None

            ult252 = fech.iloc[-252:]
            refs[t] = {
                "c5": atras(5),
                "c21": atras(21),
                "c252": atras(252) if len(fech) > 240 else None,
                "max52": arred(ult252.max()),
                "min52": arred(ult252.min()),
                "liq21": arred(float((fech.iloc[-21:] * vol.iloc[-21:]).mean()), 0),
                "data_ult": str(fech.index[-1].date()),
                "ult": arred(fech.iloc[-1]),
            }
            sem = fech.resample("W").last().dropna().iloc[-53:]
            semanal[t] = [arred(v) for v in sem.tolist()]
    log.info("Yahoo: histórico de %d ativos", len(refs))
    return refs, semanal


def indices_yahoo() -> dict:
    import yfinance as yf

    out = {}
    nomes = {"^BVSP": "ibov", "BRL=X": "dolar", "IFIX.SA": "ifix"}
    try:
        df = yf.download(list(nomes), period="10d", interval="1d", auto_adjust=False,
                         group_by="ticker", progress=False, threads=True)
    except Exception as e:
        log.warning("Yahoo índices falhou: %s", e)
        return out
    for tk, chave in nomes.items():
        try:
            c = df[tk]["Close"].dropna()
        except KeyError:
            continue
        if len(c) >= 2:
            out[chave] = {"valor": arred(c.iloc[-1]), "var_dia": arred((c.iloc[-1] / c.iloc[-2] - 1) * 100)}
    return out


# ---------------------------------------------------------------------------
# Banco Central
# ---------------------------------------------------------------------------

def banco_central() -> dict:
    out = {}
    for cod, chave in [(432, "selic"), (13522, "ipca_12m"), (1, "dolar_ptax")]:
        try:
            r = sessao().get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados/ultimos/1",
                             params={"formato": "json"}, timeout=20)
            r.raise_for_status()
            out[chave] = arred(float(r.json()[-1]["valor"]))
        except Exception as e:
            log.warning("Banco Central série %s falhou: %s", cod, e)
    return out


# ---------------------------------------------------------------------------
# Notas de fundamentos (fórmula simples e transparente, de 0 a 10)
# ---------------------------------------------------------------------------

def _faixa(v, regras):
    """regras = [(condição, pontos), ...]; retorna os pontos da primeira que bater."""
    if v is None:
        return 0
    for cond, pts in regras:
        if cond(v):
            return pts
    return 0


def nota_acao(a: dict) -> tuple[float | None, list[str]]:
    pl, pvp, dy, roe, div, cr = (a.get(k) for k in ("pl", "pvp", "dy", "roe", "div_liq_pl", "cresc_5a"))
    if pl is None and roe is None:
        return None, []
    pts = 0.0
    # P/L abaixo de 3 e dividendos acima de 15% costumam ser pontuais: ganham menos pontos
    pts += _faixa(pl, [(lambda v: 0 < v < 3, 1), (lambda v: 0 < v <= 6, 2), (lambda v: 0 < v <= 10, 1.5),
                       (lambda v: 0 < v <= 15, 1), (lambda v: 0 < v <= 25, 0.5)])
    pts += _faixa(pvp, [(lambda v: 0 < v <= 1, 1.5), (lambda v: 0 < v <= 2, 1), (lambda v: 0 < v <= 3, 0.5)])
    pts += _faixa(dy, [(lambda v: v > 15, 1), (lambda v: v >= 8, 2), (lambda v: v >= 5, 1.5),
                       (lambda v: v >= 3, 1), (lambda v: v > 0, 0.5)])
    pts += _faixa(roe, [(lambda v: v >= 20, 2), (lambda v: v >= 15, 1.5), (lambda v: v >= 10, 1), (lambda v: v > 0, 0.5)])
    pts += _faixa(div, [(lambda v: v <= 0.5, 1.5), (lambda v: v <= 1, 1), (lambda v: v <= 2, 0.5)])
    pts += _faixa(cr, [(lambda v: v >= 10, 1), (lambda v: v > 0, 0.5)])

    avisos = []
    if dy is not None and dy > 15:
        avisos.append("Dividendos muito altos: podem ter sido extraordinários")
    if pl is not None and 0 < pl < 3:
        avisos.append("P/L muito baixo: o lucro pode ter sido pontual")
    if (pl is not None and pl < 0) or (roe is not None and roe < 0):
        avisos.append("Teve prejuízo nos últimos 12 meses")
    if div is not None and div > 2:
        avisos.append("Dívida alta em relação ao patrimônio")
    return round(min(pts, 10), 1), avisos


def nota_fii(f: dict) -> tuple[float | None, list[str]]:
    dy, pvp, liq, vac, imv = (f.get(k) for k in ("dy", "pvp", "liq_2m", "vacancia", "imoveis"))
    if dy is None and pvp is None:
        return None, []
    pts = 0.0
    pts += _faixa(dy, [(lambda v: 8 <= v <= 13, 3), (lambda v: 6 <= v <= 16, 1.5), (lambda v: v > 16, 0.5)])
    pts += _faixa(pvp, [(lambda v: 0.85 <= v <= 1.0, 3), (lambda v: 0.7 <= v < 0.85, 2),
                        (lambda v: 1.0 < v <= 1.1, 2), (lambda v: 1.1 < v <= 1.25, 1)])
    pts += _faixa(liq, [(lambda v: v >= 5e6, 2), (lambda v: v >= 1e6, 1.5), (lambda v: v >= 3e5, 1)])
    if imv and imv > 0:
        pts += _faixa(vac, [(lambda v: v <= 5, 2), (lambda v: v <= 10, 1.5), (lambda v: v <= 20, 0.5)])
    else:
        pts += 1.5  # fundo de papel/recebíveis: vacância não se aplica

    avisos = []
    if dy is not None and dy > 16:
        avisos.append("Rendimento muito alto: confira se é recorrente")
    if vac is not None and vac > 15:
        avisos.append("Vacância alta (imóveis vazios)")
    if pvp is not None and 0 < pvp < 0.7:
        avisos.append("Desconto muito grande: o mercado vê algum risco")
    if imv is not None and 0 < imv <= 2:
        avisos.append("Poucos imóveis: pouca diversificação")
    return round(min(pts, 10), 1), avisos


# ---------------------------------------------------------------------------
# Montagem final
# ---------------------------------------------------------------------------

def _var(preco, ref):
    if not preco or not ref:
        return None
    return arred((preco / ref - 1) * 100)


def atualizar_referencias(pasta_dados: Path, ativos: dict, config: dict, forcar=False) -> dict:
    """Busca Fundamentus + histórico do Yahoo uma vez por dia (não muda no intradiário)."""
    caminho = pasta_dados / "referencias.json"
    refs = ler_json(caminho, {}) or {}
    if not forcar and refs.get("data") == hoje_str() and refs.get("historico"):
        return refs

    log.info("Atualizando referências do dia (Fundamentus + Yahoo)...")
    novo = {"data": hoje_str()}
    try:
        novo["fund_acoes"] = fundamentus_acoes()
    except Exception as e:
        log.warning("Fundamentus ações falhou: %s", e)
        novo["fund_acoes"] = refs.get("fund_acoes", {})
    try:
        novo["fund_fiis"] = fundamentus_fiis()
    except Exception as e:
        log.warning("Fundamentus FIIs falhou: %s", e)
        novo["fund_fiis"] = refs.get("fund_fiis", {})

    # Candidatos: ativos com alguma liquidez (o filtro final é feito depois)
    minimos = config.get("liquidez_minima", {})
    lista = {i["ticker"] for i in config.get("minha_lista", [])}
    candidatos = []
    for tk, a in ativos.items():
        tipo = a["tipo"]
        minimo = minimos.get({"acao": "acoes", "fii": "fiis", "etf": "etfs", "bdr": "bdrs"}[tipo], 1e6)
        if tipo == "acao":
            liq = (novo["fund_acoes"].get(tk) or {}).get("liq_2m") or a["volume_hoje"]
        elif tipo == "fii":
            liq = (novo["fund_fiis"].get(tk) or {}).get("liq_2m") or a["volume_hoje"]
        else:
            liq = a["volume_hoje"] * 3  # volume de hoje varia muito; margem
        if liq >= minimo * 0.5 or tk in lista:
            candidatos.append(tk)

    hist, semanal = yahoo_historico(sorted(candidatos))
    if not hist and refs.get("historico"):
        log.warning("Sem histórico novo; mantendo o anterior")
        hist = refs["historico"]
        semanal = ler_json(pasta_dados / "historico.json", {}).get("semanal", {})
    novo["historico"] = hist
    salvar_json(caminho, novo)
    salvar_json(pasta_dados / "historico.json", {"data": hoje_str(), "semanal": semanal})
    return novo


def montar_mercado(pasta_dados: Path, config: dict, forcar_refs=False) -> dict:
    ativos = brapi_lista()
    refs = atualizar_referencias(pasta_dados, ativos, config, forcar=forcar_refs)
    fund_a, fund_f, hist = refs.get("fund_acoes", {}), refs.get("fund_fiis", {}), refs.get("historico", {})
    minimos = config.get("liquidez_minima", {})
    lista = [i["ticker"].upper() for i in config.get("minha_lista", [])]

    saida = {"acoes": [], "fiis": [], "etfs": [], "bdrs": []}
    for tk, a in ativos.items():
        tipo = a["tipo"]
        h = hist.get(tk, {})
        preco = a["preco"]
        item = {
            "ticker": tk, "nome": a["nome"], "preco": preco, "var_dia": a["var_dia"],
            "var_7d": _var(preco, h.get("c5")), "var_30d": _var(preco, h.get("c21")),
            "var_12m": _var(preco, h.get("c252")),
            "max_12m": h.get("max52"), "min_12m": h.get("min52"),
            "setor": a["setor"], "logo": a["logo"],
        }
        if item["max_12m"] and preco and preco > item["max_12m"]:
            item["max_12m"] = preco
        if item["min_12m"] and preco and preco < item["min_12m"]:
            item["min_12m"] = preco

        if tipo == "acao":
            f = fund_a.get(tk, {})
            liq = f.get("liq_2m") or h.get("liq21") or a["volume_hoje"]
            fator = (preco / f["cotacao_ref"]) if preco and f.get("cotacao_ref") else 1.0
            item.update({
                "pl": arred(f["pl"] * fator) if f.get("pl") else f.get("pl"),
                "pvp": arred(f["pvp"] * fator) if f.get("pvp") else f.get("pvp"),
                "dy": arred(f["dy"] / fator) if f.get("dy") else f.get("dy"),
                "roe": f.get("roe"), "margem_liq": f.get("margem_liq"),
                "div_liq_pl": f.get("div_liq_pl"), "cresc_5a": f.get("cresc_5a"),
                "ev_ebitda": f.get("ev_ebitda"), "valor_mercado": a["valor_mercado"],
            })
            item["nota"], item["avisos"] = nota_acao(item)
            chave = "acoes"
        elif tipo == "fii":
            f = fund_f.get(tk, {})
            liq = f.get("liq_2m") or h.get("liq21") or a["volume_hoje"]
            fator = (preco / f["cotacao_ref"]) if preco and f.get("cotacao_ref") else 1.0
            item.update({
                "segmento": a.get("subtipo") or f.get("segmento") or a["setor"],
                "dy": arred(f["dy"] / fator) if f.get("dy") else f.get("dy"),
                "pvp": arred(f["pvp"] * fator) if f.get("pvp") else f.get("pvp"),
                "vacancia": f.get("vacancia"), "imoveis": f.get("imoveis"),
                "cap_rate": f.get("cap_rate"), "valor_mercado": f.get("valor_mercado"),
            })
            item["liq_2m"] = liq
            item["nota"], item["avisos"] = nota_fii(item)
            chave = "fiis"
        else:
            liq = h.get("liq21") or a["volume_hoje"]
            item["nota"], item["avisos"] = None, []
            chave = "etfs" if tipo == "etf" else "bdrs"

        minimo = minimos.get(chave, 1e6)
        if (liq or 0) < minimo and tk not in lista:
            continue
        item["liquidez"] = arred(liq, 0)
        if item["min_12m"] and preco and preco <= item["min_12m"] * 1.05:
            item["avisos"] = item["avisos"] + ["Perto da mínima de 12 meses"]
        elif item["max_12m"] and preco and preco >= item["max_12m"] * 0.97:
            item["avisos"] = item["avisos"] + ["Perto da máxima de 12 meses"]
        saida[chave].append(item)

    for chave in saida:
        saida[chave].sort(key=lambda x: -(x.get("liquidez") or 0))

    macro = banco_central()
    macro.update(indices_yahoo())
    if "dolar" not in macro and macro.get("dolar_ptax"):
        macro["dolar"] = {"valor": macro["dolar_ptax"], "var_dia": None}

    mercado = {
        "atualizado": agora().isoformat(timespec="minutes"),
        "data_referencias": refs.get("data"),
        "macro": macro,
        "minha_lista": lista,
        "regras": {k: config.get("alertas", {}).get(k, {}) for k in ("caiu_mas_solida", "fii_com_desconto")},
        **saida,
    }
    log.info("Mercado: %d ações, %d FIIs, %d ETFs, %d BDRs",
             len(saida["acoes"]), len(saida["fiis"]), len(saida["etfs"]), len(saida["bdrs"]))
    return mercado


def indice_por_ticker(mercado: dict) -> dict[str, dict]:
    idx = {}
    for chave in ("acoes", "fiis", "etfs", "bdrs"):
        for item in mercado.get(chave, []):
            idx[item["ticker"]] = {**item, "categoria": chave}
    return idx
