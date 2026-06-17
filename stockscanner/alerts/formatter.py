from __future__ import annotations

from datetime import datetime

from stockscanner.filters import ScanCandidate
from stockscanner.plan import build_trade_plans
from stockscanner.scanner import ScanResult


def candidate_key(candidate: ScanCandidate) -> str:
    return f"{candidate.symbol}:{candidate.signals.codes}"


def format_scan_alert(
    result: ScanResult,
    *,
    new_keys: set[str] | None = None,
    regime_changed: bool = False,
    stop_pct: float = 0.075,
    reward_risk: float = 2.0,
    max_plans: int = 10,
) -> tuple[str, str]:
    regime = result.regime
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    plans = build_trade_plans(
        result.candidates,
        stop_pct=stop_pct,
        reward_risk=reward_risk,
        max_rows=max_plans,
    )

    lines: list[str] = [
        f"Stock Scanner — {stamp}",
        f"Regime: {regime.label}",
        "",
    ]

    if regime_changed:
        lines.append("Regime changed since last alert.")
        lines.append("")

    if not regime.is_risk_on:
        lines.append("RISK-OFF — watch only.")
        lines.append("")

    if not plans:
        lines.append("No trade plans today.")
    else:
        lines.append("PRI | STOCK | SUMMARY | CONF | ENTRY | TARGET | STOP")
        for p in plans:
            lines.append(
                f"{marker}{p.priority} | {p.symbol} | {p.summary} | {p.confidence_exact:.1f}% | "
                f"${p.entry:.2f} | ${p.target:.2f} | ${p.stop:.2f}"
            )

    lines.extend(["", "-", "Not financial advice."])
    body = "\n".join(lines)

    if plans and new_keys:
        subject = f"Scanner: {len(new_keys)} new plan(s) — {regime.label}"
    elif plans:
        subject = f"Scanner: {len(plans)} plan(s) — {regime.label}"
    elif not regime.is_risk_on:
        subject = f"Scanner: RISK-OFF"
    else:
        subject = f"Scanner: no plans"

    return subject, body


def format_test_message() -> tuple[str, str]:
    subject = "Stock Scanner — test alert"
    body = (
        "Stock Scanner test alert\n\n"
        "If you received this, your notification channel is configured correctly.\n\n"
        "-\nResearch tool only. Not financial advice."
    )
    return subject, body
