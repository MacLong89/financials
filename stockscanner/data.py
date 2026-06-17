from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


def _cache_path(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / f"{symbol.upper()}.parquet"


def _is_fresh(path: Path, max_age_hours: float) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime < timedelta(hours=max_age_hours)


def fetch_history(
    symbol: str,
    *,
    cache_dir: Path,
    max_age_hours: float = 4,
    period: str = "2y",
) -> pd.DataFrame | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, symbol)

    if _is_fresh(path, max_age_hours):
        df = pd.read_parquet(path)
        if not df.empty:
            return df

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, auto_adjust=True)
    if df.empty:
        return None

    df = df.rename(columns=str.title)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.to_parquet(path)
    return df


def fetch_bulk_history(
    symbols: list[str],
    *,
    cache_dir: Path,
    max_age_hours: float = 4,
    period: str = "2y",
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        df = fetch_history(
            symbol,
            cache_dir=cache_dir,
            max_age_hours=max_age_hours,
            period=period,
        )
        if df is not None and len(df) >= 50:
            frames[symbol] = df
    return frames


def fetch_benchmark(
    symbol: str,
    *,
    cache_dir: Path,
    max_age_hours: float = 4,
) -> pd.DataFrame | None:
    return fetch_history(symbol, cache_dir=cache_dir, max_age_hours=max_age_hours, period="2y")
