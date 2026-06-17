from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"


def data_dir() -> Path:
    """Writable app data directory (uses /tmp on Vercel serverless)."""
    base = Path("/tmp/stockscanner/data") if os.environ.get("VERCEL") else ROOT / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def resolve_cache_dir(path: Path | None = None) -> Path:
    cfg = ScannerConfig.load(path)
    output_cfg = cfg.section("output")
    cache_dir = Path(output_cfg.get("cache_dir", "data/cache"))
    if cache_dir.is_absolute():
        resolved = cache_dir
    elif os.environ.get("VERCEL"):
        resolved = data_dir() / "cache"
    else:
        resolved = ROOT / cache_dir
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


@dataclass(frozen=True)
class ScannerConfig:
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: Path | None = None) -> ScannerConfig:
        config_path = path or DEFAULT_CONFIG_PATH
        with config_path.open(encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    def section(self, name: str) -> dict[str, Any]:
        return self.raw.get(name, {})

    @property
    def filters(self) -> dict[str, Any]:
        return self.section("filters")

    @property
    def regime(self) -> dict[str, Any]:
        return self.section("regime")

    @property
    def breakout(self) -> dict[str, Any]:
        return self.section("breakout")

    @property
    def pullback(self) -> dict[str, Any]:
        return self.section("pullback")

    @property
    def earnings(self) -> dict[str, Any]:
        return self.section("earnings")

    @property
    def scoring(self) -> dict[str, Any]:
        return self.section("scoring")

    @property
    def output(self) -> dict[str, Any]:
        return self.section("output")

    @property
    def universe(self) -> dict[str, Any]:
        return self.section("universe")

    @property
    def signals(self) -> dict[str, Any]:
        return self.section("signals")

    @property
    def setups(self) -> dict[str, Any]:
        return self.section("setups")

    @property
    def plan(self) -> dict[str, Any]:
        return self.section("plan")

    @property
    def intraday(self) -> dict[str, Any]:
        return self.section("intraday")

    @property
    def alerts(self) -> dict[str, Any]:
        return self.section("alerts")
