from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Any

import pandas as pd
import yfinance as yf

from stockscanner.config import ScannerConfig


@dataclass
class IntradayPlan:
    priority: int
    symbol: str
    setup: str
    bias: str
    summary: str
    confidence: float
    entry: float
    target: float
    stop: float
    vwap: float
    vs_vwap_pct: float
    gap_pct: float
    or_high: float | None = None
    or_low: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def _resolve_ticker(symbol: str, cfg: dict) -> str:
    aliases = cfg.get("ticker_aliases", {}) or {}
    return aliases.get(symbol, symbol)


def _fetch_5m(symbol: str, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or {}
    ticker = _resolve_ticker(symbol, cfg)
    df = yf.Ticker(ticker).history(period="5d", interval="5m", auto_adjust=True)
    if df.empty and ticker != symbol:
        df = yf.Ticker(symbol).history(period="5d", interval="5m", auto_adjust=True)
    if df.empty:
        return df
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df.rename(columns=str.title)


def _session_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    last_date = df.index[-1].date()
    return df[df.index.date == last_date].copy()


def _vwap(session: pd.DataFrame) -> pd.Series:
    tp = (session["High"] + session["Low"] + session["Close"]) / 3.0
    vol = session["Volume"].fillna(0)
    if vol.sum() <= 0:
        return tp.expanding().mean()
    vol = vol.replace(0, pd.NA)
    return (tp * vol).cumsum() / vol.cumsum()


def _prior_close(df: pd.DataFrame, session: pd.DataFrame) -> float | None:
    if session.empty:
        return None
    prior = df[df.index < session.index[0]]
    if prior.empty:
        return None
    return float(prior["Close"].iloc[-1])


def _opening_range(session: pd.DataFrame, orb_bars: int) -> tuple[float, float] | None:
    if len(session) < orb_bars + 1:
        return None
    orb = session.iloc[:orb_bars]
    return float(orb["High"].max()), float(orb["Low"].min())


def _scan_symbol(symbol: str, cfg: dict) -> IntradayPlan:
    empty = IntradayPlan(
        priority=0,
        symbol=symbol,
        setup="NO DATA",
        bias="—",
        summary="Could not load 5m bars (market closed or bad ticker)",
        confidence=0.0,
        entry=0.0,
        target=0.0,
        stop=0.0,
        vwap=0.0,
        vs_vwap_pct=0.0,
        gap_pct=0.0,
    )

    df = _fetch_5m(symbol, cfg)
    if df.empty or len(df) < 20:
        return empty

    session = _session_bars(df)
    if len(session) < 3:
        empty.summary = "Not enough intraday bars yet (wait for market open)"
        return empty

    orb_bars = int(cfg.get("orb_bars", 6))
    vol_mult = float(cfg.get("volume_multiplier", 1.2))
    stop_pct = float(cfg.get("stop_pct", 0.003))
    reward_risk = float(cfg.get("reward_risk", 2.0))
    min_orb_break_pct = float(cfg.get("min_orb_break_pct", 0.0005))

    vwap_series = _vwap(session)
    last = session.iloc[-1]
    prev = session.iloc[-2] if len(session) > 1 else last
    price = float(last["Close"])
    vwap_val = float(vwap_series.iloc[-1])
    if math.isnan(vwap_val):
        vwap_val = price
    vs_vwap = price / vwap_val - 1.0 if vwap_val else 0.0

    pclose = _prior_close(df, session)
    gap_pct = (float(session["Open"].iloc[0]) / pclose - 1.0) if pclose else 0.0

    or_levels = _opening_range(session, orb_bars)
    vol_avg = float(session["Volume"].iloc[:-1].tail(20).mean() or 0)
    vol_ratio = float(last["Volume"]) / vol_avg if vol_avg > 0 else 1.0

    setup = "NONE"
    bias = "NEUTRAL"
    confidence = 40.0

    vol_ok = vol_ratio >= vol_mult if vol_avg > 0 else True

    if or_levels and len(session) > orb_bars:
        or_high, or_low = or_levels
        after_orb = session.iloc[orb_bars:]
        if not after_orb.empty:
            if price > or_high * (1 + min_orb_break_pct) and vol_ok:
                setup = "ORB-L"
                bias = "LONG"
                confidence = 55 + min(25, vol_ratio * 8) + (10 if price > vwap_val else 0)
            elif price < or_low * (1 - min_orb_break_pct) and vol_ok:
                setup = "ORB-S"
                bias = "SHORT"
                confidence = 55 + min(25, vol_ratio * 8) + (10 if price < vwap_val else 0)

    # VWAP reclaim: prior bar below, current above, green candle
    if setup == "NONE":
        prev_vwap = float(vwap_series.iloc[-2])
        if float(prev["Close"]) < prev_vwap and price > vwap_val and price > float(last["Open"]):
            setup = "VWAP-L"
            bias = "LONG"
            confidence = 50 + min(20, vol_ratio * 6) + (10 if gap_pct > 0 else 0)
        elif float(prev["Close"]) > prev_vwap and price < vwap_val and price < float(last["Open"]):
            setup = "VWAP-S"
            bias = "SHORT"
            confidence = 50 + min(20, vol_ratio * 6) + (10 if gap_pct < 0 else 0)

    # Trend context only if no trigger
    if setup == "NONE":
        ema9 = session["Close"].ewm(span=9, adjust=False).mean().iloc[-1]
        if price > vwap_val and price > ema9:
            setup = "TREND-L"
            bias = "WATCH-L"
            confidence = 42 + min(15, vs_vwap * 500)
        elif price < vwap_val and price < ema9:
            setup = "TREND-S"
            bias = "WATCH-S"
            confidence = 42 + min(15, abs(vs_vwap) * 500)
        else:
            setup = "FLAT"
            bias = "NEUTRAL"
            confidence = 35 + min(10, abs(vs_vwap) * 200)

    if bias == "LONG" or bias == "WATCH-L":
        stop = round(min(price * (1 - stop_pct), or_levels[1] if or_levels else price * (1 - stop_pct)), 2)
        risk = price - stop
        target = round(price + risk * reward_risk, 2)
    elif bias == "SHORT" or bias == "WATCH-S":
        stop = round(max(price * (1 + stop_pct), or_levels[0] if or_levels else price * (1 + stop_pct)), 2)
        risk = stop - price
        target = round(price - risk * reward_risk, 2)
    else:
        stop = round(price * (1 - stop_pct), 2)
        target = round(price * (1 + stop_pct * reward_risk), 2)

    summary_parts = [
        f"vs VWAP {vs_vwap:+.2%}" if vs_vwap == vs_vwap else "vs VWAP n/a",
        f"gap {gap_pct:+.2%}",
    ]
    if vol_avg > 0:
        summary_parts.append(f"vol {vol_ratio:.1f}x")
    if or_levels:
        summary_parts.append(f"OR {or_levels[0]:.2f}/{or_levels[1]:.2f}")

    min_trade = float(cfg.get("min_trade_confidence", 65))
    is_trigger = setup.startswith("ORB") or setup.startswith("VWAP")
    tradeable = is_trigger and confidence >= min_trade

    return IntradayPlan(
        priority=0,
        symbol=symbol,
        setup=setup,
        bias=bias,
        summary=" · ".join(summary_parts),
        confidence=round(min(95.0, confidence), 1),
        entry=round(price, 2),
        target=target,
        stop=stop,
        vwap=round(vwap_val, 2),
        vs_vwap_pct=round(vs_vwap * 100, 3),
        gap_pct=round(gap_pct * 100, 3),
        or_high=or_levels[0] if or_levels else None,
        or_low=or_levels[1] if or_levels else None,
        detail={"volume_ratio": round(vol_ratio, 2), "tradeable": tradeable},
    )


def run_intraday_scan(config: ScannerConfig | None = None) -> dict[str, Any]:
    cfg = (config or ScannerConfig.load()).intraday
    symbols = cfg.get("symbols", ["SPY", "QQQ"])
    plans: list[IntradayPlan] = []

    for sym in symbols:
        try:
            plans.append(_scan_symbol(sym, cfg))
        except Exception:
            plans.append(
                IntradayPlan(
                    priority=0,
                    symbol=sym,
                    setup="ERROR",
                    bias="—",
                    summary="Scan failed",
                    confidence=0.0,
                    entry=0.0,
                    target=0.0,
                    stop=0.0,
                    vwap=0.0,
                    vs_vwap_pct=0.0,
                    gap_pct=0.0,
                )
            )

    plans.sort(key=lambda p: (-p.confidence, p.symbol))
    for i, p in enumerate(plans, start=1):
        p.priority = i

    return {
        "ran_at": datetime.now().isoformat(),
        "symbols": symbols,
        "min_trade_confidence": float(cfg.get("min_trade_confidence", 65)),
        "plans": [p.__dict__ for p in plans],
        "plan_count": len(plans),
        "disclaimer": "Intraday module for fun/small size only. Not financial advice.",
    }
