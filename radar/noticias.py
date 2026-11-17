"""Coleta de notícias de sites confiáveis (feeds RSS e Google Notícias)."""
from __future__ import annotations

import html
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser

from .util import agora, log, sessao

_TAG = re.compile(r"<[^>]+>")


def _texto(v: str | None, limite: int) -> str:
    if not v:
        return ""
    t = html.unescape(_TAG.sub(" ", v))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limite]


def _data(e) -> datetime | None:
    for campo in ("published", "updated"):
        v = e.get(campo)
        if not v:
            continue
        try:
            d = parsedate_to_datetime(v)
        except (TypeError, ValueError):
            try:
                d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone(timedelta(hours=-3)))
        return d
    return None


def _baixar(url: str):
    """Baixa o feed; no Google Notícias espera um pouco entre buscas para não ser bloqueado."""
    google = "news.google.com" in url
    for tentativa in range(3):
        if google:
            time.sleep(1.5 + tentativa * 6)
        r = sessao().get(url, timeout=25)
        if r.status_code == 429 and tentativa < 2:
            continue
        r.raise_for_status()
        return r
    return None


def _ler_feed(url: str, fonte_padrao: str, horas: float) -> list[dict]:
    try:
        r = _baixar(url)
    except Exception as e:
        log.warning("Feed falhou (%s): %s", fonte_padrao, type(e).__name__)
        return []
    if r is None:
        return []
    d = feedparser.parse(r.content)
    limite = agora() - timedelta(hours=horas)
    itens = []
    for e in d.entries:
        quando = _data(e)
        if quando and quando < limite:
            continue
        titulo = _texto(e.get("title"), 220)
        fonte = fonte_padrao
        # Google Notícias põe a fonte no fim do título: "Manchete - InfoMoney"
        if "news.google.com" in url and " - " in titulo:
            titulo, fonte = titulo.rsplit(" - ", 1)
        if not titulo:
            continue
        itens.append({
            "titulo": titulo,
            "fonte": fonte,
            "link": e.get("link"),
            "quando": quando.isoformat(timespec="minutes") if quando else None,
            "resumo": "" if "news.google.com" in url else _texto(e.get("summary"), 300),
            "via_google": "news.google.com" in url,
        })
    return itens


def google_noticias(busca: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(busca)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"


def _chave(titulo: str) -> str:
    return re.sub(r"[^a-z0-9]", "", titulo.lower())[:70]


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _filtrar(itens: list[dict], cfg: dict) -> list[dict]:
    ignorar = [_sem_acento(p) for p in cfg.get("ignorar_palavras", [])]
    confiaveis = [_sem_acento(f) for f in cfg.get("google_fontes_confiaveis", [])]
    ok = []
    for n in itens:
        titulo = _sem_acento(n["titulo"])
        if any(p in titulo for p in ignorar):
            continue
        if n.get("via_google") and confiaveis and not any(c in _sem_acento(n["fonte"]) for c in confiaveis):
            continue
        ok.append(n)
    return ok


def coletar(config: dict) -> list[dict]:
    cfg = config.get("noticias", {})
    horas = float(cfg.get("horas", 18))
    # Segunda de manhã / fim de semana: olha mais para trás
    if agora().weekday() in (0, 5, 6) and agora().hour < 12:
        horas = max(horas, 64)

    todas: list[dict] = []
    for f in cfg.get("fontes", []):
        todas += _ler_feed(f["url"], f["nome"], horas)
    for busca in cfg.get("buscas_google", []):
        todas += _ler_feed(google_noticias(busca + f" when:{max(1, round(horas / 24))}d"), "Google Notícias", horas)

    # Notícias específicas dos ativos da sua lista
    for ativo in config.get("minha_lista", []):
        termo = f'{ativo["ticker"]} OR "{ativo.get("nome", ativo["ticker"])}"'
        itens = _filtrar(_ler_feed(google_noticias(termo + " when:2d"), "Google Notícias", max(horas, 48)), cfg)
        for it in itens[:6]:
            it["sobre"] = ativo["ticker"]
        todas += itens[:6]

    todas = _filtrar(todas, cfg)
    for n in todas:
        n.pop("via_google", None)
    vistos: dict[str, dict] = {}
    unicas = []
    for n in sorted(todas, key=lambda x: x.get("quando") or "", reverse=True):
        k = _chave(n["titulo"])
        if k in vistos:
            if n.get("sobre") and not vistos[k].get("sobre"):
                vistos[k]["sobre"] = n["sobre"]
            continue
        vistos[k] = n
        unicas.append(n)

    maximo = int(config.get("ia", {}).get("maximo_noticias", 150))
    # Garante espaço para as notícias da sua lista
    da_lista = [n for n in unicas if n.get("sobre")]
    gerais = [n for n in unicas if not n.get("sobre")]
    selecionadas = da_lista[: maximo // 3] + gerais
    selecionadas = sorted(selecionadas[:maximo], key=lambda x: x.get("quando") or "", reverse=True)
    for i, n in enumerate(selecionadas, 1):
        n["id"] = i
    log.info("Notícias: %d coletadas, %d únicas, %d selecionadas", len(todas), len(unicas), len(selecionadas))
    return selecionadas
