"""Envio de mensagens pelo Telegram (bot criado no @BotFather)."""
from __future__ import annotations

import html
import os

from .util import log, sessao


def esc(texto) -> str:
    return html.escape(str(texto if texto is not None else ""), quote=False)


def link(texto: str, url: str | None) -> str:
    if not url:
        return esc(texto)
    return f'<a href="{html.escape(url, quote=True)}">{esc(texto)}</a>'


def _dividir(texto: str, limite: int = 3900) -> list[str]:
    """Divide em blocos (separados por linha em branco) sem quebrar tags HTML."""
    partes, atual = [], ""
    for bloco in texto.split("\n\n"):
        if len(atual) + len(bloco) + 2 > limite and atual:
            partes.append(atual)
            atual = ""
        atual = f"{atual}\n\n{bloco}" if atual else bloco
    if atual:
        partes.append(atual)
    return partes


def configurado() -> bool:
    return bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def enviar(texto: str) -> bool:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log.info("Telegram não configurado. Mensagem que seria enviada:\n%s", texto)
        return False
    ok = True
    for parte in _dividir(texto):
        try:
            r = sessao().post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat,
                    "text": parte,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
                timeout=30,
            )
            if not r.ok:
                log.error("Telegram recusou a mensagem (%s): %s", r.status_code, r.text[:300])
                ok = False
        except Exception as e:  # não mostra a URL (ela contém o token)
            log.error("Falha ao falar com o Telegram: %s", type(e).__name__)
            ok = False
    return ok
