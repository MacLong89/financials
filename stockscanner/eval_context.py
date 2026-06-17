from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from stockscanner.config import ScannerConfig
from stockscanner.filters import ScanCandidate, build_base_candidate, passes_liquidity
from stockscanner.indicators import pct_return, rs_percentile
from stockscanner.regime import RegimeStatus
from stockscanner.scoring import apply_tags, score_candidate
from stockscanner.sectors import (
    build_sector_map,
    sector_momentum_returns,
    sector_percentile_ranks,
)
from stockscanner.signals.breakout import detect_breakout
from stockscanner.signals.empirical import SignalContext, build_signal_context, evaluate_empirical_signals
from stockscanner.signals.pullback import detect_pullback


@dataclass(frozen=True)
class EvaluationContext:
    liquidity_symbols: list[str]
    sector_map: dict[str, str]
    signal_ctx: SignalContext
    jt_pct_map: dict[str, float]
    sector_rank: dict[str, float]


def build_evaluation_context(
    history: dict[str, pd.DataFrame],
    config: ScannerConfig,
    cache_dir: Path,
) -> EvaluationContext:
    filters = config.filters
    signals_cfg = config.signals

    liquidity_symbols = [
        sym
        for sym, df in history.items()
        if passes_liquidity(
            df,
            min_price=float(filters.get("min_price", 10)),
            min_avg_volume=float(filters.get("min_avg_volume", 500_000)),
            min_history_days=int(filters.get("min_history_days", 200)),
        )[0]
    ]

    sector_map = build_sector_map(liquidity_symbols, cache_dir)
    im_lb = int(signals_cfg.get("industry_momentum", {}).get("sector_lookback_days", 63))
    sector_rets = sector_momentum_returns(history, sector_map, im_lb)
    sector_rank = sector_percentile_ranks(sector_rets)
    signal_ctx = build_signal_context(history, sector_map, sector_rank, signals_cfg)

    jt_lb = int(signals_cfg.get("jt_momentum", {}).get("lookback_days", 126))
    jt_returns = {
        sym: pct_return(history[sym]["Close"], jt_lb)
        for sym in liquidity_symbols
        if sym in history
    }
    jt_returns = {k: v for k, v in jt_returns.items() if v is not None}
    jt_pct_map = rs_percentile(jt_returns)

    return EvaluationContext(
        liquidity_symbols=liquidity_symbols,
        sector_map=sector_map,
        signal_ctx=signal_ctx,
        jt_pct_map=jt_pct_map,
        sector_rank=sector_rank,
    )


def build_evaluated_candidate(
    symbol: str,
    df: pd.DataFrame,
    *,
    eval_ctx: EvaluationContext,
    regime: RegimeStatus,
    config: ScannerConfig,
    skip_pead: bool,
) -> ScanCandidate | None:
    signals_cfg = config.signals
    scoring_cfg = config.scoring
    breakout_cfg = config.breakout
    pullback_cfg = config.pullback

    empirical = evaluate_empirical_signals(
        symbol,
        df,
        regime=regime,
        ctx=eval_ctx.signal_ctx,
        config=signals_cfg,
        pead_enabled_runtime=not skip_pead,
    )
    rs_pct = eval_ctx.jt_pct_map.get(symbol, 0.0)
    candidate = build_base_candidate(symbol, df, rs_pct)
    if candidate is None:
        return None

    bo = detect_breakout(
        df,
        base_min_days=int(breakout_cfg.get("base_min_days", 10)),
        base_max_days=int(breakout_cfg.get("base_max_days", 20)),
        base_max_range_pct=float(breakout_cfg.get("base_max_range_pct", 0.08)),
        volume_multiplier=float(breakout_cfg.get("volume_multiplier", 1.5)),
    )
    pb = detect_pullback(
        df,
        ema_period=int(pullback_cfg.get("ema_period", 20)),
        touch_tolerance_pct=float(pullback_cfg.get("touch_tolerance_pct", 0.02)),
        require_green_candle=bool(pullback_cfg.get("require_green_candle", True)),
        volume_multiplier=float(pullback_cfg.get("volume_multiplier", 1.0)),
    )

    candidate.signals = empirical
    candidate.setup_breakout = bo.triggered
    candidate.setup_pullback = pb.triggered
    candidate.detail["sector"] = eval_ctx.sector_map.get(symbol)
    if bo.volume_ratio is not None:
        candidate.detail["volume_ratio"] = bo.volume_ratio
    elif pb.volume_ratio is not None:
        candidate.detail["volume_ratio"] = pb.volume_ratio

    candidate.score = score_candidate(
        candidate,
        weight_signal_count=float(scoring_cfg.get("weight_signal_count", 0.50)),
        weight_rs=float(scoring_cfg.get("weight_rs", 0.20)),
        weight_52w_ratio=float(scoring_cfg.get("weight_52w_ratio", 0.15)),
        weight_setup=float(scoring_cfg.get("weight_setup", 0.15)),
    )
    apply_tags(candidate)
    return candidate
