"""Envio SMTP com fila: até 90 e-mails/hora e intervalo aleatório 45–120 s."""

from __future__ import annotations

import random
import re
import smtplib
import ssl
import time
from collections import deque
from email.message import EmailMessage
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
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    plain = plain_fallback or re.sub(r"<[^>]+>", "", html_body)
    plain = plain.replace("&nbsp;", " ").strip()
    msg.set_content(plain)
    msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=60) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.send_message(msg)
