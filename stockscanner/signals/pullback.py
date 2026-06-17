from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from stockscanner.indicators import avg_volume, ema


@dataclass(frozen=True)
class PullbackSignal:
    triggered: bool
    ema20: float | None = None
    volume_ratio: float | None = None
    reason: str = ""


def detect_pullback(
    df: pd.DataFrame,
    *,
    ema_period: int = 20,
    touch_tolerance_pct: float = 0.02,
    require_green_candle: bool = True,
    volume_multiplier: float = 1.0,
) -> PullbackSignal:
    if len(df) < ema_period + 5:
        return PullbackSignal(False, reason="insufficient history")

    ema_series = ema(df["Close"], ema_period)
    ema_val = float(ema_series.iloc[-1])
    if ema_val <= 0:
        return PullbackSignal(False, reason="invalid ema")

    today = df.iloc[-1]
    low = float(today["Low"])
    close = float(today["Close"])
    open_ = float(today["Open"])

    touch_level = ema_val * (1.0 + touch_tolerance_pct)
    touched = low <= touch_level
    reclaimed = close > ema_val

    vol_avg = avg_volume(df["Volume"], 20)
    vol_ratio = float(today["Volume"]) / vol_avg if vol_avg else None
    volume_ok = vol_ratio is not None and vol_ratio >= volume_multiplier

    if require_green_candle and close <= open_:
        return PullbackSignal(
            False,
            ema20=ema_val,
            volume_ratio=vol_ratio,
            reason="not a green candle",
        )

    if not touched:
        return PullbackSignal(
            False,
            ema20=ema_val,
            volume_ratio=vol_ratio,
            reason="did not touch 20 EMA zone",
        )

    if not reclaimed:
        return PullbackSignal(
            False,
            ema20=ema_val,
            volume_ratio=vol_ratio,
            reason="close below 20 EMA",
        )

    if not volume_ok:
        return PullbackSignal(
            False,
            ema20=ema_val,
            volume_ratio=vol_ratio,
            reason="volume below threshold",
        )

    # Uptrend: 20 EMA above recent slope — simple check vs 5 days ago
    if ema_series.iloc[-6] >= ema_val:
        return PullbackSignal(
            False,
            ema20=ema_val,
            volume_ratio=vol_ratio,
            reason="20 EMA not rising",
        )

    return PullbackSignal(
        True,
        ema20=ema_val,
        volume_ratio=vol_ratio,
        reason="20 EMA pullback confirmed",
    )
