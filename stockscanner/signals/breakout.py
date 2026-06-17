from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from stockscanner.indicators import avg_volume, ema


@dataclass(frozen=True)
class BreakoutSignal:
    triggered: bool
    base_high: float | None = None
    base_range_pct: float | None = None
    volume_ratio: float | None = None
    reason: str = ""


def detect_breakout(
    df: pd.DataFrame,
    *,
    base_min_days: int = 10,
    base_max_days: int = 20,
    base_max_range_pct: float = 0.08,
    volume_multiplier: float = 1.5,
) -> BreakoutSignal:
    if len(df) < base_max_days + 5:
        return BreakoutSignal(False, reason="insufficient history")

    today = df.iloc[-1]
    vol_avg = avg_volume(df["Volume"], 20)
    if not vol_avg or vol_avg <= 0:
        return BreakoutSignal(False, reason="no volume data")

    vol_ratio = float(today["Volume"]) / vol_avg
    if vol_ratio < volume_multiplier:
        return BreakoutSignal(False, volume_ratio=vol_ratio, reason="volume below threshold")

    # Prior base window excludes today
    base = df.iloc[-(base_max_days + 1) : -1]
    if len(base) < base_min_days:
        return BreakoutSignal(False, reason="base too short")

    base_window = base.tail(base_max_days).head(max(base_min_days, len(base)))
    base_high = float(base_window["High"].max())
    base_low = float(base_window["Low"].min())
    mid = (base_high + base_low) / 2.0
    if mid <= 0:
        return BreakoutSignal(False, reason="invalid base")

    range_pct = (base_high - base_low) / mid
    if range_pct > base_max_range_pct:
        return BreakoutSignal(
            False,
            base_high=base_high,
            base_range_pct=range_pct,
            volume_ratio=vol_ratio,
            reason="base too wide",
        )

    base_vol = float(base_window["Volume"].mean())
    if base_vol > vol_avg * 1.05:
        return BreakoutSignal(
            False,
            base_high=base_high,
            base_range_pct=range_pct,
            volume_ratio=vol_ratio,
            reason="base volume not contracted",
        )

    if float(today["Close"]) <= base_high:
        return BreakoutSignal(
            False,
            base_high=base_high,
            base_range_pct=range_pct,
            volume_ratio=vol_ratio,
            reason="no close above base high",
        )

    return BreakoutSignal(
        True,
        base_high=base_high,
        base_range_pct=range_pct,
        volume_ratio=vol_ratio,
        reason="breakout confirmed",
    )
