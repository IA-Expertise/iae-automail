"""Validação de domínio via DNS MX antes da campanha."""

from __future__ import annotations

import logging
from typing import Tuple

import dns.resolver
import dns.exception
import pandas as pd

logger = logging.getLogger(__name__)


def _domain_from_email(email: str) -> str:
    email = (email or "").strip().lower()
    if "@" not in email:
        return ""
    return email.split("@", 1)[1].strip()


def check_mx(domain: str) -> Tuple[bool, str]:
    """
    Retorna (ok, motivo). ok=True se existir pelo menos um registro MX
    ou se o domínio resolver por A/AAAA (alguns servidores usam apenas A).
    """
    domain = (domain or "").strip().lower().rstrip(".")
    if not domain:
        return False, "Domínio vazio"

    try:
        answers = dns.resolver.resolve(domain, "MX")
        if answers:
            return True, "MX OK"
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        pass
    except dns.exception.DNSException as e:
        return False, f"DNS: {e}"

    try:
        dns.resolver.resolve(domain, "A")
        return True, "A record (sem MX explícito)"
    except dns.exception.DNSException:
        pass

    try:
        dns.resolver.resolve(domain, "AAAA")
        return True, "AAAA record (sem MX explícito)"
    except dns.exception.DNSException:
        pass

    return False, "Sem MX/A/AAAA ou domínio inexistente"


def validate_emails_column(
    df: pd.DataFrame,
    email_col: str,
) -> pd.DataFrame:
    """
    Adiciona colunas _dominio, _mx_ok, _validacao_msg e status_higiene
    ('Válido' ou 'Inválido').
    """
    out = df.copy()
    if email_col not in out.columns:
        raise ValueError(f"Coluna de e-mail não encontrada: {email_col}")

    dominios = []
    mx_ok_list = []
    msgs = []
    status = []

    for _, row in out.iterrows():
        raw = row[email_col]
        if pd.isna(raw) or str(raw).strip() == "":
            dominios.append("")
            mx_ok_list.append(False)
            msgs.append("E-mail vazio")
            status.append("Inválido")
            continue

        email = str(raw).strip()
        dom = _domain_from_email(email)
        dominios.append(dom)
        ok, msg = check_mx(dom)
        mx_ok_list.append(ok)
        msgs.append(msg)
        status.append("Válido" if ok else "Inválido")

    out["_dominio"] = dominios
    out["_mx_ok"] = mx_ok_list
    out["_validacao_msg"] = msgs
    out["status_higiene"] = status
    return out
