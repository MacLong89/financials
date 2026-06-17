from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from stockscanner.alerts.formatter import candidate_key
from stockscanner.scanner import ScanResult


@dataclass
class AlertState:
    candidate_keys: set[str] = field(default_factory=set)
    regime: str | None = None

    @classmethod
    def load(cls, path: Path) -> AlertState:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            candidate_keys=set(data.get("candidate_keys", [])),
            regime=data.get("regime"),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "candidate_keys": sorted(self.candidate_keys),
            "regime": self.regime,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def diff_alert_state(
    result: ScanResult,
    previous: AlertState,
) -> tuple[set[str], bool]:
    current_keys = {candidate_key(c) for c in result.candidates}
    new_keys = current_keys - previous.candidate_keys
    regime_label = result.regime.label
    regime_changed = previous.regime is not None and previous.regime != regime_label
    return new_keys, regime_changed


def update_alert_state(result: ScanResult, previous: AlertState) -> AlertState:
    return AlertState(
        candidate_keys={candidate_key(c) for c in result.candidates},
        regime=result.regime.label,
    )
