"""UTM únicos por cidade para links iaesmartguide.com.br."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def city_slug(cidade: str) -> str:
    s = unicodedata.normalize("NFKD", str(cidade or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9]+", "", s).lower()
    return s or "cidade"


_IAE_HOST_RE = re.compile(
    r"https?://(?:www\.)?iaesmartguide\.com\.br[^\s\"\'<>]*",
    re.IGNORECASE,
)


def _merge_utm(url: str, campaign: str, city_slug_val: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if "iaesmartguide.com.br" not in host:
        return url

    q = parse_qs(parsed.query, keep_blank_values=True)
    q["utm_source"] = ["email"]
    q["utm_medium"] = ["email"]
    q["utm_campaign"] = [campaign]
    q["utm_content"] = [city_slug_val]

    new_query = urlencode(q, doseq=True)
    return urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def inject_utm_in_html(html: str, campaign: str, cidade: str) -> str:
    """Substitui cada URL do site IAE no HTML por versão com UTM."""

    slug = city_slug(cidade)

    def repl(m: re.Match) -> str:
        return _merge_utm(m.group(0), campaign, slug)

    return _IAE_HOST_RE.sub(repl, html)


def inject_utm_in_text(text: str, campaign: str, cidade: str) -> str:
    slug = city_slug(cidade)

    def repl(m: re.Match) -> str:
        return _merge_utm(m.group(0), campaign, slug)

    return _IAE_HOST_RE.sub(repl, text)
