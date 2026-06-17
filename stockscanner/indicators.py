from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def pct_return(series: pd.Series, lookback: int) -> float | None:
    if len(series) <= lookback:
        return None
    start = series.iloc[-lookback - 1]
    end = series.iloc[-1]
    if start <= 0:
        return None
    return float(end / start - 1.0)


def avg_volume(volume: pd.Series, period: int = 20) -> float | None:
    if len(volume) < period:
        return None
    return float(volume.tail(period).mean())


def pct_return_between(series: pd.Series, end_offset: int, lookback: int) -> float | None:
    """Return from (end_offset + lookback) ago to end_offset ago (exclusive of last end_offset days)."""
    if len(series) <= end_offset + lookback:
        return None
    start = series.iloc[-end_offset - lookback - 1]
    end = series.iloc[-end_offset - 1]
    if start <= 0:
        return None
    return float(end / start - 1.0)


def ratio_52w_high(close: pd.Series, high: pd.Series, window: int = 252) -> float | None:
    if len(close) < 20:
        return None
    window = min(window, len(high))
    peak = float(high.tail(window).max())
    last = float(close.iloc[-1])
    if peak <= 0:
        return None
    return float(last / peak)


def high_52w_distance_pct(close: pd.Series, high: pd.Series, window: int = 252) -> float | None:
    if len(close) < 20:
        return None
    window = min(window, len(high))
    peak = float(high.tail(window).max())
    last = float(close.iloc[-1])
    if peak <= 0:
        return None
    return float(1.0 - last / peak)


def above_ma(close: pd.Series, period: int) -> bool | None:
    ma = sma(close, period)
    if ma.isna().iloc[-1]:
        return None
    return bool(close.iloc[-1] > ma.iloc[-1])


def rs_percentile(returns: dict[str, float]) -> dict[str, float]:
    if not returns:
        return {}
    values = np.array(list(returns.values()), dtype=float)
    symbols = list(returns.keys())
    ranks = pd.Series(values).rank(pct=True)
    return {sym: float(ranks.iloc[i]) for i, sym in enumerate(symbols)}
