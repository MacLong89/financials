from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from stockscanner.config import data_dir


WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
BUNDLED_SP500 = Path(__file__).resolve().parent / "data" / "sp500_symbols.json"

# ~90 liquid S&P leaders — used on Vercel to stay within serverless timeouts.
LIQUID_SP500: tuple[str, ...] = (
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AMD", "AMGN", "AMAT", "AMZN", "ANET",
    "AVGO", "AXP", "BA", "BAC", "BKNG", "BLK", "BRK-B", "BSX", "C", "CAT",
    "CDNS", "CEG", "CMCSA", "COP", "COST", "CRM", "CRWD", "CSCO", "CVX", "DASH",
    "DE", "DIS", "ETN", "GE", "GILD", "GOOG", "GOOGL", "GS", "HD", "HON",
    "IBM", "INTC", "INTU", "ISRG", "JNJ", "JPM", "KLAC", "KO", "LIN", "LLY",
    "LRCX", "LOW", "LULU", "MA", "MCD", "MDLZ", "META", "MRK", "MS", "MSFT",
    "MU", "NEE", "NFLX", "NOW", "NVDA", "ORCL", "PANW", "PEP", "PFE", "PG",
    "PLTR", "PM", "QCOM", "RTX", "SBUX", "SCHW", "SNPS", "SPGI", "SYK", "T",
    "TJX", "TMO", "TMUS", "TSLA", "TXN", "UNH", "UNP", "V", "VRTX", "VZ",
    "WDC", "WFC", "WMT", "XOM",
)


def _sp500_cache_path() -> Path:
    return data_dir() / "sp500_symbols.json"


def fetch_sp500_symbols() -> list[str]:
    cache = _sp500_cache_path()
    if cache.exists():
        mtime = datetime.fromtimestamp(cache.stat().st_mtime, tz=timezone.utc)
        if datetime.now(timezone.utc) - mtime < timedelta(hours=24):
            return json.loads(cache.read_text(encoding="utf-8"))

    if BUNDLED_SP500.exists():
        out = json.loads(BUNDLED_SP500.read_text(encoding="utf-8"))
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    headers = {"User-Agent": "stockscanner/0.1 (momentum swing scanner)"}
    response = requests.get(WIKI_SP500_URL, headers=headers, timeout=30)
    response.raise_for_status()
    tables = pd.read_html(io.StringIO(response.text))
    symbols = tables[0]["Symbol"].astype(str).str.replace(".", "-", regex=False)
    out = sorted(symbols.unique().tolist())
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out


def get_universe(source: str, custom_symbols: Iterable[str] | None = None) -> list[str]:
    if source == "custom":
        if not custom_symbols:
            raise ValueError("custom universe requires symbols in config.universe.custom_symbols")
        return sorted({s.strip().upper() for s in custom_symbols if s.strip()})
    if source == "sp500":
        return fetch_sp500_symbols()
    if source == "sp500_liquid":
        return list(LIQUID_SP500)
    raise ValueError(f"Unknown universe source: {source}")
