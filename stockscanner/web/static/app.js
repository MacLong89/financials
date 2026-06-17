const $ = (id) => document.getElementById(id);

let activeTab = "swing";

const LS_PORTFOLIO = "stockscanner.portfolio";
const LS_SESSION = "stockscanner.session";

function readPortfolioLocal() {
  try {
    const raw = localStorage.getItem(LS_PORTFOLIO);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writePortfolioLocal(payload) {
  try {
    localStorage.setItem(LS_PORTFOLIO, JSON.stringify(payload));
  } catch (_) { /* private mode / quota */ }
}

function readSessionLocal() {
  try {
    const raw = localStorage.getItem(LS_SESSION);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeSessionLocal(patch) {
  const next = {
    ...(readSessionLocal() || {}),
    ...patch,
    updated_at: new Date().toISOString(),
  };
  try {
    localStorage.setItem(LS_SESSION, JSON.stringify(next));
  } catch (_) { /* private mode / quota */ }
}

function fmtMoney(n) {
  if (n == null || n === 0) return "—";
  return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtTime(iso) {
  if (!iso) return "Never";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

function confClass(c) {
  if (c >= 70) return "conf-high";
  if (c >= 55) return "conf-mid";
  return "conf-low";
}

function setupClass(setup) {
  if (!setup) return "";
  if (setup.startsWith("ORB") || setup.startsWith("VWAP")) return "setup-trigger";
  if (setup.startsWith("TREND")) return "setup-watch";
  if (setup === "NO DATA" || setup === "ERROR") return "setup-error";
  return "";
}

function fmtConf(p) {
  const v = p.confidence_exact ?? p.confidence;
  return Number(v).toFixed(1) + "%";
}

function scoreCell(scores, key) {
  if (!scores || scores[key] == null) return "—";
  return Number(scores[key]).toFixed(0);
}

function setStatus(text, cls, tab = "swing") {
  const ids = {
    swing: "scan-status",
    intraday: "id-scan-status",
    portfolio: "pf-status",
    reversal: "rev-scan-status",
  };
  const el = $(ids[tab] || "scan-status");
  if (!el) return;
  el.textContent = text;
  el.className = "status-pill " + cls;
}

function ratingClass(rating) {
  if (rating === "STRONG HOLD") return "rating-strong";
  if (rating === "HOLD") return "rating-hold";
  if (rating === "WATCH") return "rating-watch";
  if (rating === "TRIM") return "rating-trim";
  if (rating === "EXIT") return "rating-exit";
  return "";
}

const RATING_ORDER = {
  "STRONG HOLD": 0,
  HOLD: 1,
  WATCH: 2,
  TRIM: 3,
  EXIT: 4,
  "—": 5,
};

function sortHoldings(holdings) {
  return [...holdings].sort((a, b) => {
    const ra = RATING_ORDER[a.rating] ?? 9;
    const rb = RATING_ORDER[b.rating] ?? 9;
    if (ra !== rb) return ra - rb;
    const ca = Number(a.confidence) || 0;
    const cb = Number(b.confidence) || 0;
    if (cb !== ca) return cb - ca;
    return String(a.symbol).localeCompare(String(b.symbol));
  });
}

function preparePlans(plans) {
  const rows = plans.map((p) => ({
    ...p,
    confidence_exact: Number(p.confidence_exact ?? p.confidence ?? 0),
  }));
  rows.sort((a, b) => b.confidence_exact - a.confidence_exact || (a.stock || a.symbol || "").localeCompare(b.stock || b.symbol || ""));
  return rows.map((p, i) => ({ ...p, priority: i + 1 }));
}

function renderPlans(data) {
  const body = $("plans-body");
  const plans = preparePlans(data?.plans || []);
  if (!plans.length) {
    body.innerHTML = '<tr><td colspan="9" class="empty">No trade plans match filters today.</td></tr>';
    return;
  }
  body.innerHTML = plans.map((p) => {
    const s = p.scores || {};
    const total = s.total_score ?? p.confidence_exact ?? p.confidence;
    return `
    <tr>
      <td class="priority">${p.priority}</td>
      <td><strong>${p.stock}</strong></td>
      <td class="summary-cell">${p.summary}</td>
      <td>${scoreCell(s, "momentum_score")}</td>
      <td>${scoreCell(s, "confirmation_score")}</td>
      <td class="${confClass(total)}">${Number(total).toFixed(1)}%</td>
      <td>${fmtMoney(p.entry)}</td>
      <td>${fmtMoney(p.target)}</td>
      <td>${fmtMoney(p.stop)}</td>
    </tr>
  `;
  }).join("");
}

function renderIntraday(data) {
  const body = $("id-plans-body");
  const allowed = new Set(data?.symbols || ["SPY", "QQQ"]);
  const plans = (data?.plans || []).filter((p) => allowed.has(p.symbol));
  if (!plans.length) {
    body.innerHTML = '<tr><td colspan="10" class="empty">No data yet. Click Refresh Intraday.</td></tr>';
    return;
  }

  const sorted = [...plans].sort((a, b) => (b.confidence || 0) - (a.confidence || 0) || a.symbol.localeCompare(b.symbol));

  body.innerHTML = sorted.map((p, i) => {
    const tradeable = p.detail?.tradeable;
    const rowCls = tradeable ? ' class="row-tradeable"' : '';
    return `
    <tr${rowCls}>
      <td class="priority">${p.priority || i + 1}</td>
      <td><strong>${p.symbol}</strong></td>
      <td class="${setupClass(p.setup)}">${p.setup}</td>
      <td>${p.bias}</td>
      <td>${p.summary}</td>
      <td class="${confClass(p.confidence)}">${Number(p.confidence).toFixed(1)}%</td>
      <td>${fmtMoney(p.entry)}</td>
      <td>${fmtMoney(p.target)}</td>
      <td>${fmtMoney(p.stop)}</td>
      <td>${fmtMoney(p.vwap)}</td>
    </tr>
  `;
  }).join("");

  $("id-last-scan").textContent = fmtTime(data.ran_at);
  const triggers = plans.filter((p) => p.setup?.startsWith("ORB") || p.setup?.startsWith("VWAP")).length;
  $("id-setup-count").textContent = `${triggers} trigger · ${plans.length} symbols`;
  if (data.symbols?.length) {
    $("id-symbols").textContent = data.symbols.join(" · ");
  }
}

function renderReversal(data) {
  const body = $("rev-body");
  const setups = data?.setups || [];
  if (!setups.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">No oversold setups found.</td></tr>';
    $("rev-last-scan").textContent = fmtTime(data?.ran_at);
    $("rev-count").textContent = "0 setups";
    return;
  }
  body.innerHTML = setups.map((s, i) => `
    <tr>
      <td class="priority">${i + 1}</td>
      <td><strong>${s.symbol}</strong></td>
      <td class="${setupClass(s.setup)}">${s.setup}</td>
      <td>${Number(s.rsi).toFixed(0)}</td>
      <td>${s.summary}</td>
      <td class="${confClass(s.confidence)}">${Number(s.confidence).toFixed(1)}%</td>
      <td>${fmtMoney(s.price)}</td>
    </tr>
  `).join("");
  $("rev-last-scan").textContent = fmtTime(data.ran_at);
  $("rev-count").textContent = `${setups.length} setups`;
}

function renderDashboard(payload) {
  if (!payload) return;

  const regime = payload.regime || {};
  const stats = payload.stats || {};
  const rules = payload.plan_rules || {};

  const card = $("regime-card");
  card.classList.remove("risk-on", "risk-off");
  if (regime.is_risk_on) {
    card.classList.add("risk-on");
    $("regime-label").textContent = "RISK-ON";
  } else {
    card.classList.add("risk-off");
    $("regime-label").textContent = "RISK-OFF";
  }

  $("regime-meta").textContent = regime.benchmark
    ? `${regime.benchmark} $${Number(regime.last_close).toFixed(2)} · ${regime.ma_period}MA $${Number(regime.ma_value).toFixed(2)}`
    : "—";

  $("last-scan").textContent = fmtTime(payload.ran_at);
  $("scan-source").textContent = payload.source ? `via ${payload.source}` : "—";
  $("match-count").textContent = `${stats.match_count ?? "—"} / ${stats.plan_count ?? "—"}`;

  const stopPct = ((rules.stop_pct || 0) * 100).toFixed(1);
  const rr = rules.reward_risk || 2;
  $("plan-rules").textContent = `Stop -${stopPct}% · Target ${rr}x risk · Min conf ${rules.min_confidence || 0}%`;

  renderPlans(payload);
}

function renderPortfolio(data) {
  const body = $("pf-body");
  const holdings = sortHoldings(data?.holdings || []);
  if (!holdings.length) {
    body.innerHTML = '<tr><td colspan="10" class="empty">No holdings rated.</td></tr>';
    return;
  }

  body.innerHTML = holdings.map((h) => {
    const s = h.scores || {};
    const total = s.combined_score ?? h.confidence;
    return `
    <tr>
      <td><strong>${h.symbol}</strong></td>
      <td class="${ratingClass(h.rating)}">${h.rating}</td>
      <td>${h.signal_count}/6 ${h.signals}</td>
      <td>${h.confirmers || "—"}</td>
      <td>${scoreCell(s, "momentum_score")}</td>
      <td>${scoreCell(s, "quality_score")}</td>
      <td class="${confClass(total)}">${Number(total).toFixed(1)}%</td>
      <td>${fmtMoney(h.price)}</td>
      <td class="${h.above_200ma ? "ma-yes" : "ma-no"}">${h.above_200ma ? "Above" : "Below"}</td>
      <td>${h.reason}${h.quality_label ? ` · ${h.quality_label}` : ""}</td>
    </tr>
  `;
  }).join("");

  const summary = data.summary || {};
  $("pf-ok-count").textContent = `${summary.strong_hold || 0} / ${summary.hold || 0}`;
  $("pf-risk-count").textContent = `Trim ${summary.trim || 0} · Exit ${summary.exit || 0} · Watch ${summary.watch || 0}`;
  $("pf-last-review").textContent = fmtTime(data.ran_at);
  $("pf-count").textContent = data.symbol_count ?? holdings.length;

  const regime = data.regime || {};
  const card = $("pf-regime-card");
  card.classList.remove("risk-on", "risk-off");
  if (regime.is_risk_on) {
    card.classList.add("risk-on");
    $("pf-regime-label").textContent = "RISK-ON";
  } else if (regime.label) {
    card.classList.add("risk-off");
    $("pf-regime-label").textContent = "RISK-OFF";
  }
  $("pf-regime-meta").textContent = regime.benchmark
    ? `${regime.benchmark} $${Number(regime.last_close).toFixed(2)}`
    : "—";
}

function parseSymbols(text) {
  return [...new Set(
    text.split(/[\n,\s]+/).map((s) => s.trim().toUpperCase()).filter(Boolean)
  )];
}

function updatePortfolioCount() {
  $("pf-count").textContent = parseSymbols($("pf-symbols").value).length;
}

function persistPortfolioSymbolsLocally() {
  const symbols = parseSymbols($("pf-symbols").value);
  const local = readPortfolioLocal();
  writePortfolioLocal({
    symbols,
    updated_at: new Date().toISOString(),
    last_review: local?.last_review,
  });
}

async function saveSession(patch = {}) {
  writeSessionLocal(patch);
  try {
    await fetch("/api/session", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
  } catch (_) { /* ignore */ }
}

let savePortfolioTimer;
function schedulePortfolioSave() {
  clearTimeout(savePortfolioTimer);
  savePortfolioTimer = setTimeout(() => savePortfolio(true), 600);
}

async function loadPortfolio() {
  const local = readPortfolioLocal();
  if (local?.symbols?.length) {
    $("pf-symbols").value = local.symbols.join("\n");
    updatePortfolioCount();
    if (local.last_review) renderPortfolio(local.last_review);
  }

  try {
    const res = await fetch("/api/portfolio");
    const data = await res.json();
    const localUpdated = local?.updated_at ? Date.parse(local.updated_at) : 0;
    const serverUpdated = data.updated_at ? Date.parse(data.updated_at) : 0;

    if (data.symbols?.length && serverUpdated > localUpdated) {
      $("pf-symbols").value = data.symbols.join("\n");
      updatePortfolioCount();
      writePortfolioLocal({
        symbols: data.symbols,
        updated_at: data.updated_at,
        last_review: data.last_review || local?.last_review,
      });
    }
    if (data.last_review && serverUpdated >= localUpdated) {
      renderPortfolio(data.last_review);
    }
  } catch (_) { /* server unavailable — local copy already applied */ }
}

function applySession(session) {
  if (!session) return;
  if (session.fast_mode != null) $("chk-fast").checked = !!session.fast_mode;
  if (session.active_tab && $(`tab-${session.active_tab}`)) {
    switchTab(session.active_tab, false);
  }
}

async function savePortfolio(silent = false) {
  const symbols = parseSymbols($("pf-symbols").value);
  const local = readPortfolioLocal();
  writePortfolioLocal({
    symbols,
    updated_at: new Date().toISOString(),
    last_review: local?.last_review,
  });

  if (!silent) setStatus("Saving…", "running", "portfolio");
  try {
    await fetch("/api/portfolio", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols }),
    });
    updatePortfolioCount();
    if (!silent) {
      setStatus("Saved", "done", "portfolio");
      setTimeout(() => setStatus("Ready", "idle", "portfolio"), 2000);
    }
  } catch (e) {
    updatePortfolioCount();
    if (!silent) {
      setStatus("Saved locally", "done", "portfolio");
      setTimeout(() => setStatus("Ready", "idle", "portfolio"), 2000);
    }
  }
}

async function runPortfolioReview() {
  const symbols = parseSymbols($("pf-symbols").value);
  if (!symbols.length) {
    alert("Enter at least one ticker.");
    return;
  }

  setStatus("Rating…", "running", "portfolio");
  $("btn-pf-review").disabled = true;
  $("btn-scan").disabled = true;

  try {
    await fetch("/api/portfolio", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols }),
    });

    const res = await fetch("/api/portfolio/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols, fast: $("chk-fast").checked }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Review failed");
    }

    const data = await res.json();
    renderPortfolio(data);
    writePortfolioLocal({
      symbols,
      updated_at: new Date().toISOString(),
      last_review: data,
    });
    setStatus("Done", "done", "portfolio");
  } catch (e) {
    setStatus("Error", "idle", "portfolio");
    alert(e.message);
  } finally {
    $("btn-pf-review").disabled = false;
    if (activeTab === "portfolio") $("btn-scan").disabled = false;
    setTimeout(() => setStatus("Ready", "idle", "portfolio"), 3000);
  }
}

