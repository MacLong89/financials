from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from stockscanner.indicators import (
    atr,
    avg_volume,
    ma_slope,
    sma,
)


@dataclass
class ConfirmerSignals:
    rs_spy: bool = False
    vol_c: bool = False
    sqz: bool = False
    ma_s: bool = False

    @property
    def pass_count(self) -> int:
        return sum([self.rs_spy, self.vol_c, self.sqz, self.ma_s])

    @property
    def codes(self) -> str:
        parts = []
        if self.rs_spy:
            parts.append("RS")
        if self.vol_c:
            parts.append("VOL")
        if self.sqz:
            parts.append("SQZ")
        if self.ma_s:
            parts.append("MA")
        return "+".join(parts) or "-"


@dataclass
class ConfirmerContext:
    rs_spy_pct: dict[str, float] = field(default_factory=dict)


def evaluate_confirmers(
    symbol: str,
    df: pd.DataFrame,
    *,
    ctx: ConfirmerContext,
    config: dict,
) -> ConfirmerSignals:
    sig = ConfirmerSignals()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    rs_cfg = config.get("rs_spy", {})
    if rs_cfg.get("enabled", True):
        top_pct = float(rs_cfg.get("top_pct", 0.20))
        pct = ctx.rs_spy_pct.get(symbol)
        if pct is not None and pct >= 1.0 - top_pct:
            sig.rs_spy = True

    vol_cfg = config.get("vol_c", {})
    if vol_cfg.get("enabled", True):
        mult = float(vol_cfg.get("volume_multiplier", 1.2))
        range_top = float(vol_cfg.get("range_top_pct", 0.30))
        vol_avg = avg_volume(volume, 20)
        if vol_avg and len(df) >= 2:
            last = df.iloc[-1]
            prev_close = float(close.iloc[-2])
            last_close = float(last["Close"])
            last_vol = float(last["Volume"])
            up_day = last_close > prev_close
            pos = (last_close - float(last["Low"])) / max(float(last["High"]) - float(last["Low"]), 1e-9)
            if up_day and last_vol >= mult * vol_avg and pos >= range_top:
                sig.vol_c = True

    sqz_cfg = config.get("sqz", {})
    if sqz_cfg.get("enabled", True):
        max_ratio = float(sqz_cfg.get("atr_ratio_max", 0.75))
        atr_s = atr(high, low, close, 20)
        atr_l = atr(high, low, close, 60)
        if not atr_s.isna().iloc[-1] and not atr_l.isna().iloc[-1] and atr_l.iloc[-1] > 0:
            ratio = float(atr_s.iloc[-1] / atr_l.iloc[-1])
            if ratio <= max_ratio:
                sig.sqz = True

    ma_cfg = config.get("ma_s", {})
    if ma_cfg.get("enabled", True):
        fast_p = int(ma_cfg.get("fast_ma", 50))
        slow_p = int(ma_cfg.get("slow_ma", 200))
        slope_lb = int(ma_cfg.get("slope_lookback", 20))
        ma_fast = sma(close, fast_p)
        ma_slow = sma(close, slow_p)
        slope = ma_slope(close, slow_p, slope_lb)
        if (
            not ma_fast.isna().iloc[-1]
            and not ma_slow.isna().iloc[-1]
            and slope is not None
            and float(close.iloc[-1]) > float(ma_fast.iloc[-1]) > float(ma_slow.iloc[-1])
            and slope > 0
        ):
            sig.ma_s = True

    return sig


def build_confirmer_context(
    history: dict[str, pd.DataFrame],
    symbols: list[str],
    benchmark: str,
    config: dict,
) -> ConfirmerContext:
    from stockscanner.indicators import pct_return, rs_percentile

    ctx = ConfirmerContext()
    rs_cfg = config.get("rs_spy", {})
    if not rs_cfg.get("enabled", True):
        return ctx

    lb = int(rs_cfg.get("lookback_days", 63))
    bench_df = history.get(benchmark.upper())
    if bench_df is None:
        return ctx
    spy_ret = pct_return(bench_df["Close"], lb)
    if spy_ret is None:
        return ctx

    spreads: dict[str, float] = {}
    for sym in symbols:
        if sym not in history:
            continue
        ret = pct_return(history[sym]["Close"], lb)
        if ret is not None:
            spreads[sym] = ret - spy_ret
    ctx.rs_spy_pct = rs_percentile(spreads)
    return ctx
