from __future__ import annotations

from stockscanner.filters import ScanCandidate


def score_candidate(
    candidate: ScanCandidate,
    *,
    weight_signal_count: float = 0.50,
    weight_rs: float = 0.20,
    weight_52w_ratio: float = 0.15,
    weight_setup: float = 0.15,
) -> float:
    signal_score = (candidate.signal_count / 6.0) * 100.0
    rs_score = candidate.rs_percentile * 100.0
    ratio_score = candidate.ratio_52w * 100.0

    setup_score = 0.0
    if candidate.setup_breakout:
        setup_score = 100.0
    elif candidate.setup_pullback:
        setup_score = 85.0

    total = (
        signal_score * weight_signal_count
        + rs_score * weight_rs
        + ratio_score * weight_52w_ratio
        + setup_score * weight_setup
    )
    return round(total, 2)


def apply_tags(candidate: ScanCandidate) -> None:
    tags: list[str] = list(candidate.signals.codes.split("+")) if candidate.signals.codes != "-" else []
    if candidate.setup_breakout:
        tags.append("BO")
    if candidate.setup_pullback:
        tags.append("PB")
    if candidate.signal_count >= 5:
        tags.append("5+sig")
    elif candidate.signal_count >= 4:
        tags.append("4sig")
    candidate.tags = [t for t in tags if t]
