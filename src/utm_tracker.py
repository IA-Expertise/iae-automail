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


_TEXTO_LINK_AMIGAVEL = "Visite o site do IAE Smart Guide"

_IAE_URL_COMPLETA = re.compile(
    r"https?://(?:www\.)?iaesmartguide\.com\.br[^\s<\"\'\)]*",
    re.IGNORECASE,
)


def ocultar_rastreio_para_leitura(html: str) -> str:
    """
    Mantém parâmetros UTM no atributo href (rastreio preservado).
    Substitui URLs visíveis no texto por texto amigável, para não expor ?utm_* ao leitor.
    """
    chunks = re.split(r"(<[^>]+>)", html)
    depth_link = 0
    out: list[str] = []
    for ch in chunks:
        if ch.startswith("<"):
            out.append(ch)
            if re.match(r"<a\s", ch, re.I) and not ch.rstrip().endswith("/>"):
                depth_link += 1
            elif re.match(r"</a\s*>", ch, re.I):
                depth_link = max(0, depth_link - 1)
            continue
        if depth_link > 0:
            ch = _IAE_URL_COMPLETA.sub(_TEXTO_LINK_AMIGAVEL, ch)
        else:
            ch = _IAE_URL_COMPLETA.sub(
                lambda m: (
                    f'<a href="{m.group(0)}" style="color:#1565c0;text-decoration:underline">'
                    f"{_TEXTO_LINK_AMIGAVEL}</a>"
                ),
                ch,
            )
        out.append(ch)
    return "".join(out)


def preparar_links_campanha(html: str, campaign: str, cidade: str) -> str:
    """UTM nos links + texto sem expor query string de rastreio."""
    return ocultar_rastreio_para_leitura(inject_utm_in_html(html, campaign, cidade))
