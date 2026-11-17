"""Ponto de entrada do robô.

Uso:
    python -m radar --modo mercado     # cotações + alertas por regras (a cada 30 min no pregão)
    python -m radar --modo analise     # notícias + IA + alertas de possibilidades
    python -m radar --modo resumo      # tudo + resumo do dia no Telegram (fim do pregão)
    python -m radar --modo teste       # manda uma mensagem de teste no Telegram

Os dados são gravados em publicar/dados/ e a página do app é copiada para publicar/.
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys

from . import alertas, ia, mercado, noticias, telegram
from .util import RAIZ, agora, carregar_config, ler_json, log, salvar_json

PUBLICAR = RAIZ / "publicar"
DADOS = PUBLICAR / "dados"


def copiar_site() -> None:
    origem = RAIZ / "site"
    for arq in origem.iterdir():
        if arq.is_file():
            shutil.copy2(arq, PUBLICAR / arq.name)
    (PUBLICAR / ".nojekyll").touch()


def main() -> int:
    ap = argparse.ArgumentParser(description="Radar de Investimentos")
    ap.add_argument("--modo", choices=["mercado", "analise", "resumo", "teste"], default="mercado")
    ap.add_argument("--forcar-referencias", action="store_true", help="rebaixa Fundamentus/Yahoo mesmo já tendo hoje")
    ap.add_argument("--sem-telegram", action="store_true", help="não envia nada, só mostra no log")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    if args.sem_telegram:
        os.environ.pop("TELEGRAM_TOKEN", None)

    config = carregar_config()
    site_url = os.environ.get("SITE_URL")
    DADOS.mkdir(parents=True, exist_ok=True)

    if args.modo == "teste":
        ok = telegram.enviar(
            "✅ <b>Radar conectado!</b>\nA partir de agora você recebe aqui os alertas e o resumo do dia."
            + (f"\n\n{telegram.link('Abrir o Radar', site_url)}" if site_url else "")
        )
        return 0 if ok else 1

    estado = ler_json(DADOS / "estado.json", {}) or {}
    ctrl = alertas.Controle(estado)
    ctrl.limpar_antigos()
    enviados_antes = dict(ctrl.enviados)

    dados_mercado = mercado.montar_mercado(DADOS, config, forcar_refs=args.forcar_referencias)
    salvar_json(DADOS / "mercado.json", dados_mercado)

    blocos: list[str] = []
    analise = ler_json(DADOS / "analise.json")

    if args.modo in ("analise", "resumo"):
        lista_noticias = noticias.coletar(config)
        salvar_json(DADOS / "noticias.json", {"atualizado": agora().isoformat(timespec="minutes"),
                                               "noticias": lista_noticias})
        nova = ia.analisar(lista_noticias, dados_mercado, config)
        if nova:
            analise = nova
            salvar_json(DADOS / "analise.json", analise)
            blocos += alertas.alertas_de_ia(analise, config, ctrl)

    if args.modo == "mercado":
        blocos = alertas.alertas_de_mercado(dados_mercado, config, ctrl) + blocos
        msg = alertas.montar_mensagem(blocos, "Radar: alertas", site_url)
    elif args.modo == "analise":
        msg = alertas.montar_mensagem(blocos, "Radar: notícias", site_url)
    else:  # resumo
        resumo = alertas.resumo_do_dia(dados_mercado, analise, site_url)
        blocos = alertas.alertas_de_filtros(dados_mercado, config, ctrl) + blocos
        extra = alertas.montar_mensagem(blocos, "Radar: para estudar", site_url)
        msg = resumo + (f"\n\n{'—' * 10}\n\n{extra}" if extra else "")

    if msg:
        if not telegram.enviar(msg):
            # não chegou no celular: esquece estes alertas para tentar de novo na próxima rodada
            estado["enviados"] = enviados_antes
    else:
        log.info("Nenhum alerta novo nesta rodada")

    estado["ultima_rodada"] = {"modo": args.modo, "quando": agora().isoformat(timespec="minutes")}
    salvar_json(DADOS / "estado.json", estado)
    copiar_site()
    return 0


if __name__ == "__main__":
    sys.exit(main())
