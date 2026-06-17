"""Vercel entrypoint — exposes the FastAPI app at the project root."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stockscanner.web.app import app  # noqa: E402

__all__ = ["app"]
