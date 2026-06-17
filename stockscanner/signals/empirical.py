from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from stockscanner.indicators import (
    above_ma,
    pct_return,
    pct_return_between,
    ratio_52w_high,
)
from stockscanner.regime import RegimeStatus
from stockscanner.signals.earnings import detect_earnings_gap_hold


@dataclass
class EmpiricalSignals:
    jt_momentum: bool = False
    gh_52w_high: bool = False
    industry_momentum: bool = False
    pead: bool = False
    momentum_6_1: bool = False
    trend: bool = False

    @property
    def pass_count(self) -> int:
        return sum(
            [
                self.jt_momentum,
                self.gh_52w_high,
                self.industry_momentum,
                self.pead,
                self.momentum_6_1,
                self.trend,
            ]
        )

    @property
    def codes(self) -> str:
        parts = []
        if self.jt_momentum:
            parts.append("JT")
        if self.gh_52w_high:
            parts.append("GH")
        if self.industry_momentum:
            parts.append("IM")
        if self.pead:
            parts.append("PE")
        if self.momentum_6_1:
            parts.append("6-1")
        if self.trend:
            parts.append("TR")
        return "+".join(parts) or "-"


@dataclass
class SignalContext:
    jt_pct: dict[str, float] = field(default_factory=dict)
    gh_pct: dict[str, float] = field(default_factory=dict)
    m61_pct: dict[str, float] = field(default_factory=dict)
    sector_rank: dict[str, float] = field(default_factory=dict)
    stock_sector_rs: dict[str, float] = field(default_factory=dict)
    sector_map: dict[str, str] = field(default_factory=dict)


def evaluate_empirical_signals(
    symbol: str,
    df: pd.DataFrame,
    *,
    regime: RegimeStatus,
    ctx: SignalContext,
    config: dict,
    pead_enabled_runtime: bool = True,
) -> EmpiricalSignals:
    sig = EmpiricalSignals()
    close = df["Close"]
    high = df["High"]

    # JT momentum
    jt_cfg = config.get("jt_momentum", {})
    if jt_cfg.get("enabled", True):
        lb = int(jt_cfg.get("lookback_days", 126))
        top_pct = float(jt_cfg.get("top_pct", 0.20))
        pct = ctx.jt_pct.get(symbol)
        if pct is not None and pct >= 1.0 - top_pct:
            sig.jt_momentum = True

    # George & Hwang 52-week high ratio
    gh_cfg = config.get("gh_52w_high", {})
    if gh_cfg.get("enabled", True):
        ratio = ratio_52w_high(close, high)
        if ratio is not None:
            if gh_cfg.get("use_top_pct", True):
                pct = ctx.gh_pct.get(symbol)
                top_pct = float(gh_cfg.get("top_pct", 0.20))
                if pct is not None and pct >= 1.0 - top_pct:
                    sig.gh_52w_high = True
            elif ratio >= float(gh_cfg.get("min_ratio", 0.90)):
                sig.gh_52w_high = True

    # Industry momentum
    im_cfg = config.get("industry_momentum", {})
    if im_cfg.get("enabled", True):
        sector = ctx.sector_map.get(symbol)
        if sector:
            sec_rank = ctx.sector_rank.get(sector)
            stk_rank = ctx.stock_sector_rs.get(symbol)
            top_sec = float(im_cfg.get("top_sector_pct", 0.30))
            top_stk = float(im_cfg.get("top_stock_in_sector_pct", 0.30))
            if sec_rank is not None and stk_rank is not None:
                if sec_rank >= 1.0 - top_sec and stk_rank >= 1.0 - top_stk:
                    sig.industry_momentum = True

    # PEAD
    pead_cfg = config.get("pead", {})
    if pead_cfg.get("enabled", True) and pead_enabled_runtime:
        er = detect_earnings_gap_hold(
            symbol,
            df,
            lookback_days=int(pead_cfg.get("lookback_days", 20)),
            min_gap_pct=float(pead_cfg.get("min_gap_pct", 0.02)),
            require_hold_gap=bool(pead_cfg.get("require_hold_gap", True)),
        )
        beat_ok = not pead_cfg.get("require_eps_beat", True) or er.beat is not False
        if er.triggered and beat_ok:
            sig.pead = True

    # 6-1 momentum
    m61_cfg = config.get("momentum_6_1", {})
    if m61_cfg.get("enabled", True):
        top_pct = float(m61_cfg.get("top_pct", 0.20))
        pct = ctx.m61_pct.get(symbol)
        if pct is not None and pct >= 1.0 - top_pct:
            sig.momentum_6_1 = True

    # Trend: stock above MA + market risk-on
    tr_cfg = config.get("trend", {})
    if tr_cfg.get("enabled", True):
        ma_p = int(tr_cfg.get("stock_ma_period", 200))
        stock_ok = above_ma(close, ma_p)
        if tr_cfg.get("require_stock_above_ma", True) and not stock_ok:
            pass
        else:
            market_ok = not tr_cfg.get("require_market_risk_on", True) or regime.is_risk_on
            if market_ok and (stock_ok if tr_cfg.get("require_stock_above_ma", True) else True):
                sig.trend = True

    return sig


def build_signal_context(
    history: dict[str, pd.DataFrame],
    sector_map: dict[str, str],
    sector_rank: dict[str, float],
    config: dict,
) -> SignalContext:
    from stockscanner.indicators import rs_percentile

    ctx = SignalContext(sector_map=sector_map, sector_rank=sector_rank)

    jt_lb = int(config.get("jt_momentum", {}).get("lookback_days", 126))
    jt_returns: dict[str, float] = {}
    gh_ratios: dict[str, float] = {}
    m61_returns: dict[str, float] = {}

    m61_cfg = config.get("momentum_6_1", {})
    total_lb = int(m61_cfg.get("total_lookback_days", 126))
    skip = int(m61_cfg.get("skip_days", 21))

    sector_stock_returns: dict[str, dict[str, float]] = {}

    for symbol, df in history.items():
        close = df["Close"]
        high = df["High"]
        ret_jt = pct_return(close, jt_lb)
        if ret_jt is not None:
            jt_returns[symbol] = ret_jt
        ratio = ratio_52w_high(close, high)
        if ratio is not None:
            gh_ratios[symbol] = ratio
        ret_m61 = pct_return_between(close, skip, total_lb)
        if ret_m61 is not None:
            m61_returns[symbol] = ret_m61

        sector = sector_map.get(symbol)
        if sector and ret_jt is not None:
            sector_stock_returns.setdefault(sector, {})[symbol] = ret_jt

    ctx.jt_pct = rs_percentile(jt_returns)
    ctx.gh_pct = rs_percentile(gh_ratios)
    ctx.m61_pct = rs_percentile(m61_returns)

    for sector, rets in sector_stock_returns.items():
        ranks = rs_percentile(rets)
        ctx.stock_sector_rs.update(ranks)

    return ctx