function switchTab(tab, persist = true) {
  activeTab = tab;
  document.querySelectorAll(".tab").forEach((btn) => {
    const on = btn.dataset.tab === tab;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  $("tab-swing").classList.toggle("active", tab === "swing");
  $("tab-intraday").classList.toggle("active", tab === "intraday");
  $("tab-reversal").classList.toggle("active", tab === "reversal");
  $("tab-portfolio").classList.toggle("active", tab === "portfolio");

  const subtitles = {
    swing: "Empirical swing trade plans",
    intraday: "SPY / QQQ intraday — play money only",
    reversal: "Oversold mean-reversion bounces (RISK-ON)",
    portfolio: "Hold / trim / exit ratings for your positions",
  };
  const btnLabels = {
    swing: "Run Scan Now",
    intraday: "Refresh Intraday",
    reversal: "Scan Reversals",
    portfolio: "Rate Holdings",
  };
  const footers = {
    swing: "Core: JT·GH·IM·PE·6-1·TR · Confirmers: RS·VOL·SQZ·MA",
    intraday: "ORB · VWAP reclaim · Trend watch · 0.3% stop · 2:1 R:R",
    reversal: "RSI < 30 · above 200 MA · BB reclaim bonus",
    portfolio: "STRONG HOLD · HOLD · WATCH · TRIM · EXIT",
  };

  $("page-subtitle").textContent = subtitles[tab] || subtitles.swing;
  $("btn-scan").textContent = btnLabels[tab] || btnLabels.swing;
  $("fast-wrap").style.display = tab === "swing" || tab === "portfolio" ? "flex" : "none";
  $("footer-signals").textContent = footers[tab] || footers.swing;

  if (persist) saveSession({ active_tab: tab });
}

async function loadStatus() {
  const res = await fetch("/api/status");
  const data = await res.json();

  if (data.scanning) {
    setStatus("Scanning…", "running", "swing");
    if (activeTab === "swing") $("btn-scan").disabled = true;
  } else if (!data.intraday_scanning) {
    setStatus("Ready", "idle", "swing");
    if (activeTab === "swing") $("btn-scan").disabled = false;
  }

  if (data.intraday_scanning) {
    setStatus("Refreshing…", "running", "intraday");
    if (activeTab === "intraday") $("btn-scan").disabled = true;
  } else if (!data.scanning) {
    setStatus("Ready", "idle", "intraday");
    if (activeTab === "intraday") $("btn-scan").disabled = false;
  }

  const sched = data.schedule || {};
  $("schedule-time").textContent = sched.enabled
    ? `${sched.time} ${sched.timezone?.split("/").pop() || ""}`
    : "Off";
  $("schedule-tz").textContent = sched.weekdays || "Mon–Fri";

  if (data.latest) renderDashboard(data.latest);
  if (data.intraday) renderIntraday(data.intraday);
  if (data.reversal) renderReversal(data.reversal);

  if (data.reversal_scanning) {
    setStatus("Scanning…", "running", "reversal");
    if (activeTab === "reversal") $("btn-scan").disabled = true;
  } else if (!data.scanning && !data.intraday_scanning) {
    setStatus("Ready", "idle", "reversal");
    if (activeTab === "reversal") $("btn-scan").disabled = false;
  }

  const localSession = readSessionLocal();
  if (data.session) {
    const localT = localSession?.updated_at ? Date.parse(localSession.updated_at) : 0;
    const serverT = data.session.updated_at ? Date.parse(data.session.updated_at) : 0;
    if (serverT > localT) applySession(data.session);
  }
}

async function loadHistory() {
  const res = await fetch("/api/history");
  const data = await res.json();
  const list = $("history-list");
  const items = data.history || [];

  if (!items.length) {
    list.innerHTML = '<li class="empty">No history</li>';
    return;
  }

  list.innerHTML = items.map((h) => `
    <li data-id="${h.id}">
      <span>${fmtTime(h.ran_at)} · ${h.regime || "—"}</span>
      <span>${h.plan_count} plans</span>
    </li>
  `).join("");

  list.querySelectorAll("li[data-id]").forEach((li) => {
    li.addEventListener("click", async () => {
      const id = li.dataset.id;
      const res = await fetch(`/api/history/${id}`);
      const scan = await res.json();
      renderDashboard(scan);
      setStatus("History", "done", "swing");
    });
  });
}

async function runSwingScan() {
  setStatus("Scanning…", "running", "swing");
  $("btn-scan").disabled = true;

  try {
    const res = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fast: $("chk-fast").checked, alert: false }),
    });

    if (res.status === 409) {
      setStatus("Busy", "running", "swing");
      return;
    }

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Scan failed");
    }

    const data = await res.json();
    renderDashboard(data);
    setStatus("Done", "done", "swing");
    await loadHistory();
  } catch (e) {
    setStatus("Error", "idle", "swing");
    alert(e.message);
  } finally {
    $("btn-scan").disabled = false;
    setTimeout(() => setStatus("Ready", "idle", "swing"), 3000);
  }
}

