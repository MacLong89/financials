from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class EarningsSignal:
    triggered: bool
    earnings_date: str | None = None
    gap_pct: float | None = None
    beat: bool | None = None
    hold_gap: bool | None = None
    reason: str = ""


def _parse_earnings_dates(ticker: yf.Ticker) -> pd.DatetimeIndex:
    try:
        dates = ticker.earnings_dates
    except Exception:
        return pd.DatetimeIndex([])
    if dates is None or dates.empty:
        return pd.DatetimeIndex([])
    idx = pd.to_datetime(dates.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return pd.DatetimeIndex(idx)


def _estimate_beat(ticker: yf.Ticker, earnings_day: pd.Timestamp) -> bool | None:
    try:
        dates = ticker.earnings_dates
    except Exception:
        return None
    if dates is None or dates.empty:
        return None

    row = None
    for idx in dates.index:
        ts = pd.Timestamp(idx)
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        if ts.normalize() == earnings_day.normalize():
            row = dates.loc[idx]
            break
    if row is None:
        return None

    estimate = row.get("EPS Estimate") if hasattr(row, "get") else None
    reported = row.get("Reported EPS") if hasattr(row, "get") else None
    if pd.isna(estimate) or pd.isna(reported):
        return None
    return bool(float(reported) > float(estimate))


def detect_earnings_gap_hold(
    symbol: str,
    df: pd.DataFrame,
    *,
    lookback_days: int = 5,
    min_gap_pct: float = 0.03,
    require_hold_gap: bool = True,
) -> EarningsSignal:
    if df.empty:
        return EarningsSignal(False, reason="no price history")

    ticker = yf.Ticker(symbol)
    earnings_dates = _parse_earnings_dates(ticker)
    if len(earnings_dates) == 0:
        return EarningsSignal(False, reason="no earnings dates")

    last_date = pd.Timestamp(df.index[-1]).normalize()
    cutoff = last_date - timedelta(days=lookback_days + 3)

    recent = [d for d in earnings_dates if cutoff <= d.normalize() <= last_date]
    if not recent:
        return EarningsSignal(False, reason="no recent earnings")

    earnings_day = max(recent).normalize()
    idx = pd.DatetimeIndex(df.index).normalize()
    pos = idx.get_indexer([earnings_day], method="bfill")
    if pos[0] < 1 or pos[0] >= len(df):
        return EarningsSignal(False, reason="earnings day not in history")

    event_i = int(pos[0])
    prior_close = float(df["Close"].iloc[event_i - 1])
    event_open = float(df["Open"].iloc[event_i])
    event_close = float(df["Close"].iloc[event_i])
    last_close = float(df["Close"].iloc[-1])

    if prior_close <= 0:
        return EarningsSignal(False, reason="invalid prior close")

    gap_pct = event_open / prior_close - 1.0
    if gap_pct < min_gap_pct:
        return EarningsSignal(
            False,
            earnings_date=str(earnings_day.date()),
            gap_pct=gap_pct,
            reason="gap too small",
        )

    hold_gap = last_close >= prior_close if require_hold_gap else True
    beat = _estimate_beat(ticker, earnings_day)

    if require_hold_gap and not hold_gap:
        return EarningsSignal(
            False,
            earnings_date=str(earnings_day.date()),
            gap_pct=gap_pct,
            beat=beat,
            hold_gap=False,
            reason="failed to hold gap",
        )

    if beat is False:
        return EarningsSignal(
            False,
            earnings_date=str(earnings_day.date()),
            gap_pct=gap_pct,
            beat=False,
            hold_gap=hold_gap,
            reason="missed EPS estimate",
        )

    return EarningsSignal(
        True,
        earnings_date=str(earnings_day.date()),
        gap_pct=gap_pct,
        beat=beat,
        hold_gap=hold_gap,
        reason="earnings gap-and-hold confirmed",
    )
