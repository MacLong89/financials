from __future__ import annotations

from dataclasses import asdict, dataclass

from stockscanner.filters import ScanCandidate
from stockscanner.signals.quality import QualityMetrics


@dataclass(frozen=True)
class ScoreBreakdown:
    momentum_score: float
    event_trend_score: float
    confirmation_score: float
    chart_score: float
    quality_score: float | None
    total_score: float
    combined_score: float
    core_pass: int
    core_total: int
    confirmer_pass: int
    confirmer_total: int

    def to_dict(self) -> dict:
        return asdict(self)


def _family_pct(flags: list[bool]) -> float:
    if not flags:
        return 0.0
    return round(100.0 * sum(flags) / len(flags), 1)


def compute_score_breakdown(
    candidate: ScanCandidate,
    config: dict,
    *,
    quality: QualityMetrics | None = None,
) -> ScoreBreakdown:
    fam = config.get("score_families", {})
    w_mom = float(fam.get("momentum_weight", 0.40))
    w_evt = float(fam.get("event_trend_weight", 0.25))
    w_cfm = float(fam.get("confirmation_weight", 0.20))
    w_chart = float(fam.get("chart_weight", 0.15))
    w_qual = float(fam.get("quality_weight", 0.10))

    sig = candidate.signals
    cfm = candidate.confirmers

    momentum_flags = [sig.jt_momentum, sig.momentum_6_1, sig.gh_52w_high, sig.industry_momentum]
    event_flags = [sig.pead, sig.trend]
    confirmer_flags = [cfm.rs_spy, cfm.vol_c, cfm.sqz, cfm.ma_s]
    chart_flags = [candidate.setup_breakout, candidate.setup_pullback]

    momentum_score = _family_pct(momentum_flags)
    event_trend_score = _family_pct(event_flags)
    confirmation_score = _family_pct(confirmer_flags)
    chart_score = _family_pct(chart_flags)

    total_score = round(
        momentum_score * w_mom
        + event_trend_score * w_evt
        + confirmation_score * w_cfm
        + chart_score * w_chart,
        1,
    )

    quality_score = round(quality.score, 1) if quality else None
    if quality_score is not None:
        combined_score = round((1.0 - w_qual) * total_score + w_qual * quality_score, 1)
    else:
        combined_score = total_score

    return ScoreBreakdown(
        momentum_score=momentum_score,
        event_trend_score=event_trend_score,
        confirmation_score=confirmation_score,
        chart_score=chart_score,
        quality_score=quality_score,
        total_score=total_score,
        combined_score=combined_score,
        core_pass=candidate.signal_count,
        core_total=6,
        confirmer_pass=cfm.pass_count,
        confirmer_total=4,
    )