async function runIntradayScan() {
  setStatus("Refreshing…", "running", "intraday");
  $("btn-scan").disabled = true;

  try {
    const res = await fetch("/api/intraday/scan", { method: "POST" });

    if (res.status === 409) {
      setStatus("Busy", "running", "intraday");
      return;
    }

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Intraday scan failed");
    }

    const data = await res.json();
    renderIntraday(data);
    setStatus("Done", "done", "intraday");
  } catch (e) {
    setStatus("Error", "idle", "intraday");
    alert(e.message);
  } finally {
    $("btn-scan").disabled = false;
    setTimeout(() => setStatus("Ready", "idle", "intraday"), 3000);
  }
}

async function runReversalScan() {
  setStatus("Scanning…", "running", "reversal");
  $("btn-scan").disabled = true;
  try {
    const res = await fetch("/api/reversal/scan", { method: "POST" });
    if (res.status === 409) {
      setStatus("Busy", "running", "reversal");
      return;
    }
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Reversal scan failed");
    }
    const data = await res.json();
    renderReversal(data);
    setStatus("Done", "done", "reversal");
  } catch (e) {
    setStatus("Error", "idle", "reversal");
    alert(e.message);
  } finally {
    $("btn-scan").disabled = false;
    setTimeout(() => setStatus("Ready", "idle", "reversal"), 3000);
  }
}

function runScan() {
  if (activeTab === "intraday") runIntradayScan();
  else if (activeTab === "reversal") runReversalScan();
  else if (activeTab === "portfolio") runPortfolioReview();
  else runSwingScan();
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

$("btn-scan").addEventListener("click", runScan);
$("btn-pf-save").addEventListener("click", () => savePortfolio(false));
$("btn-pf-review").addEventListener("click", runPortfolioReview);
$("pf-symbols").addEventListener("input", () => {
  updatePortfolioCount();
  persistPortfolioSymbolsLocally();
  schedulePortfolioSave();
});
$("chk-fast").addEventListener("change", () => saveSession({ fast_mode: $("chk-fast").checked }));

applySession(readSessionLocal());
loadStatus();
loadHistory();
loadPortfolio();
setInterval(loadStatus, 15000);
