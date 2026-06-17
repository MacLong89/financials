from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from stockscanner.indicators import above_ma, sma


@dataclass(frozen=True)
class RegimeStatus:
    benchmark: str
    ma_period: int
    last_close: float
    ma_value: float
    is_risk_on: bool
    distance_pct: float

    @property
    def label(self) -> str:
        return "RISK-ON" if self.is_risk_on else "RISK-OFF"


def evaluate_regime(
    benchmark_df: pd.DataFrame,
    *,
    benchmark: str = "SPY",
    ma_period: int = 200,
    require_above: bool = True,
) -> RegimeStatus:
    close = benchmark_df["Close"]
    ma = sma(close, ma_period)
    last_close = float(close.iloc[-1])
    ma_value = float(ma.iloc[-1])
    is_above = last_close > ma_value
    is_risk_on = is_above if require_above else True
    distance_pct = (last_close / ma_value - 1.0) if ma_value else 0.0
    return RegimeStatus(
        benchmark=benchmark,
        ma_period=ma_period,
        last_close=last_close,
        ma_value=ma_value,
        is_risk_on=is_risk_on,
        distance_pct=float(distance_pct),
    )
