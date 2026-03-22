"""Geração de 3 variações de copy (assunto + corpo) com Gemini."""

from __future__ import annotations

import json
import re
from typing import Any, List

import google.generativeai as genai

from .config import GEMINI_API_KEY, GEMINI_MODEL


def _parse_json_array(text: str) -> List[dict[str, Any]]:
    text = text.strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        text = m.group(0)
    return json.loads(text)


def aplicar_placeholders(assunto: str, corpo_html: str, cidade: str, categoria: str) -> tuple[str, str]:
    """Substitui {{CIDADE}} / {{CATEGORIA}} (e variantes {CIDADE}) pelos valores reais."""
    subj, body = assunto, corpo_html
    for a, b in (
        ("{{CIDADE}}", cidade),
        ("{{CATEGORIA}}", categoria),
        ("{CIDADE}", cidade),
        ("{CATEGORIA}", categoria),
    ):
        subj = subj.replace(a, b)
        body = body.replace(a, b)
    return subj, body


def gerar_variacoes_copy(
    cidade_exemplo: str,
    categoria_exemplo: str,
    site_oficial: str,
) -> List[dict[str, str]]:
    """
    Retorna lista de até 3 itens: {"assunto": str, "corpo_html": str}.
    Textos devem usar os placeholders {{CIDADE}} e {{CATEGORIA}} para personalização em massa.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY não configurada no .env")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt = f"""Você é copywriter B2G para o produto IAE Smart Guide (guia inteligente para secretarias de turismo).

Exemplo de contexto (use só para tom; no texto final use placeholders, não o nome real):
- Cidade exemplo: {cidade_exemplo}
- Categoria exemplo: {categoria_exemplo}
- Site oficial (referência): {site_oficial}

Tarefa: gere exatamente 3 variações de e-mail de prospecção para o Secretário(a) de Turismo.
Foco na dor: falta de dados para decisão, promoção do destino, atendimento ao visitante e modernização da gestão.

Regras obrigatórias:
- No ASSUNTO e no CORPO use os placeholders literais {{{{CIDADE}}}} e {{{{CATEGORIA}}}} onde houver personalização (não escreva nomes de cidades reais).
- Tom respeitoso, profissional, objetivo.
- Cada variação: assunto curto + corpo em HTML simples (parágrafos <p>, pode usar <strong>, listas <ul>).
- Inclua pelo menos um link para https://www.iaesmartguide.com.br (pode ser na home ou texto âncora).
- Não use emojis excessivos (no máximo 1 por e-mail se fizer sentido).
- Saída APENAS em JSON válido: array de 3 objetos com chaves exatamente: "assunto", "corpo_html".

Responda somente o JSON, sem markdown."""

    try:
        resp = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.85,
            ),
        )
        raw = (resp.text or "").strip()
    except Exception:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()

    data = _parse_json_array(raw)
    out: List[dict[str, str]] = []
    for item in data[:3]:
        if not isinstance(item, dict):
            continue
        assunto = str(item.get("assunto", "")).strip()
        corpo = str(item.get("corpo_html", "")).strip()
        if assunto and corpo:
            out.append({"assunto": assunto, "corpo_html": corpo})

    if len(out) < 3:
        raise ValueError("A IA não retornou 3 variações válidas. Tente novamente.")

    return out
