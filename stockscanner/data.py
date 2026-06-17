from __future__ import annotations

import os
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


def _cache_path(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / f"{symbol.upper()}.pkl"


def _read_cache(path: Path) -> pd.DataFrame:
    with path.open("rb") as f:
        return pickle.load(f)


def _write_cache(path: Path, df: pd.DataFrame) -> None:
    with path.open("wb") as f:
        pickle.dump(df, f, protocol=pickle.HIGHEST_PROTOCOL)


def _is_fresh(path: Path, max_age_hours: float) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime < timedelta(hours=max_age_hours)


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns=str.title)
    out.index = pd.to_datetime(out.index).tz_localize(None)
    return out


def _extract_ticker_frame(data: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    if data.empty:
        return None
    if isinstance(data.columns, pd.MultiIndex):
        tickers = data.columns.get_level_values(0)
        if symbol not in tickers:
            return None
        df = data[symbol].copy()
    else:
        df = data.copy()
    df = df.dropna(how="all")
    if df.empty:
        return None
    return _normalize_ohlcv(df)


def _store_history_frame(
    symbol: str,
    df: pd.DataFrame,
    *,
    cache_dir: Path,
) -> pd.DataFrame | None:
    if len(df) < 50:
        return None
    _write_cache(_cache_path(cache_dir, symbol), df)
    return df


def fetch_history(
    symbol: str,
    *,
    cache_dir: Path,
    max_age_hours: float = 4,
    period: str = "2y",
) -> pd.DataFrame | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    sym = symbol.upper()
    path = _cache_path(cache_dir, sym)

    if _is_fresh(path, max_age_hours):
        df = _read_cache(path)
        if not df.empty:
            return df

    ticker = yf.Ticker(sym)
    df = ticker.history(period=period, auto_adjust=True)
    if df.empty:
        return None

    return _store_history_frame(sym, _normalize_ohlcv(df), cache_dir=cache_dir)


def fetch_bulk_history(
    symbols: list[str],
    *,
    cache_dir: Path,
    max_age_hours: float = 4,
    period: str = "2y",
) -> dict[str, pd.DataFrame]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    need_fetch: list[str] = []

    for symbol in symbols:
        sym = symbol.upper()
        path = _cache_path(cache_dir, sym)
        if _is_fresh(path, max_age_hours):
            try:
                df = _read_cache(path)
                if not df.empty and len(df) >= 50:
                    frames[sym] = df
                    continue
            except Exception:
                pass
        need_fetch.append(sym)

    chunk_size = 35 if os.environ.get("VERCEL") else 60
    for i in range(0, len(need_fetch), chunk_size):
        chunk = need_fetch[i : i + chunk_size]
        if not chunk:
            continue
        try:
            data = yf.download(
                chunk,
                period=period,
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception:
            for sym in chunk:
                df = fetch_history(
                    sym,
                    cache_dir=cache_dir,
                    max_age_hours=max_age_hours,
                    period=period,
                )
                if df is not None:
                    frames[sym] = df
            continue

        if len(chunk) == 1:
            sym = chunk[0]
            df = _extract_ticker_frame(data, sym)
            if df is not None:
                stored = _store_history_frame(sym, df, cache_dir=cache_dir)
                if stored is not None:
                    frames[sym] = stored
            continue

        for sym in chunk:
            df = _extract_ticker_frame(data, sym)
            if df is None:
                continue
            stored = _store_history_frame(sym, df, cache_dir=cache_dir)
            if stored is not None:
                frames[sym] = stored

    return frames


def fetch_benchmark(
    symbol: str,
    *,
    cache_dir: Path,
    max_age_hours: float = 4,
) -> pd.DataFrame | None:
    return fetch_history(symbol, cache_dir=cache_dir, max_age_hours=max_age_hours, period="2y")
