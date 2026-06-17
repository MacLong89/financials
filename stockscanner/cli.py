from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from stockscanner.config import ScannerConfig
from stockscanner.data import fetch_benchmark
from stockscanner.plan import build_trade_plans
from stockscanner.regime import evaluate_regime
from stockscanner.scanner import run_scan
from stockscanner.alerts.dispatcher import configured_channels, dispatch_alerts, send_test_alerts


console = Console()


def _regime_panel(config: ScannerConfig) -> None:
    output_cfg = config.output
    cache_dir = Path(output_cfg.get("cache_dir", "data/cache"))
    if not cache_dir.is_absolute():
        cache_dir = Path(__file__).resolve().parent.parent / cache_dir

    regime_cfg = config.regime
    benchmark = regime_cfg.get("benchmark", "SPY")
    df = fetch_benchmark(
        benchmark,
        cache_dir=cache_dir,
        max_age_hours=float(output_cfg.get("cache_max_age_hours", 4)),
    )
    if df is None:
        console.print("[red]Could not load SPY data for regime check.[/red]")
        return

    status = evaluate_regime(
        df,
        benchmark=benchmark,
        ma_period=int(regime_cfg.get("ma_period", 200)),
        require_above=bool(regime_cfg.get("require_above", True)),
    )
    color = "green" if status.is_risk_on else "red"
    console.print(
        Panel(
            f"[bold]{status.benchmark}[/bold] close: ${status.last_close:,.2f}\n"
            f"{status.ma_period}-day MA: ${status.ma_value:,.2f} "
            f"({status.distance_pct:+.1%} vs MA)\n"
            f"Regime: [{color} bold]{status.label}[/{color} bold]",
            title="Market Regime",
            border_style=color,
        )
    )


def _print_results(result, config: ScannerConfig, *, export_path: Path | None) -> None:
    regime = result.regime
    color = "green" if regime.is_risk_on else "red"
    plan_cfg = config.plan
    output_cfg = config.output

    plans = build_trade_plans(
        result.candidates,
        stop_pct=float(plan_cfg.get("stop_pct", 0.075)),
        reward_risk=float(plan_cfg.get("reward_risk", 2.0)),
        min_confidence=int(plan_cfg.get("min_confidence", 0)),
        max_rows=int(output_cfg.get("plan_max_rows", 15)),
    )

    console.print(
        Panel(
            f"Regime: [{color}]{regime.label}[/{color}] | "
            f"Matches: {len(result.candidates)} | Plans shown: {len(plans)}\n"
            f"Stop: {float(plan_cfg.get('stop_pct', 0.075)):.1%} | "
            f"Target: {float(plan_cfg.get('reward_risk', 2.0)):.0f}x risk",
            title="Trade Plan Scan",
        )
    )

    if not regime.is_risk_on:
        console.print("[yellow]RISK-OFF — treat all plans as watch-only until SPY > 200 MA.[/yellow]")

    if not plans:
        console.print("[dim]No trade plans today.[/dim]")
        return

    table = Table(title="Swing Trade Plans", box=box.SIMPLE_HEAVY)
    table.add_column("#", justify="right")
    table.add_column("Stock")
    table.add_column("Scanner Summary")
    table.add_column("Conf%", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Stop", justify="right")

    for p in plans:
        table.add_row(
            str(p.priority),
            p.symbol,
            p.summary,
            f"{p.confidence_exact:.1f}",
            f"${p.entry:,.2f}",
            f"${p.target:,.2f}",
            f"${p.stop:,.2f}",
        )

    console.print(table)
    console.print(
        "[dim]Entry = last close. Conf = signal strength + chart trigger. "
        "Risk ~1% of account per trade.[/dim]"
    )

    if export_path:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        all_plans = build_trade_plans(
            result.candidates,
            stop_pct=float(plan_cfg.get("stop_pct", 0.075)),
            reward_risk=float(plan_cfg.get("reward_risk", 2.0)),
            min_confidence=int(plan_cfg.get("min_confidence", 0)),
            max_rows=None,
        )
        with export_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "priority",
                    "stock",
                    "scanner_summary",
                    "confidence_exact",
                    "entry",
                    "target",
                    "stop",
                    "chart",
                ],
            )
            writer.writeheader()
            for p in all_plans:
                writer.writerow(
                    {
                        "priority": p.priority,
                        "stock": p.symbol,
                        "scanner_summary": p.summary,
                        "confidence_exact": p.confidence_exact,
                        "entry": p.entry,
                        "target": p.target,
                        "stop": p.stop,
                        "chart": p.chart,
                    }
                )
        console.print(f"[green]Exported[/green] {export_path}")


