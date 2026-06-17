from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stockscanner.config import ScannerConfig, resolve_cache_dir
from stockscanner.data import fetch_benchmark, fetch_bulk_history
from stockscanner.eval_context import build_evaluated_candidate, build_evaluation_context
from stockscanner.filters import ScanCandidate
from stockscanner.regime import RegimeStatus, evaluate_regime
from stockscanner.universe import get_universe


@dataclass(frozen=True)
class ScanResult:
    regime: RegimeStatus
    candidates: list[ScanCandidate]
    universe_size: int
    screened_count: int
    sector_count: int
    min_signals_required: int
    strict_match_count: int = 0


def _total_score(candidate: ScanCandidate) -> float:
    scores = candidate.detail.get("scores")
    if isinstance(scores, dict) and scores.get("total_score") is not None:
        return float(scores["total_score"])
    return float(candidate.score)


def _rank_candidates(candidates: list[ScanCandidate]) -> list[ScanCandidate]:
    return sorted(
        candidates,
        key=lambda c: (
            -_total_score(c),
            -c.signal_count,
            -c.score,
            -c.rs_percentile,
            c.symbol,
        ),
    )


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

    signals_cfg = config.signals
    min_pass = int(signals_cfg.get("min_pass_count", 3))
    setups_cfg = config.setups
    require_setup = bool(setups_cfg.get("require_breakout_or_pullback", False))

    eval_ctx = build_evaluation_context(history, config, cache_dir)
    strict: list[ScanCandidate] = []
    all_evaluated: list[ScanCandidate] = []

    for symbol in eval_ctx.liquidity_symbols:
        df = history[symbol]
        candidate = build_evaluated_candidate(
            symbol,
            df,
            eval_ctx=eval_ctx,
            regime=regime,
            config=config,
            skip_pead=skip_pead,
        )
        if candidate is None:
            continue
        all_evaluated.append(candidate)
        if candidate.signal_count < min_pass:
            continue
        if require_setup and not (candidate.setup_breakout or candidate.setup_pullback):
            continue
        strict.append(candidate)

    strict = _rank_candidates(strict)
    strict_match_count = len(strict)

    fallback_min = int(output_cfg.get("fallback_min_rows", 10))
    candidates = list(strict)
    if len(candidates) < fallback_min:
        strict_symbols = {c.symbol for c in candidates}
        pool = [c for c in _rank_candidates(all_evaluated) if c.symbol not in strict_symbols]
        for c in pool[: max(0, fallback_min - len(candidates))]:
            c.detail["fallback"] = True
            candidates.append(c)

    top_n = int(output_cfg.get("top_n", 50))
    return ScanResult(
        regime=regime,
        candidates=candidates[:top_n],
        universe_size=len(symbols),
        screened_count=len(eval_ctx.liquidity_symbols),
        sector_count=len(eval_ctx.sector_rank),
        min_signals_required=min_pass,
        strict_match_count=strict_match_count,
    )
