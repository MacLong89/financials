# Stock Scanner v1

Weekly / intraweekly momentum swing scanner for a **$10k play account** strategy:

- Rank by **6-month relative strength**
- Flag **52-week-high proximity**
- Detect **base breakout** and **20 EMA pullback** setups
- **SPY 200 MA regime** filter (risk-on / risk-off)
- Optional **earnings beat + gap hold** module

## Quick start

```bash
cd stockscanner
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m stockscanner regime
python -m stockscanner scan
python -m stockscanner scan --earnings
```

Results export automatically to `data/exports/scan_YYYYMMDD.csv`.

## Commands

| Command | Description |
|---------|-------------|
| `python -m stockscanner regime` | SPY vs 200-day MA — trade new longs only when RISK-ON |
| `python -m stockscanner scan` | Full S&P 500 scan with breakout + pullback setups |
| `python -m stockscanner scan --earnings` | Also scan recent earnings gap-and-hold names |
| `python -m stockscanner scan --alert` | Scan + send Discord/email if new setups |
| `python -m stockscanner alert-test` | Test your notification channels |

## Alerts (Discord + Email)

### 1. Configure secrets

```powershell
copy .env.example .env
# Edit .env with your webhook URL and/or SMTP credentials
```

**Discord:** Server Settings → Integrations → Webhooks → New Webhook → copy URL into `DISCORD_WEBHOOK_URL`.

**Gmail:** Use an [App Password](https://support.google.com/accounts/answer/185833) (not your login password). Set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`.

Disable a channel in `config.yaml`:

```yaml
alerts:
  email:
    enabled: false   # Discord only
```

### 2. Test

```powershell
python -m stockscanner alert-test
```

### 3. Scan with alerts

```powershell
python -m stockscanner scan --alert
python -m stockscanner scan --alert --force-alert   # always send
python -m stockscanner scan --alert --alert-mode all
```

### Alert modes (`config.yaml` → `alerts.mode`)

| Mode | Sends when |
|------|------------|
| `new` (default) | **New** symbol+setup combo vs last run, or **regime change** |
| `matches_only` | Any scan with ≥1 match |
| `all` | Every run with matches or RISK-OFF warning |

State is stored in `data/alerts/last_state.json` so you don't get pinged for the same LIN pullback every day.

### Schedule (Windows Task Scheduler)

Run every weekday after market close:

```
Program: C:\Users\Macra\OneDrive\Desktop\stockscanner\.venv\Scripts\python.exe
Args:    -m stockscanner scan --alert
Start in: C:\Users\Macra\OneDrive\Desktop\stockscanner
```

## Scanner logic (v1)

### Universe
S&P 500 (Wikipedia list). Override in `config.yaml` with `universe.source: custom`.

### Hard filters
- Price ≥ $10
- 20-day avg volume ≥ 500k shares
- 6-month return in **top 20%** of universe
- Within **5%** of 52-week high
- Above **200-day MA**
- **SPY > 200 MA** for new longs (unless `--earnings`)

### Setups
**Breakout (BO):** 10–20 day tight base (≤8% range), volume contraction, close above base high on ≥1.5× avg volume.

**Pullback (PB):** Touch 20 EMA (within 2%), green close back above EMA, rising 20 EMA.

**Earnings (ER):** Optional — gap up ≥3% on earnings, still holding above pre-earnings close, EPS beat when Yahoo data available.

### Scoring (0–100)
| Component | Weight |
|-----------|--------|
| RS percentile | 40% |
| 52W high proximity | 20% |
| Setup quality | 30% |
| Volume confirmation | 10% |

## Config

Edit `config.yaml` for thresholds, weights, cache TTL, and universe.

## Data source

**Free tier:** [Yahoo Finance via yfinance](https://github.com/ranaroussi/yfinance)

- Good for prices, volume, SPY regime
- Earnings dates / EPS estimates are **incomplete** — treat ER module as best-effort
- First full scan downloads ~500 symbols (~2–5 min); cached 4 hours in `data/cache/`

**Upgrade path (paid):** Polygon.io or IBKR for cleaner earnings, real-time, and faster bulk pulls.

## Trading rules (your playbook)

Use scanner output as a **watchlist**, not auto-buy:

1. **RISK-OFF** → no new longs (except optional earnings module review)
2. Pick **1–3 names** from top of list with BO or PB
3. Risk **1% of account** per trade (~$100 on $10k)
4. Stop **−7 to −8%**; time stop **10 trading days**
5. Max **3–4 open positions**

## Project layout

```
stockscanner/
  config.yaml
  requirements.txt
  stockscanner/
    cli.py          # CLI entry
    scanner.py      # orchestration
    regime.py       # SPY filter
    signals/        # breakout, pullback, earnings
    data.py         # yfinance + cache
```

## Disclaimer

Research tool only. Not financial advice. Past factor performance does not guarantee future results.
