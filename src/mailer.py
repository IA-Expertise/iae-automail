"""Envio SMTP com fila: até 90 e-mails/hora e intervalo aleatório 45–120 s."""

from __future__ import annotations

import random
import re
import smtplib
import ssl
import time
from collections import deque
from email.message import EmailMessage
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Deque, Optional

MAX_POR_HORA = 90
DELAY_MIN_S = 45
DELAY_MAX_S = 120


class FilaEnvioInteligente:
    def __init__(self) -> None:
        self._timestamps: Deque[float] = deque()

    def _limpar_antigos(self) -> None:
        agora = time.time()
        while self._timestamps and agora - self._timestamps[0] >= 3600:
            self._timestamps.popleft()

    def aguardar_vaga_hora(self) -> None:
        """Garante menos de 90 envios na janela móvel de 1 hora."""
        while True:
            self._limpar_antigos()
            if len(self._timestamps) < MAX_POR_HORA:
                return
            espera = 3600 - (time.time() - self._timestamps[0]) + 0.5
            time.sleep(max(1.0, espera))

    def registrar_envio(self) -> None:
        self._timestamps.append(time.time())

    def pausa_entre_envios(self) -> None:
        time.sleep(random.uniform(DELAY_MIN_S, DELAY_MAX_S))


def _plain_from_html(html_body: str, plain_fallback: Optional[str]) -> str:
    if plain_fallback:
        return plain_fallback
    plain = re.sub(r"<[^>]+>", "", html_body)
    return plain.replace("&nbsp;", " ").strip()


def enviar_email_html(
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    html_body: str,
    plain_fallback: Optional[str] = None,
) -> None:
    plain = _plain_from_html(html_body, plain_fallback)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(plain)
    msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=120) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.send_message(msg)


def _subtype_imagem(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext in ("jpg", "jpeg"):
        return "jpeg"
    if ext in ("png", "gif", "webp"):
        return ext
    return "png"


def enviar_email_avancado(
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    html_body: str,
    plain_fallback: Optional[str] = None,
    imagem_inline: Optional[Path] = None,
    anexo_pdf: Optional[Path] = None,
) -> None:
    """
    HTML + imagem inline (cid:header_img) + anexo PDF opcional.
    Se não houver imagem nem PDF, delega para enviar_email_html.
    """
    plain = _plain_from_html(html_body, plain_fallback)
    tem_img = imagem_inline is not None and imagem_inline.exists()
    tem_pdf = anexo_pdf is not None and anexo_pdf.exists()

    if not tem_img and not tem_pdf:
        enviar_email_html(
            host, port, user, password, from_addr, to_addr, subject, html_body, plain_fallback
        )
        return

    msg_root = MIMEMultipart("mixed")
    msg_root["Subject"] = subject
    msg_root["From"] = from_addr
    msg_root["To"] = to_addr

    if tem_img:
        msg_related = MIMEMultipart("related")
        msg_alt = MIMEMultipart("alternative")
        msg_alt.attach(MIMEText(plain, "plain", "utf-8"))
        msg_alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg_related.attach(msg_alt)
        with open(imagem_inline, "rb") as f:
            data = f.read()
        img = MIMEImage(data, _subtype=_subtype_imagem(imagem_inline))
        img.add_header("Content-ID", "<header_img>")
        img.add_header("Content-Disposition", "inline", filename=imagem_inline.name)
        msg_related.attach(img)
        msg_root.attach(msg_related)
    else:
        msg_alt = MIMEMultipart("alternative")
        msg_alt.attach(MIMEText(plain, "plain", "utf-8"))
        msg_alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg_root.attach(msg_alt)

    if tem_pdf:
        with open(anexo_pdf, "rb") as f:
            pdf_data = f.read()
        pdf_att = MIMEApplication(pdf_data, _subtype="pdf")
        pdf_att.add_header("Content-Disposition", "attachment", filename=anexo_pdf.name)
        msg_root.attach(pdf_att)

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=120) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.send_message(msg_root)
