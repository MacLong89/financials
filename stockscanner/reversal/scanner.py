from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from stockscanner.config import ScannerConfig, resolve_cache_dir
from stockscanner.data import fetch_benchmark, fetch_bulk_history
from stockscanner.eval_context import build_evaluation_context
from stockscanner.filters import passes_liquidity
from stockscanner.indicators import rsi, sma
from stockscanner.regime import evaluate_regime
from stockscanner.universe import get_universe


@dataclass
class ReversalSetup:
    symbol: str
    setup: str
    rsi: float
    bb_reclaim: bool
    above_200ma: bool
    confidence: float
    price: float
    summary: str


def _detect_bb_reclaim(close: pd.Series, period: int = 20) -> bool:
    if len(close) < period + 2:
        return False
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std()
    lower = mid - 2 * std
    prev_close = float(close.iloc[-2])
    last_close = float(close.iloc[-1])
    prev_lower = float(lower.iloc[-2])
    last_lower = float(lower.iloc[-1])
    return prev_close < prev_lower and last_close > last_lower


def run_reversal_scan(config: ScannerConfig | None = None) -> dict[str, Any]:
    cfg = config or ScannerConfig.load()
    rev_cfg = cfg.section("reversal")
    output_cfg = cfg.output
    cache_dir = resolve_cache_dir()

    symbols = get_universe(
        cfg.universe.get("source", "sp500"),
        cfg.universe.get("custom_symbols", []),
    )

    benchmark = cfg.regime.get("benchmark", "SPY")
    benchmark_df = fetch_benchmark(
        benchmark,
        cache_dir=cache_dir,
        max_age_hours=float(output_cfg.get("cache_max_age_hours", 4)),
    )
    if benchmark_df is None:
        raise RuntimeError(f"Could not load benchmark data for {benchmark}")

    regime = evaluate_regime(
        benchmark_df,
        benchmark=benchmark,
        ma_period=int(cfg.regime.get("ma_period", 200)),
        require_above=bool(cfg.regime.get("require_above", True)),
    )

    history = fetch_bulk_history(
        symbols,
        cache_dir=cache_dir,
        max_age_hours=float(output_cfg.get("cache_max_age_hours", 4)),
    )
    eval_ctx = build_evaluation_context(history, cfg, cache_dir)

    rsi_max = float(rev_cfg.get("rsi_max", 30))
    require_200 = bool(rev_cfg.get("require_above_200ma", True))
    require_risk_on = bool(rev_cfg.get("require_risk_on", True))
    min_conf = float(rev_cfg.get("min_confidence", 50))

    setups: list[ReversalSetup] = []

    for sym in eval_ctx.liquidity_symbols:
        df = history.get(sym)
        if df is None:
            continue

        rsi_val = rsi(df["Close"], int(rev_cfg.get("rsi_period", 14)))
        if rsi_val is None or rsi_val > rsi_max:
            continue

        from stockscanner.indicators import above_ma

        is_above = above_ma(df["Close"], 200)
        if require_200 and not is_above:
            continue
        if require_risk_on and not regime.is_risk_on:
            continue

        bb_reclaim = _detect_bb_reclaim(df["Close"])
        conf = 40.0
        if rsi_val <= 25:
            conf += 15
        if bb_reclaim:
            conf += 20
        if is_above:
            conf += 15
        if regime.is_risk_on:
            conf += 10
        conf = min(100.0, conf)

        if conf < min_conf:
            continue

        parts = [f"RSI {rsi_val:.0f}"]
        if bb_reclaim:
            parts.append("BB reclaim")
        if is_above:
            parts.append(">200MA")

        setups.append(
            ReversalSetup(
                symbol=sym,
                setup="REV-L" if bb_reclaim else "OVERSOLD",
                rsi=round(rsi_val, 1),
                bb_reclaim=bb_reclaim,
                above_200ma=bool(is_above),
                confidence=round(conf, 1),
                price=float(df["Close"].iloc[-1]),
                summary=" · ".join(parts),
            )
        )

    setups.sort(key=lambda s: (-s.confidence, s.rsi, s.symbol))

    return {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "regime": {
            "label": regime.label,
            "is_risk_on": regime.is_risk_on,
            "benchmark": regime.benchmark,
        },
        "setups": [s.__dict__ for s in setups[: int(rev_cfg.get("max_rows", 20))]],
        "stats": {"count": len(setups), "screened": len(eval_ctx.liquidity_symbols)},
    }
