"""Funções pequenas usadas em vários lugares."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

RAIZ = Path(__file__).resolve().parent.parent
FUSO_BR = timezone(timedelta(hours=-3))  # Brasília (sem horário de verão)

log = logging.getLogger("radar")

_sessao: requests.Session | None = None


def sessao() -> requests.Session:
    global _sessao
    if _sessao is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9",
        })
        _sessao = s
    return _sessao


def agora() -> datetime:
    return datetime.now(FUSO_BR)


def hoje_str() -> str:
    return agora().strftime("%Y-%m-%d")


def carregar_config() -> dict:
    with open(RAIZ / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def ler_json(caminho: Path, padrao=None):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return padrao


def salvar_json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, caminho)


def num_br(texto: str | None) -> float | None:
    """Converte '1.234,56' ou '12,5%' em float. Retorna None se vazio."""
    if texto is None:
        return None
    t = str(texto).strip().replace("%", "").replace(".", "").replace(",", ".")
    if t in ("", "-", "--"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def arred(v, casas=2):
    if v is None:
        return None
    try:
        if v != v:  # NaN
            return None
        return round(float(v), casas)
    except (TypeError, ValueError):
        return None


def fmt_pct(v, casas=1, sinal=True) -> str:
    if v is None:
        return "–"
    s = f"{v:+.{casas}f}" if sinal else f"{v:.{casas}f}"
    return s.replace(".", ",") + "%"


def fmt_num(v, casas=2) -> str:
    if v is None:
        return "–"
    return f"{v:.{casas}f}".replace(".", ",")


def fmt_reais(v) -> str:
    if v is None:
        return "–"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"
