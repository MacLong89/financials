from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stockscanner.config import ScannerConfig, resolve_cache_dir
from stockscanner.data import fetch_benchmark, fetch_bulk_history
from stockscanner.filters import ScanCandidate, build_base_candidate, passes_liquidity
from stockscanner.indicators import pct_return, rs_percentile
from stockscanner.regime import RegimeStatus, evaluate_regime
from stockscanner.scoring import apply_tags, score_candidate
from stockscanner.sectors import (
    build_sector_map,
    sector_momentum_returns,
    sector_percentile_ranks,
)
from stockscanner.signals.breakout import detect_breakout
from stockscanner.signals.empirical import build_signal_context, evaluate_empirical_signals
from stockscanner.signals.pullback import detect_pullback
from stockscanner.universe import get_universe


@dataclass(frozen=True)
class ScanResult:
    regime: RegimeStatus
    candidates: list[ScanCandidate]
    universe_size: int
    screened_count: int
    sector_count: int
    min_signals_required: int


def run_scan(
    config: ScannerConfig,
    *,
    skip_pead: bool = False,
    config_path: Path | None = None,
) -> ScanResult:
    output_cfg = config.output
    cache_dir = resolve_cache_dir(config_path)

    symbols = get_universe(
        config.universe.get("source", "sp500"),
        config.universe.get("custom_symbols", []),
    )

    regime_cfg = config.regime
    benchmark = regime_cfg.get("benchmark", "SPY")
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
        ma_period=int(regime_cfg.get("ma_period", 200)),
        require_above=bool(regime_cfg.get("require_above", True)),
    )

    history = fetch_bulk_history(
        symbols,
        cache_dir=cache_dir,
        max_age_hours=float(output_cfg.get("cache_max_age_hours", 4)),
    )

    filters = config.filters
    min_price = float(filters.get("min_price", 10))
    min_avg_volume = float(filters.get("min_avg_volume", 500_000))
    min_history = int(filters.get("min_history_days", 200))

    signals_cfg = config.signals
    min_pass = int(signals_cfg.get("min_pass_count", 3))
    setups_cfg = config.setups
    require_setup = bool(setups_cfg.get("require_breakout_or_pullback", False))

    liquidity_symbols = [
        sym
        for sym, df in history.items()
        if passes_liquidity(
            df,
            min_price=min_price,
            min_avg_volume=min_avg_volume,
            min_history_days=min_history,
        )[0]
    ]

    sector_map = build_sector_map(liquidity_symbols, cache_dir)
    im_lb = int(signals_cfg.get("industry_momentum", {}).get("sector_lookback_days", 63))
    sector_rets = sector_momentum_returns(history, sector_map, im_lb)
    sector_rank = sector_percentile_ranks(sector_rets)
    ctx = build_signal_context(history, sector_map, sector_rank, signals_cfg)

    jt_returns = {
        sym: pct_return(history[sym]["Close"], int(signals_cfg.get("jt_momentum", {}).get("lookback_days", 126)))
        for sym in liquidity_symbols
        if sym in history
    }
    jt_returns = {k: v for k, v in jt_returns.items() if v is not None}
    jt_pct_map = rs_percentile(jt_returns)

    breakout_cfg = config.breakout
    pullback_cfg = config.pullback
    scoring_cfg = config.scoring

    candidates: list[ScanCandidate] = []
    screened = len(liquidity_symbols)

    for symbol in liquidity_symbols:
        df = history[symbol]
        empirical = evaluate_empirical_signals(
            symbol,
            df,
            regime=regime,
            ctx=ctx,
            config=signals_cfg,
            pead_enabled_runtime=not skip_pead,
        )

        if empirical.pass_count < min_pass:
            continue

        if require_setup:
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
            if not (bo.triggered or pb.triggered):
                continue
        else:
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

        rs_pct = jt_pct_map.get(symbol, 0.0)
        candidate = build_base_candidate(symbol, df, rs_pct)
        if candidate is None:
            continue

        candidate.signals = empirical
        candidate.setup_breakout = bo.triggered
        candidate.setup_pullback = pb.triggered
        candidate.detail["sector"] = sector_map.get(symbol)
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
        candidates.append(candidate)

    candidates.sort(
        key=lambda c: (-c.signal_count, -c.score, -c.rs_percentile, c.symbol),
    )
    top_n = int(output_cfg.get("top_n", 50))
    return ScanResult(
        regime=regime,
        candidates=candidates[:top_n],
        universe_size=len(symbols),
        screened_count=screened,
        sector_count=len(sector_rets),
        min_signals_required=min_pass,
    )
