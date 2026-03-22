"""Listagem e caminhos seguros para planilhas salvas."""

from __future__ import annotations

from pathlib import Path

from src.config import DADOS_DIR

PLANILHAS_DIR = DADOS_DIR / "planilhas"


def garantir_pastas() -> None:
    PLANILHAS_DIR.mkdir(parents=True, exist_ok=True)


def listar_planilhas() -> list[Path]:
    """Planilhas em dados/planilhas + CSVs na raiz de /dados (exceto blacklist)."""
    garantir_pastas()
    paths: list[Path] = []
    paths.extend(PLANILHAS_DIR.glob("*.csv"))
    for p in DADOS_DIR.glob("*.csv"):
        if p.name.lower() == "blacklist.csv":
            continue
        if p not in paths:
            paths.append(p)
    return sorted(paths, key=lambda x: x.name.lower())


def nome_seguro(nome: str) -> str:
    nome = (nome or "").replace("..", "").strip()
    if not nome.lower().endswith(".csv"):
        nome = f"{nome}.csv"
    return nome
