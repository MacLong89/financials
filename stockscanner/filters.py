from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from stockscanner.indicators import avg_volume, high_52w_distance_pct, ratio_52w_high
from stockscanner.signals.empirical import EmpiricalSignals
from stockscanner.signals.confirmers import ConfirmerSignals


@dataclass
class ScanCandidate:
    symbol: str
    last_close: float
    return_6m: float
    rs_percentile: float
    ratio_52w: float
    distance_52w_pct: float
    avg_volume_20d: float
    above_200ma: bool
    signals: EmpiricalSignals = field(default_factory=EmpiricalSignals)
    confirmers: ConfirmerSignals = field(default_factory=ConfirmerSignals)
    setup_breakout: bool = False
    setup_pullback: bool = False
    score: float = 0.0
    tags: list[str] = field(default_factory=list)
    detail: dict[str, str | float | None] = field(default_factory=dict)

    @property
    def signal_count(self) -> int:
        return self.signals.pass_count

    @property
    def confirmer_count(self) -> int:
        return self.confirmers.pass_count


def passes_liquidity(
    df: pd.DataFrame,
    *,
    min_price: float,
    min_avg_volume: float,
    min_history_days: int,
) -> tuple[bool, str]:
    if len(df) < min_history_days:
        return False, "insufficient history"
    last_close = float(df["Close"].iloc[-1])
    if last_close < min_price:
        return False, "price below minimum"
    vol = avg_volume(df["Volume"], 20)
    if vol is None or vol < min_avg_volume:
        return False, "volume below minimum"
    return True, "ok"


def build_base_candidate(
    symbol: str,
    df: pd.DataFrame,
    rs_pct: float,
) -> ScanCandidate | None:
    from stockscanner.indicators import above_ma, pct_return

    ret_6m = pct_return(df["Close"], 126)
    dist_52w = high_52w_distance_pct(df["Close"], df["High"])
    r52 = ratio_52w_high(df["Close"], df["High"])
    vol20 = avg_volume(df["Volume"], 20)
    is_above_200 = above_ma(df["Close"], 200)

    if ret_6m is None or dist_52w is None or r52 is None or vol20 is None or is_above_200 is None:
        return None

    return ScanCandidate(
        symbol=symbol,
        last_close=float(df["Close"].iloc[-1]),
        return_6m=ret_6m,
        rs_percentile=rs_pct,
        ratio_52w=r52,
        distance_52w_pct=dist_52w,
        avg_volume_20d=vol20,
        above_200ma=is_above_200,
    )
