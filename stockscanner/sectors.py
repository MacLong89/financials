from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


def _sector_cache_path(cache_dir: Path, symbol: str) -> Path:
    d = cache_dir / "sectors"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{symbol.upper()}.json"


def _is_fresh(path: Path, max_age_hours: float = 168) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime < timedelta(hours=max_age_hours)


def get_stock_sector(symbol: str, cache_dir: Path, max_age_hours: float = 168) -> str | None:
    path = _sector_cache_path(cache_dir, symbol)
    if _is_fresh(path, max_age_hours):
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("sector")

    try:
        info = yf.Ticker(symbol).info
        sector = info.get("sector")
    except Exception:
        sector = None

    if sector:
        path.write_text(json.dumps({"sector": sector}), encoding="utf-8")
    return sector


def build_sector_map(
    symbols: list[str],
    cache_dir: Path,
    max_age_hours: float = 168,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for symbol in symbols:
        sector = get_stock_sector(symbol, cache_dir, max_age_hours)
        if sector:
            mapping[symbol] = sector
    return mapping


def sector_momentum_returns(
    history: dict[str, pd.DataFrame],
    sector_map: dict[str, str],
    lookback: int,
) -> dict[str, float]:
    """Average lookback return per sector."""
    from stockscanner.indicators import pct_return

    sector_rets: dict[str, list[float]] = {}
    for symbol, df in history.items():
        sector = sector_map.get(symbol)
        if not sector:
            continue
        ret = pct_return(df["Close"], lookback)
        if ret is None:
            continue
        sector_rets.setdefault(sector, []).append(ret)

    return {s: float(sum(v) / len(v)) for s, v in sector_rets.items() if v}


def sector_percentile_ranks(sector_returns: dict[str, float]) -> dict[str, float]:
    if not sector_returns:
        return {}
    import pandas as pd

    series = pd.Series(sector_returns)
    ranks = series.rank(pct=True)
    return {k: float(ranks[k]) for k in sector_returns}
