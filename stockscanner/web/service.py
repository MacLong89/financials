from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from stockscanner.alerts.dispatcher import configured_channels, dispatch_alerts
from stockscanner.config import ScannerConfig
from stockscanner.plan import build_trade_plans
from stockscanner.scanner import run_scan
from stockscanner.web.store import (
    load_intraday,
    normalize_plans,
    save_intraday,
    save_portfolio,
    save_portfolio_review,
    save_scan,
)
from stockscanner.intraday.scanner import run_intraday_scan
from stockscanner.portfolio.review import run_portfolio_review

_intraday_lock = threading.Lock()
_intraday_scanning = False


def run_intraday_and_store(config: ScannerConfig | None = None) -> dict[str, Any]:
    global _intraday_scanning
    with _intraday_lock:
        if _intraday_scanning:
            return {"status": "busy"}
        _intraday_scanning = True
    try:
        payload = run_intraday_scan(config)
        payload["status"] = "ok"
        save_intraday(payload)
        return payload
    finally:
        with _intraday_lock:
            _intraday_scanning = False


def is_intraday_scanning() -> bool:
    return _intraday_scanning


_scan_lock = threading.Lock()
_scanning = False


def _plan_to_dict(p) -> dict[str, Any]:
    return {
        "priority": p.priority,
        "stock": p.symbol,
        "summary": p.summary,
        "confidence": p.confidence_exact,
        "confidence_exact": p.confidence_exact,
        "entry": p.entry,
        "target": p.target,
        "stop": p.stop,
        "chart": p.chart,
    }


def _result_to_payload(
    result,
    config: ScannerConfig,
    *,
    fast: bool,
    source: str,
) -> dict[str, Any]:
    plan_cfg = config.plan
    output_cfg = config.output
    plans = build_trade_plans(
        result.candidates,
        stop_pct=float(plan_cfg.get("stop_pct", 0.075)),
        reward_risk=float(plan_cfg.get("reward_risk", 2.0)),
        min_confidence=int(plan_cfg.get("min_confidence", 0)),
        max_rows=None,
    )
    display_plans = build_trade_plans(
        result.candidates,
        stop_pct=float(plan_cfg.get("stop_pct", 0.075)),
        reward_risk=float(plan_cfg.get("reward_risk", 2.0)),
        min_confidence=int(plan_cfg.get("min_confidence", 0)),
        max_rows=int(output_cfg.get("plan_max_rows", 15)),
    )

    regime = result.regime
    return {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "fast": fast,
        "regime": {
            "label": regime.label,
            "benchmark": regime.benchmark,
            "last_close": regime.last_close,
            "ma_value": regime.ma_value,
            "ma_period": regime.ma_period,
            "distance_pct": regime.distance_pct,
            "is_risk_on": regime.is_risk_on,
        },
        "stats": {
            "universe_size": result.universe_size,
            "screened_count": result.screened_count,
            "sector_count": result.sector_count,
            "min_signals_required": result.min_signals_required,
            "match_count": len(result.candidates),
            "plan_count": len(plans),
        },
        "plan_rules": {
            "stop_pct": float(plan_cfg.get("stop_pct", 0.075)),
            "reward_risk": float(plan_cfg.get("reward_risk", 2.0)),
            "min_confidence": int(plan_cfg.get("min_confidence", 0)),
        },
        "plans": normalize_plans([_plan_to_dict(p) for p in display_plans]),
        "all_plans": normalize_plans([_plan_to_dict(p) for p in plans]),
    }


def run_and_store(
    config: ScannerConfig | None = None,
    *,
    fast: bool = True,
    source: str = "manual",
    send_alert: bool = False,
) -> dict[str, Any]:
    global _scanning
    cfg = config or ScannerConfig.load()

    with _scan_lock:
        if _scanning:
            return {"status": "busy", "message": "Scan already in progress"}
        _scanning = True

    try:
        result = run_scan(cfg, skip_pead=fast)
        payload = _result_to_payload(result, cfg, fast=fast, source=source)
        save_scan(payload)

        if send_alert and any(configured_channels(cfg).values()):
            dispatch_alerts(result, cfg)

        payload["status"] = "ok"
        return payload
    finally:
        with _scan_lock:
            _scanning = False


def is_scanning() -> bool:
    return _scanning


def review_portfolio(
    symbols: list[str],
    config: ScannerConfig | None = None,
    *,
    fast: bool = True,
) -> dict[str, Any]:
    cfg = config or ScannerConfig.load()
    payload = run_portfolio_review(symbols, cfg, skip_pead=fast)
    payload["status"] = "ok"
    save_portfolio(symbols)
    save_portfolio_review(payload)
    return payload
