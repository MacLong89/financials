from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from stockscanner.config import ROOT, ScannerConfig
from stockscanner.web import service, store

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
PUBLIC_STATIC_DIR = ROOT / "public" / "static"

app = FastAPI(title="Stock Scanner", version="1.0.0")
_config = ScannerConfig.load()


class ScanRequest(BaseModel):
    fast: bool = True
    alert: bool = False


class PortfolioRequest(BaseModel):
    symbols: list[str]
    fast: bool = True


class PortfolioSaveRequest(BaseModel):
    symbols: list[str]


class SessionRequest(BaseModel):
    active_tab: str | None = None
    fast_mode: bool | None = None


@app.on_event("startup")
def on_startup() -> None:
    if os.environ.get("VERCEL"):
        return
    web_cfg = _config.section("web")
    if web_cfg.get("auto_schedule", True):
        from stockscanner.web.scheduler import start_scheduler

        start_scheduler(_config)
        logger.info("Scheduler started")


@app.on_event("shutdown")
def on_shutdown() -> None:
    if os.environ.get("VERCEL"):
        return
    from stockscanner.web.scheduler import stop_scheduler

    stop_scheduler()


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok", "platform": "vercel" if os.environ.get("VERCEL") else "local"}


@app.get("/")
def index() -> FileResponse:
    for base in (STATIC_DIR, PUBLIC_STATIC_DIR):
        path = base / "index.html"
        if path.exists():
            return FileResponse(path)
    raise HTTPException(status_code=500, detail="index.html not found")


@app.get("/api/status")
def api_status() -> dict:
    latest = store.load_latest()
    intraday = store.load_intraday()
    portfolio = store.load_portfolio()
    session = store.load_session()
    web_cfg = _config.section("web")
    return {
        "scanning": service.is_scanning(),
        "intraday_scanning": service.is_intraday_scanning(),
        "reversal_scanning": service.is_reversal_scanning(),
        "latest": latest,
        "intraday": intraday,
        "reversal": store.load_reversal(),
        "portfolio": portfolio,
        "session": session,
        "schedule": {
            "enabled": web_cfg.get("auto_schedule", True),
            "time": f"{web_cfg.get('schedule_hour', 7):02d}:{web_cfg.get('schedule_minute', 30):02d}",
            "timezone": web_cfg.get("timezone", "America/Denver"),
            "weekdays": "Mon-Fri",
        },
    }


@app.get("/api/plans")
def api_plans() -> dict:
    latest = store.load_latest()
    if latest is None:
        return {"plans": [], "message": "No scan yet. Run a scan first."}
    return latest


@app.get("/api/history")
def api_history() -> dict:
    return {"history": store.list_history()}


@app.get("/api/history/{scan_id}")
def api_history_item(scan_id: str) -> dict:
    data = store.load_scan(scan_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return data


@app.post("/api/scan")
def api_scan(body: ScanRequest | None = None) -> dict:
    if service.is_scanning():
        raise HTTPException(status_code=409, detail="Scan already in progress")

    req = body or ScanRequest()
    try:
        return service.run_and_store(
            _config,
            fast=req.fast,
            source="manual",
            send_alert=req.alert,
        )
    except Exception as exc:
        logger.exception("Scan failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/intraday")
def api_intraday() -> dict:
    data = store.load_intraday()
    if data is None:
        return {"plans": [], "message": "No intraday scan yet. Click Refresh Intraday."}
    return data


@app.post("/api/intraday/scan")
def api_intraday_scan() -> dict:
    if service.is_intraday_scanning():
        raise HTTPException(status_code=409, detail="Intraday scan already in progress")
    try:
        result = service.run_intraday_and_store(_config)
        if result.get("status") == "busy":
            raise HTTPException(status_code=409, detail="Intraday scan already in progress")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Intraday scan failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/reversal")
def api_reversal() -> dict:
    data = store.load_reversal()
    if data is None:
        return {"setups": [], "message": "No reversal scan yet. Click Scan Reversals."}
    return data


@app.post("/api/reversal/scan")
def api_reversal_scan() -> dict:
    if service.is_reversal_scanning():
        raise HTTPException(status_code=409, detail="Reversal scan already in progress")
    try:
        result = service.run_reversal_and_store(_config)
        if result.get("status") == "busy":
            raise HTTPException(status_code=409, detail="Reversal scan already in progress")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Reversal scan failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/portfolio")
def api_portfolio_get() -> dict:
    return store.load_portfolio()


@app.put("/api/portfolio")
def api_portfolio_save(body: PortfolioSaveRequest) -> dict:
    symbols = [s.strip().upper() for s in body.symbols if s.strip()]
    return store.save_portfolio(symbols)


@app.put("/api/session")
def api_session_save(body: SessionRequest) -> dict:
    return store.save_session(active_tab=body.active_tab, fast_mode=body.fast_mode)


@app.post("/api/portfolio/review")
def api_portfolio_review(body: PortfolioRequest) -> dict:
    try:
        return service.review_portfolio(body.symbols, _config, fast=body.fast)
    except Exception as exc:
        logger.exception("Portfolio review failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


_static_dir = STATIC_DIR if STATIC_DIR.exists() else PUBLIC_STATIC_DIR
if _static_dir.exists() and not os.environ.get("VERCEL"):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


def run_server(host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    web_cfg = _config.section("web")
    h = host or web_cfg.get("host", "127.0.0.1")
    p = port or int(web_cfg.get("port", 8787))
    uvicorn.run(
        "stockscanner.web.app:app",
        host=h,
        port=p,
        reload=False,
        log_level="info",
    )
