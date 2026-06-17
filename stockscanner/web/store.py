from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from stockscanner.config import data_dir


SCANS_DIR = data_dir() / "scans"
LATEST_FILE = SCANS_DIR / "latest.json"
INTRADAY_LATEST = SCANS_DIR / "intraday_latest.json"
USER_DIR = data_dir() / "user"
PORTFOLIO_FILE = USER_DIR / "portfolio.json"
PORTFOLIO_REVIEW_FILE = USER_DIR / "portfolio_review.json"
SESSION_FILE = USER_DIR / "session.json"
_LEGACY_PORTFOLIO_FILE = data_dir() / "portfolio.json"


def _ensure_user_dir() -> None:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    if _LEGACY_PORTFOLIO_FILE.exists() and not PORTFOLIO_FILE.exists():
        _ensure_user_dir()
        shutil.copy2(_LEGACY_PORTFOLIO_FILE, PORTFOLIO_FILE)


def _ensure_dir() -> None:
    SCANS_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_scan(payload: dict[str, Any]) -> Path:
    _ensure_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SCANS_DIR / f"scan_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    LATEST_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def save_intraday(payload: dict[str, Any]) -> Path:
    _ensure_dir()
    INTRADAY_LATEST.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return INTRADAY_LATEST


def load_intraday() -> dict[str, Any] | None:
    if not INTRADAY_LATEST.exists():
        return None
    return json.loads(INTRADAY_LATEST.read_text(encoding="utf-8"))


def normalize_plans(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure priority + exact confidence; sort for display."""
    if not plans:
        return plans
    normalized = []
    for p in plans:
        row = dict(p)
        if "confidence_exact" not in row:
            row["confidence_exact"] = float(row.get("confidence", 0))
        normalized.append(row)
    normalized.sort(
        key=lambda p: (-float(p["confidence_exact"]), p.get("stock", "")),
    )
    for i, p in enumerate(normalized, start=1):
        p["priority"] = i
    return normalized


def load_latest() -> dict[str, Any] | None:
    if not LATEST_FILE.exists():
        return None
    data = json.loads(LATEST_FILE.read_text(encoding="utf-8"))
    if "plans" in data:
        data["plans"] = normalize_plans(data["plans"])
    return data


def list_history(limit: int = 20) -> list[dict[str, Any]]:
    _ensure_dir()
    files = sorted(SCANS_DIR.glob("scan_*.json"), reverse=True)
    items: list[dict[str, Any]] = []
    for path in files[:limit]:
        data = json.loads(path.read_text(encoding="utf-8"))
        items.append(
            {
                "id": path.stem,
                "ran_at": data.get("ran_at"),
                "match_count": data.get("match_count", 0),
                "plan_count": data.get("plan_count", 0),
                "regime": data.get("regime", {}).get("label"),
            }
        )
    return items


def load_scan(scan_id: str) -> dict[str, Any] | None:
    path = SCANS_DIR / f"{scan_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if "plans" in data:
        data["plans"] = normalize_plans(data["plans"])
    return data


def load_portfolio() -> dict[str, Any]:
    _ensure_user_dir()
    data = _read_json(PORTFOLIO_FILE, {"symbols": []})
    review = load_portfolio_review()
    if review:
        data["last_review"] = review
    return data


def save_portfolio(symbols: list[str]) -> dict[str, Any]:
    _ensure_user_dir()
    existing = _read_json(PORTFOLIO_FILE, {"symbols": []})
    payload = {
        "symbols": symbols,
        "updated_at": datetime.now().isoformat(),
        "fast_mode": existing.get("fast_mode", True),
    }
    _write_json(PORTFOLIO_FILE, payload)
    return payload


def save_portfolio_review(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_user_dir()
    _write_json(PORTFOLIO_REVIEW_FILE, payload)
    return payload


def load_portfolio_review() -> dict[str, Any] | None:
    _ensure_user_dir()
    if not PORTFOLIO_REVIEW_FILE.exists():
        return None
    return json.loads(PORTFOLIO_REVIEW_FILE.read_text(encoding="utf-8"))


def load_session() -> dict[str, Any]:
    _ensure_user_dir()
    session = _read_json(SESSION_FILE, {"active_tab": "swing", "fast_mode": True})
    portfolio = _read_json(PORTFOLIO_FILE, {"symbols": [], "fast_mode": True})
    if "fast_mode" in portfolio:
        session["fast_mode"] = portfolio["fast_mode"]
    return session


def save_session(
    *,
    active_tab: str | None = None,
    fast_mode: bool | None = None,
) -> dict[str, Any]:
    _ensure_user_dir()
    session = load_session()
    if active_tab is not None:
        session["active_tab"] = active_tab
    if fast_mode is not None:
        session["fast_mode"] = fast_mode
        portfolio = _read_json(PORTFOLIO_FILE, {"symbols": []})
        portfolio["fast_mode"] = fast_mode
        portfolio["updated_at"] = datetime.now().isoformat()
        _write_json(PORTFOLIO_FILE, portfolio)
    session["updated_at"] = datetime.now().isoformat()
    _write_json(SESSION_FILE, session)
    return session
