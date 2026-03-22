"""Layout HTML opcional com banner (imagem inline cid:header_img)."""

from __future__ import annotations


def aplicar_layout_email(html_fragment: str, com_banner: bool) -> str:
    """Envolve o corpo em container responsivo; opcionalmente adiciona slot para imagem inline."""
    bloco = f'<div style="max-width:600px;margin:0 auto;font-family:Segoe UI,system-ui,Arial,sans-serif;line-height:1.5;color:#222">{html_fragment}</div>'
    if not com_banner:
        return bloco
    banner = (
        '<div style="margin-bottom:20px">'
        '<img src="cid:header_img" alt="" width="560" '
        'style="max-width:100%;height:auto;border:0;display:block;border-radius:8px">'
        "</div>"
    )
    return banner + bloco
