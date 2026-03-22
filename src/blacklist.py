"""Cruzamento com blacklist.csv (e-mails e domínios)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Set, Tuple

import pandas as pd


def _norm_email(s: str) -> str:
    return (s or "").strip().lower()


def _norm_domain(s: str) -> str:
    d = (s or "").strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0].strip()
    if d.startswith("www."):
        d = d[4:]
    return d


def load_blacklist(path: Path) -> Tuple[Set[str], Set[str]]:
    """Retorna (emails_bloqueados, dominios_bloqueados)."""
    emails: Set[str] = set()
    dominios: Set[str] = set()
    if not path.exists():
        return emails, dominios

    df = pd.read_csv(path, dtype=str)
    df = df.fillna("")

    if "email" in df.columns:
        for v in df["email"]:
            v = _norm_email(str(v))
            if v and "@" in v:
                emails.add(v)

    if "domain" in df.columns:
        for v in df["domain"]:
            v = _norm_domain(str(v))
            if v:
                dominios.add(v)

    return emails, dominios


def is_blocked(email: str, site_domain: str, emails_bl: Set[str], doms_bl: Set[str]) -> bool:
    em = _norm_email(email)
    if em and em in emails_bl:
        return True

    dom = _norm_email(email).split("@", 1)[-1] if "@" in em else ""
    if dom and dom in doms_bl:
        return True

    sd = _norm_domain(site_domain)
    if sd and sd in doms_bl:
        return True

    return False


def apply_blacklist(
    df: pd.DataFrame,
    email_col: str,
    site_col: str | None,
    emails_bl: Set[str],
    dominios_bl: Set[str],
) -> pd.DataFrame:
    out = df.copy()
    bloqueado = []

    for _, row in out.iterrows():
        raw_email = row.get(email_col, "")
        raw_site = row.get(site_col, "") if site_col and site_col in out.columns else ""
        email = "" if pd.isna(raw_email) else str(raw_email)
        site = "" if pd.isna(raw_site) else str(raw_site)
        bloqueado.append(is_blocked(email, site, emails_bl, dominios_bl))

    out["blacklist_bloqueado"] = bloqueado
    out["status_blacklist"] = out["blacklist_bloqueado"].map(lambda x: "Bloqueado" if x else "Liberado")
    return out
