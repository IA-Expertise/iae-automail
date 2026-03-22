"""Geração de mensagem de campanha (assunto + corpo) com Gemini (Replit AI ou API Google)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from google import genai
from google.genai import types


def _get_client() -> genai.Client:
    base_url = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL")
    api_key = os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "Configure AI_INTEGRATIONS_GEMINI_API_KEY (Replit) ou GEMINI_API_KEY no ambiente."
        )
    if base_url:
        return genai.Client(
            api_key=api_key,
            http_options={
                "api_version": "",
                "base_url": base_url,
            },
        )
    return genai.Client(api_key=api_key)


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    data = json.loads(text)
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        raise ValueError("Resposta JSON inválida da IA.")
    return data


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


def gerar_mensagem_campanha(
    cidade_exemplo: str,
    categoria_exemplo: str,
    site_oficial: str,
    instrucoes_estrategia: str,
) -> dict[str, str]:
    """
    Uma única mensagem (assunto + corpo HTML) com placeholders {{CIDADE}} e {{CATEGORIA}}.
    `instrucoes_estrategia` contém produtos, serviços e tom desejados pelo usuário.
    """
    client = _get_client()

    instr = (instrucoes_estrategia or "").strip()
    if not instr:
        instr = (
            "Destaque o IAE Smart Guide como solução para gestão e promoção do destino. "
            "Tom profissional e respeitoso ao Secretário(a) de Turismo."
        )

    prompt = f"""Você é copywriter B2G para o produto IAE Smart Guide (guia inteligente para secretarias de turismo).

Contexto de exemplo (tom e segmento; no texto use placeholders, não nomes reais de cidades):
- Cidade exemplo: {cidade_exemplo}
- Categoria exemplo: {categoria_exemplo}
- Site oficial do município (referência): {site_oficial}

Instruções do usuário (estratégia, produtos, serviços, proposta de valor — siga com prioridade):
---
{instr}
---

Tarefa: gere UM único e-mail de prospecção para o Secretário(a) de Turismo, alinhado às instruções acima.

Regras obrigatórias:
- No ASSUNTO e no CORPO use os placeholders literais {{{{CIDADE}}}} e {{{{CATEGORIA}}}} para personalização em massa (não use nomes reais de cidades).
- Tom respeitoso, profissional, objetivo.
- Corpo em HTML simples: <p>, <strong>, <ul> quando fizer sentido.
- Inclua pelo menos um link para https://www.iaesmartguide.com.br (texto âncora ou URL visível).
- Evite emojis excessivos (no máximo 1 se fizer sentido).
- Saída APENAS em JSON válido: um objeto com chaves exatamente "assunto" e "corpo_html".

Responda somente o JSON, sem markdown."""

    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.75,
        ),
    )

    raw = (resp.text or "").strip()
    data = _parse_json_object(raw)
    assunto = str(data.get("assunto", "")).strip()
    corpo = str(data.get("corpo_html", "")).strip()
    if not assunto or not corpo:
        raise ValueError("A IA não retornou assunto e corpo válidos. Tente novamente.")

    return {"assunto": assunto, "corpo_html": corpo}
