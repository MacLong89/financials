from __future__ import annotations

import io
from typing import Iterable

import pandas as pd
import requests


WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def fetch_sp500_symbols() -> list[str]:
    headers = {"User-Agent": "stockscanner/0.1 (momentum swing scanner)"}
    response = requests.get(WIKI_SP500_URL, headers=headers, timeout=30)
    response.raise_for_status()
    tables = pd.read_html(io.StringIO(response.text))
    symbols = tables[0]["Symbol"].astype(str).str.replace(".", "-", regex=False)
    return sorted(symbols.unique().tolist())


def get_universe(source: str, custom_symbols: Iterable[str] | None = None) -> list[str]:
    if source == "custom":
        if not custom_symbols:
            raise ValueError("custom universe requires symbols in config.universe.custom_symbols")
        return sorted({s.strip().upper() for s in custom_symbols if s.strip()})
    if source == "sp500":
        return fetch_sp500_symbols()
    raise ValueError(f"Unknown universe source: {source}")
