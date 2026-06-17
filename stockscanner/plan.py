from __future__ import annotations

from dataclasses import dataclass, replace

from stockscanner.filters import ScanCandidate


@dataclass(frozen=True)
class TradePlan:
    priority: int
    symbol: str
    summary: str
    confidence_exact: float
    entry: float
    target: float
    stop: float
    chart: str
    rs_percentile: float = 0.0
    scores: dict | None = None

    @property
    def confidence(self) -> int:
        return int(round(self.confidence_exact))

    @property
    def risk_pct(self) -> float:
        if self.entry <= 0:
            return 0.0
        return (self.entry - self.stop) / self.entry


def _chart_label(candidate: ScanCandidate) -> str:
    parts = []
    if candidate.setup_breakout:
        parts.append("BO")
    if candidate.setup_pullback:
        parts.append("PB")
    return "+".join(parts) if parts else "-"


def _summary(candidate: ScanCandidate) -> str:
    sig = candidate.signals.codes
    cfm = candidate.confirmers.codes
    chart = _chart_label(candidate)
    base = f"{candidate.signal_count}/6 {sig} · {candidate.confirmer_count}/4 {cfm}"
    if chart != "-":
        return f"{base} | {chart}"
    return base


def _confidence_exact(candidate: ScanCandidate) -> float:
    scores = candidate.detail.get("scores")
    if isinstance(scores, dict) and "total_score" in scores:
        return float(scores["total_score"])
    sig_pts = (candidate.signal_count / 6.0) * 35.0
    rs_pts = candidate.rs_percentile * 25.0
    gh_pts = candidate.ratio_52w * 15.0
    score_norm = max(0.0, min(1.0, (candidate.score - 55.0) / 25.0))
    comp_pts = score_norm * 20.0
    chart_pts = 10.0 if (candidate.setup_breakout or candidate.setup_pullback) else 0.0
    pead_pts = 5.0 if candidate.signals.pead else 0.0
    total = sig_pts + rs_pts + gh_pts + comp_pts + chart_pts + pead_pts
    return round(min(100.0, total), 2)


def build_trade_plan(
    candidate: ScanCandidate,
    *,
    stop_pct: float = 0.075,
    reward_risk: float = 2.0,
    priority: int = 0,
) -> TradePlan:
    entry = candidate.last_close
    stop = round(entry * (1.0 - stop_pct), 2)
    target = round(entry * (1.0 + stop_pct * reward_risk), 2)
    scores = candidate.detail.get("scores")
    return TradePlan(
        priority=priority,
        symbol=candidate.symbol,
        summary=_summary(candidate),
        confidence_exact=_confidence_exact(candidate),
        entry=round(entry, 2),
        target=target,
        stop=stop,
        chart=_chart_label(candidate),
        rs_percentile=candidate.rs_percentile,
        scores=dict(scores) if isinstance(scores, dict) else None,
    )


def build_trade_plans(
    candidates: list[ScanCandidate],
    *,
    stop_pct: float = 0.075,
    reward_risk: float = 2.0,
    min_confidence: float = 0,
    max_rows: int | None = None,
) -> list[TradePlan]:
    plans = [
        build_trade_plan(c, stop_pct=stop_pct, reward_risk=reward_risk)
        for c in candidates
    ]
    if min_confidence:
        plans = [p for p in plans if p.confidence_exact >= min_confidence]

    plans.sort(key=lambda p: (-p.confidence_exact, -p.rs_percentile, p.symbol))

    numbered: list[TradePlan] = []
    for i, p in enumerate(plans, start=1):
        numbered.append(replace(p, priority=i))

    if max_rows is not None:
        numbered = numbered[:max_rows]
    return numbered
