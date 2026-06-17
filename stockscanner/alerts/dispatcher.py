from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from stockscanner.alerts.discord import send_discord_message
from stockscanner.alerts.email_alert import send_email_message
from stockscanner.alerts.formatter import format_scan_alert, format_test_message
from stockscanner.alerts.state import (
    AlertState,
    diff_alert_state,
    update_alert_state,
)
from stockscanner.config import ROOT, ScannerConfig
from stockscanner.scanner import ScanResult


@dataclass
class AlertResult:
    sent: bool
    reason: str
    discord_ok: bool = False
    email_ok: bool = False
    errors: list[str] = field(default_factory=list)
    new_keys: set[str] = field(default_factory=set)
    regime_changed: bool = False


def _load_env() -> None:
    load_dotenv(ROOT / ".env")


def _state_path(config: ScannerConfig) -> Path:
    alerts_cfg = config.section("alerts")
    rel = Path(alerts_cfg.get("state_file", "data/alerts/last_state.json"))
    return rel if rel.is_absolute() else ROOT / rel


def _should_send(
    result: ScanResult,
    *,
    mode: str,
    on_risk_off: bool,
    new_keys: set[str],
    regime_changed: bool,
) -> tuple[bool, str]:
    has_matches = bool(result.candidates)
    risk_off = not result.regime.is_risk_on

    if mode == "all":
        if has_matches or (risk_off and on_risk_off) or regime_changed:
            return True, "mode=all"
        return False, "mode=all but nothing to report"

    if mode == "matches_only":
        if has_matches:
            return True, "matches found"
        return False, "no matches"

    # mode == "new" (default)
    if new_keys:
        return True, f"{len(new_keys)} new setup(s)"
    if regime_changed:
        return True, "regime changed"
    if risk_off and on_risk_off and regime_changed:
        return True, "risk-off regime change"
    return False, "no new setups or regime change"


def dispatch_alerts(
    result: ScanResult,
    config: ScannerConfig,
    *,
    force: bool = False,
    mode_override: str | None = None,
) -> AlertResult:
    _load_env()
    alerts_cfg = config.section("alerts")
    mode = mode_override or alerts_cfg.get("mode", "new")
    on_risk_off = bool(alerts_cfg.get("on_risk_off", True))
    persist_state = bool(alerts_cfg.get("persist_state", True))

    discord_enabled = bool(alerts_cfg.get("discord", {}).get("enabled", True))
    email_enabled = bool(alerts_cfg.get("email", {}).get("enabled", True))

    state_path = _state_path(config)
    previous = AlertState.load(state_path)
    new_keys, regime_changed = diff_alert_state(result, previous)

    if force:
        should_send, reason = True, "forced"
    else:
        should_send, reason = _should_send(
            result,
            mode=mode,
            on_risk_off=on_risk_off,
            new_keys=new_keys,
            regime_changed=regime_changed,
        )

    alert_result = AlertResult(
        sent=False,
        reason=reason,
        new_keys=new_keys,
        regime_changed=regime_changed,
    )

    if not should_send:
        return alert_result

    plan_cfg = config.plan
    output_cfg = config.output
    subject, body = format_scan_alert(
        result,
        new_keys=new_keys if mode == "new" else None,
        regime_changed=regime_changed,
        stop_pct=float(plan_cfg.get("stop_pct", 0.075)),
        reward_risk=float(plan_cfg.get("reward_risk", 2.0)),
        max_plans=int(output_cfg.get("plan_max_rows", 10)),
    )

    if discord_enabled:
        try:
            send_discord_message(body)
            alert_result.discord_ok = True
        except Exception as exc:  # noqa: BLE001 — surface channel errors to CLI
            alert_result.errors.append(f"Discord: {exc}")

    if email_enabled:
        try:
            send_email_message(subject, body)
            alert_result.email_ok = True
        except Exception as exc:  # noqa: BLE001
            alert_result.errors.append(f"Email: {exc}")

    alert_result.sent = alert_result.discord_ok or alert_result.email_ok

    if alert_result.sent and persist_state:
        update_alert_state(result, previous).save(state_path)

    return alert_result


def send_test_alerts(config: ScannerConfig) -> AlertResult:
    _load_env()
    alerts_cfg = config.section("alerts")
    discord_enabled = bool(alerts_cfg.get("discord", {}).get("enabled", True))
    email_enabled = bool(alerts_cfg.get("email", {}).get("enabled", True))

    subject, body = format_test_message()
    result = AlertResult(sent=False, reason="test")

    if discord_enabled:
        try:
            send_discord_message(body)
            result.discord_ok = True
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Discord: {exc}")

    if email_enabled:
        try:
            send_email_message(subject, body)
            result.email_ok = True
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Email: {exc}")

    result.sent = result.discord_ok or result.email_ok
    return result


def configured_channels(config: ScannerConfig) -> dict[str, bool]:
    _load_env()
    alerts_cfg = config.section("alerts")
    return {
        "discord": bool(alerts_cfg.get("discord", {}).get("enabled", True))
        and bool(os.environ.get("DISCORD_WEBHOOK_URL")),
        "email": bool(alerts_cfg.get("email", {}).get("enabled", True))
        and bool(os.environ.get("SMTP_HOST"))
        and bool(os.environ.get("SMTP_USER"))
        and bool(os.environ.get("SMTP_PASSWORD"))
        and bool(os.environ.get("SMTP_TO")),
    }