def _print_alert_result(alert_result) -> None:
    if alert_result.sent:
        channels = []
        if alert_result.discord_ok:
            channels.append("Discord")
        if alert_result.email_ok:
            channels.append("Email")
        console.print(
            f"[green]Alert sent[/green] via {', '.join(channels)} "
            f"({alert_result.reason})"
        )
        if alert_result.new_keys:
            console.print(f"  New setups: {', '.join(sorted(alert_result.new_keys))}")
    else:
        console.print(f"[dim]Alert skipped:[/dim] {alert_result.reason}")

    for err in alert_result.errors:
        console.print(f"[red]{err}[/red]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Momentum swing scanner — weekly / intraweekly setups",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Run full universe scan")
    scan.add_argument(
        "--fast",
        action="store_true",
        help="Skip PEAD checks (faster; PE column will be empty)",
    )
    scan.add_argument(
        "--export",
        type=Path,
        default=None,
        help="Export results to CSV path",
    )
    scan.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml",
    )
    scan.add_argument(
        "--alert",
        action="store_true",
        help="Send Discord/email alert after scan (see .env.example)",
    )
    scan.add_argument(
        "--alert-mode",
        choices=["new", "all", "matches_only"],
        default=None,
        help="Override alerts.mode from config.yaml",
    )
    scan.add_argument(
        "--force-alert",
        action="store_true",
        help="Send alert even if no new setups (still respects channel config)",
    )

    sub.add_parser("regime", help="Show SPY 200 MA regime only")
    sub.add_parser("alert-test", help="Send a test message to configured channels")

    web = sub.add_parser("web", help="Start web dashboard")
    web.add_argument("--host", default=None)
    web.add_argument("--port", type=int, default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = args.config if hasattr(args, "config") and args.config else None
    config = ScannerConfig.load(config_path)

    if args.command == "regime":
        _regime_panel(config)
        return 0

    if args.command == "scan":
        console.print("[bold]Running momentum swing scan…[/bold]")
        export = args.export
        if export is None:
            stamp = datetime.now().strftime("%Y%m%d")
            export = Path("data/exports") / f"scan_{stamp}.csv"

        result = run_scan(config, skip_pead=args.fast)
        _print_results(result, config, export_path=export)

        if args.alert or args.force_alert:
            channels = configured_channels(config)
            if not any(channels.values()):
                console.print(
                    "[yellow]No alert channels configured. "
                    "Copy .env.example to .env and set credentials.[/yellow]"
                )
            else:
                alert_result = dispatch_alerts(
                    result,
                    config,
                    force=args.force_alert,
                    mode_override=args.alert_mode,
                )
                _print_alert_result(alert_result)
        return 0

    if args.command == "alert-test":
        channels = configured_channels(config)
        if not any(channels.values()):
            console.print(
                "[red]No channels configured.[/red] Copy .env.example to .env and fill in values."
            )
            return 1
        console.print("[bold]Sending test alert…[/bold]")
        alert_result = send_test_alerts(config)
        _print_alert_result(alert_result)
        return 0 if alert_result.sent and not alert_result.errors else 1

    if args.command == "web":
        from stockscanner.web.app import run_server

        console.print("[bold green]Stock Scanner web dashboard[/bold green]")
        web_cfg = config.section("web")
        host = args.host or web_cfg.get("host", "127.0.0.1")
        port = args.port or int(web_cfg.get("port", 8787))
        console.print(f"Open [link=http://{host}:{port}]http://{host}:{port}[/link]")
        console.print(
            f"Auto-scan: Mon-Fri {web_cfg.get('schedule_hour', 7):02d}:"
            f"{web_cfg.get('schedule_minute', 30):02d} "
            f"{web_cfg.get('timezone', 'America/Denver')}"
        )
        run_server(host=host, port=port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
