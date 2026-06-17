from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stockscanner.config import ScannerConfig
from stockscanner.data import fetch_benchmark, fetch_bulk_history, fetch_history
from stockscanner.filters import build_base_candidate
from stockscanner.indicators import pct_return, rs_percentile
from stockscanner.plan import build_trade_plan
from stockscanner.regime import RegimeStatus, evaluate_regime
from stockscanner.scoring import score_candidate
from stockscanner.sectors import (
    build_sector_map,
    sector_momentum_returns,
    sector_percentile_ranks,
)
from stockscanner.signals.breakout import detect_breakout
from stockscanner.signals.empirical import build_signal_context, evaluate_empirical_signals
from stockscanner.signals.pullback import detect_pullback
from stockscanner.universe import get_universe


@dataclass
class HoldingReview:
    symbol: str
    rating: str
    confidence: float
    signal_count: int
    signals: str
    price: float
    above_200ma: bool
    rs_percentile: float
    ratio_52w: float
    reason: str
    error: str | None = None


def _parse_symbols(raw: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in raw:
        for part in line.replace(",", " ").split():
            sym = part.strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                out.append(sym)
    return out


def _rate_holding(
    *,
    signal_count: int,
    confidence: float,
    above_200ma: bool,
    regime: RegimeStatus,
    cfg: dict,
) -> tuple[str, str]:
    strong_sig = int(cfg.get("strong_hold_min_signals", 4))
    strong_conf = float(cfg.get("strong_hold_min_confidence", 72))
    hold_sig = int(cfg.get("hold_min_signals", 3))
    hold_conf = float(cfg.get("hold_min_confidence", 55))
    trim_sig = int(cfg.get("trim_max_signals", 2))
    exit_sig = int(cfg.get("exit_max_signals", 1))

    if signal_count >= strong_sig and confidence >= strong_conf and above_200ma:
        rating = "STRONG HOLD"
        reason = f"{signal_count}/6 signals · conf {confidence:.0f}% · above 200 MA"
    elif signal_count >= hold_sig and confidence >= hold_conf and above_200ma:
        rating = "HOLD"
        reason = f"{signal_count}/6 signals · above 200 MA · momentum intact"
    elif not above_200ma and signal_count <= trim_sig:
        rating = "EXIT"
        reason = "Below 200 MA with weak signal stack"
    elif not above_200ma:
        rating = "TRIM"
        reason = "Below 200 MA — trend broken"
    elif signal_count <= exit_sig and confidence < 45:
        rating = "EXIT"
        reason = f"Only {signal_count}/6 signals · very weak momentum"
    elif signal_count <= trim_sig:
        rating = "TRIM"
        reason = f"Only {signal_count}/6 signals · lagging peers"
    else:
        rating = "WATCH"
        reason = f"{signal_count}/6 signals · mixed — not a scanner leader"

    if not regime.is_risk_on and rating in {"STRONG HOLD", "HOLD"}:
        rating = "WATCH"
        reason = f"RISK-OFF market — tighten size. {reason}"

    return rating, reason


def run_portfolio_review(
    symbols: list[str],
    config: ScannerConfig | None = None,
    *,
    skip_pead: bool = True,
) -> dict[str, Any]:
    cfg = config or ScannerConfig.load()
    pf_cfg = cfg.section("portfolio")
    output_cfg = cfg.output
    cache_dir = Path(output_cfg.get("cache_dir", "data/cache"))
    if not cache_dir.is_absolute():
        cache_dir = Path(__file__).resolve().parent.parent.parent / cache_dir

    parsed = _parse_symbols(symbols)
    if not parsed:
        return {
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "holdings": [],
            "summary": {"strong_hold": 0, "hold": 0, "watch": 0, "trim": 0, "exit": 0},
            "regime": None,
            "message": "No symbols provided",
        }

    regime_cfg = cfg.regime
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

    universe = get_universe(
        cfg.universe.get("source", "sp500"),
        cfg.universe.get("custom_symbols", []),
    )
    all_symbols = sorted(set(universe) | set(parsed))
    history = fetch_bulk_history(
        all_symbols,
        cache_dir=cache_dir,
        max_age_hours=float(output_cfg.get("cache_max_age_hours", 4)),
    )

    for sym in parsed:
        if sym not in history:
            df = fetch_history(
                sym,
                cache_dir=cache_dir,
                max_age_hours=float(output_cfg.get("cache_max_age_hours", 4)),
            )
            if df is not None and len(df) >= 50:
                history[sym] = df

    signals_cfg = cfg.signals
    sector_map = build_sector_map(list(history.keys()), cache_dir)
    im_lb = int(signals_cfg.get("industry_momentum", {}).get("sector_lookback_days", 63))
    sector_rets = sector_momentum_returns(history, sector_map, im_lb)
    sector_rank = sector_percentile_ranks(sector_rets)
    ctx = build_signal_context(history, sector_map, sector_rank, signals_cfg)

    jt_returns = {
        sym: pct_return(history[sym]["Close"], int(signals_cfg.get("jt_momentum", {}).get("lookback_days", 126)))
        for sym in history
    }
    jt_returns = {k: v for k, v in jt_returns.items() if v is not None}
    jt_pct_map = rs_percentile(jt_returns)

    breakout_cfg = cfg.breakout
    pullback_cfg = cfg.pullback
    reviews: list[HoldingReview] = []

    for sym in parsed:
        df = history.get(sym)
        if df is None or len(df) < 200:
            reviews.append(
                HoldingReview(
                    symbol=sym,
                    rating="—",
                    confidence=0.0,
                    signal_count=0,
                    signals="-",
                    price=0.0,
                    above_200ma=False,
                    rs_percentile=0.0,
                    ratio_52w=0.0,
                    reason="Could not load price history",
                    error="no_data",
                )
            )
            continue

        empirical = evaluate_empirical_signals(
            sym,
            df,
            regime=regime,
            ctx=ctx,
            config=signals_cfg,
            pead_enabled_runtime=not skip_pead,
        )
        rs_pct = jt_pct_map.get(sym, 0.0)
        candidate = build_base_candidate(sym, df, rs_pct)
        if candidate is None:
            reviews.append(
                HoldingReview(
                    symbol=sym,
                    rating="—",
                    confidence=0.0,
                    signal_count=empirical.pass_count,
                    signals=empirical.codes,
                    price=float(df["Close"].iloc[-1]),
                    above_200ma=False,
                    rs_percentile=rs_pct,
                    ratio_52w=0.0,
                    reason="Insufficient indicator data",
                    error="indicators",
                )
            )
            continue

        candidate.signals = empirical
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
        candidate.setup_breakout = bo.triggered
        candidate.setup_pullback = pb.triggered
        candidate.score = score_candidate(candidate)
        plan = build_trade_plan(candidate)

        rating, reason = _rate_holding(
            signal_count=empirical.pass_count,
            confidence=plan.confidence_exact,
            above_200ma=candidate.above_200ma,
            regime=regime,
            cfg=pf_cfg,
        )
        reviews.append(
            HoldingReview(
                symbol=sym,
                rating=rating,
                confidence=plan.confidence_exact,
                signal_count=empirical.pass_count,
                signals=empirical.codes,
                price=candidate.last_close,
                above_200ma=candidate.above_200ma,
                rs_percentile=candidate.rs_percentile,
                ratio_52w=candidate.ratio_52w,
                reason=reason,
            )
        )

    order = {"EXIT": 0, "TRIM": 1, "WATCH": 2, "HOLD": 3, "STRONG HOLD": 4, "—": 5}
    reviews.sort(key=lambda r: (order.get(r.rating, 9), -r.confidence, r.symbol))

    summary = {"strong_hold": 0, "hold": 0, "watch": 0, "trim": 0, "exit": 0}
    for r in reviews:
        key = r.rating.lower().replace(" ", "_")
        if key in summary:
            summary[key] += 1

    return {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "regime": {
            "label": regime.label,
            "benchmark": regime.benchmark,
            "last_close": regime.last_close,
            "is_risk_on": regime.is_risk_on,
        },
        "holdings": [r.__dict__ for r in reviews],
        "summary": summary,
        "symbol_count": len(parsed),
    }
