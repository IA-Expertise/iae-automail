"""
Executa a campanha de e-mails em uma thread de fundo independente do Streamlit.
O estado é mantido em variáveis de módulo (persistem entre reruns do Streamlit).
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_lock = threading.Lock()

_STATE: dict[str, Any] = {
    "running": False,
    "status": "idle",
    "sucesso": 0,
    "erros": 0,
    "total": 0,
    "processados": 0,
    "log": "",
    "last_successes": [],
    "last_errors": [],
    "destinatarios_planejados": [],
    "relatorio_em": "",
    "relatorio_utm": "",
    "motivo_interrupcao": "",
}

_cancel_event = threading.Event()


def get_state() -> dict[str, Any]:
    with _lock:
        return dict(_STATE)


def is_running() -> bool:
    with _lock:
        return bool(_STATE["running"])


def cancel() -> None:
    _cancel_event.set()


def _set(key: str, value: Any) -> None:
    with _lock:
        _STATE[key] = value


def _update(updates: dict[str, Any]) -> None:
    with _lock:
        _STATE.update(updates)


def start_campaign(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_email: str,
    destinatarios: list[dict],
    assunto_tpl: str,
    corpo_tpl: str,
    utm_campaign: str,
    usar_testeira: bool,
    com_banner: bool,
    img_path: Optional[Path],
    pdf_path: Optional[Path],
    relatorio_file: Path,
) -> bool:
    """Inicia a campanha em thread de fundo. Retorna False se já houver uma rodando."""
    with _lock:
        if _STATE["running"]:
            return False

    _cancel_event.clear()

    thread = threading.Thread(
        target=_run,
        kwargs=dict(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            from_email=from_email,
            destinatarios=destinatarios,
            assunto_tpl=assunto_tpl,
            corpo_tpl=corpo_tpl,
            utm_campaign=utm_campaign,
            usar_testeira=usar_testeira,
            com_banner=com_banner,
            img_path=img_path,
            pdf_path=pdf_path,
            relatorio_file=relatorio_file,
        ),
        daemon=True,
    )
    thread.start()
    return True


def _run(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_email: str,
    destinatarios: list[dict],
    assunto_tpl: str,
    corpo_tpl: str,
    utm_campaign: str,
    usar_testeira: bool,
    com_banner: bool,
    img_path: Optional[Path],
    pdf_path: Optional[Path],
    relatorio_file: Path,
) -> None:
    from src.email_layout import aplicar_layout_email
    from src.gemini_client import aplicar_placeholders
    from src.mailer import FilaEnvioInteligente, enviar_email_avancado, MAX_POR_HORA, DELAY_MIN_S, DELAY_MAX_S
    from src.utm_tracker import preparar_links_campanha
    import json

    total = len(destinatarios)
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _update({
        "running": True,
        "status": "em_andamento",
        "sucesso": 0,
        "erros": 0,
        "total": total,
        "processados": 0,
        "log": "Iniciando...",
        "last_successes": [],
        "last_errors": [],
        "destinatarios_planejados": destinatarios,
        "relatorio_em": agora,
        "relatorio_utm": utm_campaign,
        "motivo_interrupcao": "",
    })

    _salvar(relatorio_file)

    fila = FilaEnvioInteligente()
    sucesso = 0
    erros = 0

    def _tick_hora(rest: float) -> None:
        s = get_state()
        _set("log", f"Processados: {s['processados']}/{total} | OK: {s['sucesso']} | Erro: {s['erros']} | Aguardando janela horária: {int(rest)}s")

    def _tick_pausa(rest: float) -> None:
        s = get_state()
        _set("log", f"Processados: {s['processados']}/{total} | OK: {s['sucesso']} | Erro: {s['erros']} | Próximo envio em {int(rest)}s")

    for i, dest in enumerate(destinatarios):
        if _cancel_event.is_set():
            _update({"motivo_interrupcao": "Cancelado pelo usuário"})
            break

        email = dest["email"]
        cidade = dest["cidade"]
        categoria = dest.get("categoria", "")

        fila.aguardar_vaga_hora(on_tick=_tick_hora)

        if _cancel_event.is_set():
            _update({"motivo_interrupcao": "Cancelado pelo usuário"})
            break

        try:
            assunto, corpo = aplicar_placeholders(assunto_tpl, corpo_tpl, cidade, categoria)
            corpo = preparar_links_campanha(corpo, utm_campaign, cidade)
            html_body = aplicar_layout_email(corpo, com_testeira=usar_testeira, com_imagem=com_banner)

            enviar_email_avancado(
                smtp_host, smtp_port, smtp_user, smtp_password,
                from_email, email, assunto, html_body,
                imagem_inline=img_path, anexo_pdf=pdf_path,
            )
            fila.registrar_envio()
            sucesso += 1
            with _lock:
                _STATE["last_successes"].append({"email": email, "cidade": cidade})
        except Exception as exc:
            erros += 1
            with _lock:
                _STATE["last_errors"].append({"email": email, "erro": str(exc)})

        processados = i + 1
        _update({
            "processados": processados,
            "sucesso": sucesso,
            "erros": erros,
            "log": f"Processados: {processados}/{total} | OK: {sucesso} | Erro: {erros}",
            "ultimo_envio": {"sucesso": sucesso, "erros": erros, "total": total},
        })
        _salvar(relatorio_file)

        if i + 1 < total and not _cancel_event.is_set():
            fila.pausa_entre_envios(on_tick=_tick_pausa)

    _update({
        "running": False,
        "status": "finalizado",
        "sucesso": sucesso,
        "erros": erros,
        "processados": len(destinatarios) if not _cancel_event.is_set() else get_state()["processados"],
        "ultimo_envio": {"sucesso": sucesso, "erros": erros, "total": total},
        "log": f"Finalizado — {sucesso} enviados, {erros} erros.",
    })
    _salvar(relatorio_file)


def _salvar(relatorio_file: Path) -> None:
    import json
    with _lock:
        dados = {
            "ultimo_envio": _STATE.get("ultimo_envio", {"sucesso": _STATE["sucesso"], "erros": _STATE["erros"], "total": _STATE["total"]}),
            "last_successes": list(_STATE["last_successes"]),
            "last_errors": list(_STATE["last_errors"]),
            "relatorio_em": _STATE["relatorio_em"],
            "relatorio_utm": _STATE["relatorio_utm"],
            "envio_status": _STATE["status"],
            "processados": _STATE["processados"],
            "destinatarios_planejados": list(_STATE["destinatarios_planejados"]),
            "motivo_interrupcao": _STATE["motivo_interrupcao"],
        }
    relatorio_file.parent.mkdir(parents=True, exist_ok=True)
    relatorio_file.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
