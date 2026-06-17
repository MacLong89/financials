from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf


@dataclass(frozen=True)
class QualityMetrics:
    score: float
    revenue_growth_yoy: float | None
    margin_trend: str
    label: str


def _cache_path(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / f"quality_{symbol.upper()}.pkl"


def _is_fresh(path: Path, max_age_hours: float) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime < timedelta(hours=max_age_hours)


def evaluate_quality(
    symbol: str,
    *,
    cache_dir: Path,
    max_age_hours: float = 24,
    config: dict | None = None,
) -> QualityMetrics:
    cfg = config or {}
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, symbol)

    if _is_fresh(path, max_age_hours):
        try:
            with path.open("rb") as f:
                return pickle.load(f)
        except Exception:
            pass

    sym = symbol.upper()
    ticker = yf.Ticker(sym)
    score = 50.0
    rev_growth: float | None = None
    margin_trend = "unknown"
    label = "Limited data"

    try:
        fin = ticker.financials
        if fin is not None and not fin.empty and "Total Revenue" in fin.index:
            rev = fin.loc["Total Revenue"].dropna().astype(float)
            if len(rev) >= 2:
                latest, prior = float(rev.iloc[0]), float(rev.iloc[1])
                if prior > 0:
                    rev_growth = (latest - prior) / prior
                    if rev_growth >= 0.15:
                        score += 25
                        label = "Strong growth"
                    elif rev_growth >= 0.05:
                        score += 15
                        label = "Steady growth"
                    elif rev_growth >= 0:
                        score += 5
                        label = "Flat revenue"
                    else:
                        score -= 20
                        label = "Revenue declining"

        if fin is not None and not fin.empty:
            margin_row = None
            for row_name in ("Gross Profit", "Operating Income", "Net Income"):
                if row_name in fin.index and "Total Revenue" in fin.index:
                    margin_row = row_name
                    break
            if margin_row:
                rev = fin.loc["Total Revenue"].dropna().astype(float)
                val = fin.loc[margin_row].dropna().astype(float)
                if len(rev) >= 2 and len(val) >= 2 and rev.iloc[1] > 0 and rev.iloc[0] > 0:
                    m0 = float(val.iloc[0] / rev.iloc[0])
                    m1 = float(val.iloc[1] / rev.iloc[1])
                    if m0 > m1 * 1.02:
                        margin_trend = "improving"
                        score += 15
                    elif m0 >= m1 * 0.98:
                        margin_trend = "stable"
                        score += 8
                    else:
                        margin_trend = "declining"
                        score -= 15
                        if label == "Limited data":
                            label = "Margins compressing"
    except Exception:
        pass

    score = max(0.0, min(100.0, score))
    if label == "Limited data" and rev_growth is not None:
        label = "Fundamentals OK" if score >= 55 else "Weak fundamentals"

    result = QualityMetrics(
        score=round(score, 1),
        revenue_growth_yoy=round(rev_growth, 4) if rev_growth is not None else None,
        margin_trend=margin_trend,
        label=label,
    )
    with path.open("wb") as f:
        pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
    return result
