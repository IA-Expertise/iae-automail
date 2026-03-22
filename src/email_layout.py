"""Layout HTML: testeira (faixa visual sem imagem) e opcional banner com foto (cid:header_img)."""

from __future__ import annotations


def html_testeira() -> str:
    """Faixa superior só com HTML/CSS — não depende de upload (evita erro de anexo de imagem)."""
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;border-collapse:collapse;margin:0 auto">'
        "<tr>"
        '<td style="background:linear-gradient(135deg,#0d47a1 0%,#1565c0 45%,#0277bd 100%);'
        'padding:22px 24px;text-align:center;border-radius:8px 8px 0 0">'
        '<div style="color:#fff;font-size:21px;font-weight:700;letter-spacing:0.3px">IAE Smart Guide</div>'
        '<div style="color:#e3f2fd;font-size:13px;margin-top:10px;line-height:1.45">'
        "Solução inteligente para secretarias de turismo e experiência do visitante"
        "</div>"
        "</td>"
        "</tr>"
        "</table>"
    )


def aplicar_layout_email(
    html_fragment: str,
    *,
    com_testeira: bool = True,
    com_imagem: bool = False,
) -> str:
    """
    Envolve o corpo em cartão responsivo.
    - com_testeira: faixa azul no topo (sem arquivo de imagem).
    - com_imagem: foto opcional abaixo da testeira (requer anexo inline no SMTP).
    """
    partes: list[str] = []
    if com_testeira:
        partes.append(html_testeira())
    if com_imagem:
        partes.append(
            '<div style="max-width:600px;margin:0 auto 0 auto">'
            '<img src="cid:header_img" alt="" width="560" '
            'style="max-width:100%;height:auto;border:0;display:block">'
            "</div>"
        )

    borda_topo = "border-radius:8px" if not com_testeira else "border-radius:0 0 8px 8px;border-top:none"
    bloco = (
        f'<div style="max-width:600px;margin:0 auto;font-family:Segoe UI,system-ui,Arial,sans-serif;'
        f"line-height:1.55;color:#212121;border:1px solid #e0e0e0;{borda_topo};"
        f'padding:22px 24px;background:#ffffff">{html_fragment}</div>'
    )
    partes.append(bloco)
    return "".join(partes)
