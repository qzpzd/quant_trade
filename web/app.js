const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const PLOT = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#cfc6b0", family: "Segoe UI, Microsoft YaHei, PingFang SC, sans-serif", size: 11 },
  margin: { t: 28, r: 48, b: 40, l: 52 },
  legend: { orientation: "h", y: 1.08, font: { size: 11 } },
  xaxis: { gridcolor: "#2c3224", zeroline: false },
  yaxis: { gridcolor: "#2c3224", zeroline: false },
  hovermode: "x unified",
  dragmode: "pan",
};

const DAY = 86400000;
const PRICE_ROWS = 4;
const DATE_TICKS = [
  { dtickrange: [null, DAY * 20], value: "%m-%d" },
  { dtickrange: [DAY * 20, DAY * 120], value: "%Y-%m" },
  { dtickrange: [DAY * 120, null], value: "%Y" },
];

const PLOT_CFG = { responsive: true, displaylogo: false, scrollZoom: false };

function toMs(v) {
  if (typeof v === "number" && isFinite(v)) return v;
  const t = Date.parse(v);
  return isFinite(t) ? t : Number(v);
}

function dataBounds(gd, dateAxis) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const t of gd.data || []) {
    const xs = t.x || (t.y ? t.y.map((_, i) => i) : []);
    for (const x of xs) {
      const v = dateAxis ? toMs(x) : Number(x);
      if (!isFinite(v)) continue;
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
  }
  if (!isFinite(lo) || !isFinite(hi) || lo === hi) return null;
  return [lo, hi];
}

function hasCandle(gd) {
  return (gd.data || []).some((t) => t.type === "candlestick");
}

function visibleCandleRange(gd, a, b, dateAxis) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const t of gd.data || []) {
    if (t.type !== "candlestick") continue;
    const xs = t.x || [];
    for (let i = 0; i < xs.length; i++) {
      const xv = dateAxis ? toMs(xs[i]) : Number(xs[i]);
      if (!isFinite(xv) || xv < a || xv > b) continue;
      const low = Number(t.low[i]);
      const high = Number(t.high[i]);
      if (isFinite(low)) lo = Math.min(lo, low);
      if (isFinite(high)) hi = Math.max(hi, high);
    }
  }
  if (!isFinite(lo) || !isFinite(hi)) return null;
  if (lo === hi) {
    const pad = Math.abs(lo) * 0.02 || 0.05;
    return { lo: lo - pad, hi: hi + pad };
  }
  return { lo, hi };
}

function fourGridAxis(lo, hi) {
  const pad = (hi - lo) * 0.04 || Math.abs(hi) * 0.008 || 0.02;
  const a = lo - pad;
  const b = hi + pad;
  const dtick = (b - a) / PRICE_ROWS;
  const digits = dtick >= 0.1 ? 2 : dtick >= 0.01 ? 3 : 4;
  return {
    range: [a, b],
    dtick,
    tick0: a,
    tickformat: `.${digits}f`,
  };
}

function priceAxisLayout() {
  return {
    autorange: false,
    nticks: PRICE_ROWS + 1,
    tickmode: "linear",
    fixedrange: true,
    showgrid: true,
    zeroline: false,
    side: "right",
    separatethousands: false,
    exponentformat: "none",
  };
}

function visibleXRange(gd, dateAxis) {
  const xa = gd._fullLayout && gd._fullLayout.xaxis;
  if (!xa || !xa.range) return null;
  const a = dateAxis ? toMs(xa.range[0]) : Number(xa.range[0]);
  const b = dateAxis ? toMs(xa.range[1]) : Number(xa.range[1]);
  if (!isFinite(a) || !isFinite(b)) return null;
  return [Math.min(a, b), Math.max(a, b)];
}

function xViewKey(gd) {
  const xa = gd._fullLayout && gd._fullLayout.xaxis;
  if (!xa || !xa.range) return "";
  return `${xa.range[0]}|${xa.range[1]}`;
}

function writeYAxis(gd, axis) {
  const y = gd.layout.yaxis || (gd.layout.yaxis = {});
  y.autorange = false;
  y.fixedrange = true;
  y.tickmode = "linear";
  y.nticks = PRICE_ROWS + 1;
  y.range = axis.range.slice();
  y.dtick = axis.dtick;
  y.tick0 = axis.tick0;
  y.tickformat = axis.tickformat;
  if (gd._fullLayout && gd._fullLayout.yaxis) {
    gd._fullLayout.yaxis.autorange = false;
    gd._fullLayout.yaxis.tickmode = "linear";
    gd._fullLayout.yaxis.range = axis.range.slice();
    gd._fullLayout.yaxis.dtick = axis.dtick;
    gd._fullLayout.yaxis.tick0 = axis.tick0;
    gd._fullLayout.yaxis.tickformat = axis.tickformat;
  }
}

function yRelayout(axis) {
  return {
    "yaxis.autorange": false,
    "yaxis.fixedrange": true,
    "yaxis.tickmode": "linear",
    "yaxis.nticks": PRICE_ROWS + 1,
    "yaxis.range": axis.range,
    "yaxis.dtick": axis.dtick,
    "yaxis.tick0": axis.tick0,
    "yaxis.tickformat": axis.tickformat,
  };
}

function priceAxisForWindow(gd, a, b, dateAxis) {
  if (hasCandle(gd)) {
    const vis = visibleCandleRange(gd, a, b, dateAxis);
    if (!vis) return null;
    return fourGridAxis(vis.lo, vis.hi);
  }
  let lo = Infinity;
  let hi = -Infinity;
  for (const t of gd.data || []) {
    if (t.yaxis === "y2" || t.yaxis === "y3") continue;
    const xs = t.x || (t.y ? t.y.map((_, i) => i) : []);
    for (let i = 0; i < xs.length; i++) {
      const xv = dateAxis ? toMs(xs[i]) : Number(xs[i]);
      if (!isFinite(xv) || xv < a || xv > b) continue;
      if (t.y && t.y[i] != null && isFinite(t.y[i])) {
        lo = Math.min(lo, t.y[i]);
        hi = Math.max(hi, t.y[i]);
      }
    }
  }
  if (!isFinite(lo) || !isFinite(hi)) return null;
  const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.02 || 1;
  return { range: [lo - pad, hi + pad], dtick: undefined, tick0: undefined, tickformat: undefined };
}

function candleAxisFromTraces(traces) {
  const t = traces.find((x) => x.type === "candlestick");
  if (!t || !t.low || !t.high) return {};
  let lo = Infinity;
  let hi = -Infinity;
  for (let i = 0; i < t.low.length; i++) {
    const a = Number(t.low[i]);
    const b = Number(t.high[i]);
    if (isFinite(a)) lo = Math.min(lo, a);
    if (isFinite(b)) hi = Math.max(hi, b);
  }
  if (!isFinite(lo) || !isFinite(hi)) return {};
  const axis = fourGridAxis(lo, hi);
  return { range: axis.range, dtick: axis.dtick, tick0: axis.tick0, tickformat: axis.tickformat };
}

function paintTickLabels(gd, axis) {
  if (!axis || axis.dtick == null) return;
  const nodes = [...gd.querySelectorAll(".ytick text")];
  if (!nodes.length) return;
  const digits = Number(String(axis.tickformat || ".2f").replace(/[^0-9]/g, "")) || 2;
  const n = Math.min(nodes.length, PRICE_ROWS + 1);
  for (let i = 0; i < n; i++) {
    const v = axis.range[0] + axis.dtick * i;
    if (isFinite(v)) nodes[i].textContent = v.toFixed(digits);
  }
}

function fitYToVisible(gd, dateAxis, live) {
  if (gd.__skipAutoY) return;
  if (gd.__fittingY) return;
  const xb = visibleXRange(gd, dateAxis);
  if (!xb) return;
  const axis = priceAxisForWindow(gd, xb[0], xb[1], dateAxis);
  if (!axis) return;
  const key = xViewKey(gd);
  if (key && key === gd.__lastFitX && !live) return;
  gd.__lastFitX = key;
  writeYAxis(gd, axis);
  paintTickLabels(gd, axis);
  if (!live) {
    gd.__fittingY = true;
    Promise.resolve(Plotly.relayout(gd, yRelayout(axis))).finally(() => {
      gd.__fittingY = false;
    });
  }
}

function bindWheelZoom(gd, dateAxis) {
  gd.__dateAxis = dateAxis;
  if (gd.__zoomBound) return;
  gd.__zoomBound = true;
  gd.__wheelBound = true;

  let wheelRaf = 0;
  let pendingDelta = 0;
  let pendingFrac = 0.5;

  const applyWheelZoom = () => {
    wheelRaf = 0;
    const delta = pendingDelta;
    pendingDelta = 0;
    if (!delta || !gd._fullLayout || !gd._fullLayout.xaxis) return;
    const useDate = gd.__dateAxis !== false;
    const xa = gd._fullLayout.xaxis;
    const a = useDate ? toMs(xa.range[0]) : Number(xa.range[0]);
    const b = useDate ? toMs(xa.range[1]) : Number(xa.range[1]);
    if (!isFinite(a) || !isFinite(b) || b === a) return;
    const frac = pendingFrac;
    const factor = delta > 0 ? 1.18 : 1 / 1.18;
    const span = (b - a) * factor;
    const bounds = dataBounds(gd, useDate);
    let na = a + (b - a) * frac - span * frac;
    let nb = na + span;
    if (bounds) {
      const minSpan = useDate ? DAY * 5 : 4;
      if (nb - na < minSpan) {
        const c = na + (nb - na) / 2;
        na = c - minSpan / 2;
        nb = c + minSpan / 2;
      }
      if (na < bounds[0]) {
        nb += bounds[0] - na;
        na = bounds[0];
      }
      if (nb > bounds[1]) {
        na -= nb - bounds[1];
        nb = bounds[1];
      }
      na = Math.max(na, bounds[0]);
      nb = Math.min(nb, bounds[1]);
      if (!(nb > na)) return;
    }
    const range = useDate ? [new Date(na), new Date(nb)] : [na, nb];
    const payload = { "xaxis.range": range };
    if (hasCandle(gd)) {
      const axis = priceAxisForWindow(gd, na, nb, useDate);
      if (axis) Object.assign(payload, yRelayout(axis));
    }
    gd.__lastFitX = `${range[0]}|${range[1]}`;
    gd.__fittingY = true;
    Promise.resolve(Plotly.relayout(gd, payload)).finally(() => {
      gd.__fittingY = false;
    });
  };

  gd.addEventListener(
    "wheel",
    (ev) => {
      if (!gd._fullLayout || !gd._fullLayout.xaxis) return;
      ev.preventDefault();
      ev.stopPropagation();
      const rect = (gd.querySelector(".nsewdrag") || gd).getBoundingClientRect();
      pendingFrac = Math.min(Math.max((ev.clientX - rect.left) / Math.max(rect.width, 1), 0.02), 0.98);
      pendingDelta += ev.deltaY || 0;
      if (!wheelRaf) wheelRaf = requestAnimationFrame(applyWheelZoom);
    },
    { passive: false }
  );

  let panRaf = 0;
  gd.on("plotly_relayouting", () => {
    if (gd.__fittingY || gd.__skipAutoY || !hasCandle(gd)) return;
    if (panRaf) return;
    panRaf = requestAnimationFrame(() => {
      panRaf = 0;
      fitYToVisible(gd, gd.__dateAxis !== false, true);
    });
  });
  gd.on("plotly_relayout", (e) => {
    if (gd.__fittingY || gd.__skipAutoY || !hasCandle(gd)) return;
    const xChanged =
      e &&
      (e["xaxis.range[0]"] != null ||
        e["xaxis.range[1]"] != null ||
        e["xaxis.range"] != null ||
        e["xaxis.autorange"] != null);
    if (!xChanged) return;
    fitYToVisible(gd, gd.__dateAxis !== false, false);
  });
}

function renderPlot(id, traces, layout = {}, dateAxis = true) {
  const el = document.getElementById(id);
  const candle = traces.some((t) => t.type === "candlestick");
  const flow = traces.some((t) => t.yaxis === "y2" || t.yaxis === "y3");
  const xaxis = {
    ...(PLOT.xaxis || {}),
    ...(dateAxis
      ? { type: "date", rangeslider: { visible: false }, tickformatstops: DATE_TICKS }
      : {}),
    ...(layout.xaxis || {}),
  };
  const yaxis = {
    ...(PLOT.yaxis || {}),
    ...(candle ? { ...priceAxisLayout(), ...candleAxisFromTraces(traces) } : {}),
    ...(flow ? { domain: [0.32, 1] } : {}),
    ...(layout.yaxis || {}),
  };
  const yaxis2 = flow
    ? {
        domain: [0, 0.24],
        title: "",
        showgrid: true,
        gridcolor: "#2c3224",
        zeroline: false,
        side: "left",
        fixedrange: true,
        ...(layout.yaxis2 || {}),
      }
    : layout.yaxis2;
  const yaxis3 = flow
    ? {
        domain: [0, 0.24],
        overlaying: "y2",
        side: "right",
        showgrid: false,
        zeroline: false,
        title: "",
        fixedrange: true,
        ...(layout.yaxis3 || {}),
      }
    : layout.yaxis3;
  const margin = candle
    ? { ...(PLOT.margin || {}), l: 18, r: 58, ...(layout.margin || {}) }
    : { ...(PLOT.margin || {}), ...(layout.margin || {}) };
  const merged = { ...PLOT, ...layout, xaxis, yaxis, margin };
  if (yaxis2) {
    merged.yaxis2 = { ...yaxis2, title: yaxis2.title || "万" };
  }
  if (yaxis3) merged.yaxis3 = yaxis3;
  return Plotly.newPlot(el, traces, merged, PLOT_CFG).then((gd) => {
    gd.__lastFitX = "";
    gd.__skipAutoY = !candle;
    bindWheelZoom(gd, dateAxis);
    if (candle) fitYToVisible(gd, dateAxis, true);
    return gd;
  });
}

function candleTrace(bars) {
  return {
    type: "candlestick",
    x: bars.map((b) => b.date),
    open: bars.map((b) => b.open),
    high: bars.map((b) => b.high),
    low: bars.map((b) => b.low),
    close: bars.map((b) => b.close),
    increasing: { line: { color: "#e4454a" }, fillcolor: "#e4454a" },
    decreasing: { line: { color: "#2ea574" }, fillcolor: "#2ea574" },
    name: "K线",
    yaxis: "y",
  };
}

function fmtVol(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(abs >= 1e9 ? 2 : 2)}亿`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(abs >= 1e6 ? 1 : 2)}万`;
  return `${Math.round(n)}`;
}

function volumeTrace(bars) {
  const raw = bars.map((b) => b.volume);
  return {
    type: "bar",
    x: bars.map((b) => b.date),
    y: raw.map((v) => (v == null || !isFinite(Number(v)) ? null : Number(v) / 1e4)),
    name: "成交量(万)",
    marker: {
      color: bars.map((b) => (Number(b.close) >= Number(b.open) ? "rgba(228,69,74,0.55)" : "rgba(46,165,116,0.55)")),
    },
    yaxis: "y2",
    customdata: raw.map(fmtVol),
    hovertemplate: "%{x|%Y-%m-%d}<br>成交量 %{customdata}<extra></extra>",
  };
}

function turnoverTrace(bars) {
  return {
    type: "scatter",
    mode: "lines",
    x: bars.map((b) => b.date),
    y: bars.map((b) => b.turnover),
    name: "换手率%",
    line: { color: "#7aa2ff", width: 1.2 },
    yaxis: "y3",
    hovertemplate: "%{x|%Y-%m-%d}<br>换手 %{y:.2f}%<extra></extra>",
  };
}

function flowTraces(bars) {
  const out = [];
  if (bars.some((b) => b.volume != null && isFinite(Number(b.volume)))) out.push(volumeTrace(bars));
  if (bars.some((b) => b.turnover != null && isFinite(Number(b.turnover)))) out.push(turnoverTrace(bars));
  return out;
}

function withCandleFlow(bars, extras = []) {
  return [candleTrace(bars), ...extras, ...flowTraces(bars)];
}

function errText(detail) {
  if (!detail) return "请求失败";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  return JSON.stringify(detail);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errText(data.detail));
  return data;
}

function showBusy(on, text, pct) {
  const el = $("#busy");
  if (!el) return;
  const textEl = el.querySelector(".busy-text");
  const fill = $("#busy-fill");
  const pctEl = $("#busy-pct");
  if (textEl) textEl.textContent = text || "正在计算…";
  else if (on) el.childNodes[0] && (el.childNodes[0].textContent = text || "正在计算…");
  el.classList.toggle("hidden", !on);
  const hasPct = on && pct != null && isFinite(Number(pct));
  el.classList.toggle("indeterminate", on && !hasPct);
  if (fill) {
    if (hasPct) {
      fill.style.width = `${Math.min(100, Math.max(0, Number(pct)))}%`;
      fill.style.transform = "";
    } else {
      fill.style.width = on ? "36%" : "0%";
    }
  }
  if (pctEl) pctEl.textContent = hasPct ? `${Math.round(Number(pct))}%` : "";
  if (!on && Store.busyTimer) {
    clearInterval(Store.busyTimer);
    Store.busyTimer = null;
  }
}

/** 从缓存/同步状态算出真实进度百分比 */
function progressFromStatus(st) {
  if (!st || st.status !== "running") return null;
  const phase = st.phase || "bars";
  if (phase === "alerts" || phase === "dashboard" || phase === "sectors") {
    const done = Number(st.scan_done) || 0;
    const total = Number(st.scan_total) || 0;
    if (total > 0) return { done, total, pct: (done / total) * 100, phase };
    return { done: 0, total: 0, pct: null, phase };
  }
  const done = Number(st.done) || 0;
  const total = Number(st.total) || 0;
  if (total > 0) return { done, total, pct: (done / total) * 100, phase };
  return { done: 0, total: 0, pct: null, phase };
}

function phaseLabel(phase) {
  if (phase === "alerts") return "扫描买卖点";
  if (phase === "dashboard") return "生成大屏";
  if (phase === "sectors") return "更新行业概念";
  return "更新日线";
}

/** 无服务端分步计数的长任务：用时间推进到 92%，结束时到 100% */
function startBusyPulse(text) {
  if (Store.busyTimer) clearInterval(Store.busyTimer);
  const t0 = Date.now();
  showBusy(true, text, 3);
  Store.busyTimer = setInterval(() => {
    const sec = (Date.now() - t0) / 1000;
    const pct = Math.min(92, 3 + 89 * (1 - Math.exp(-sec / 6)));
    showBusy(true, text, pct);
  }, 250);
}

function stopBusyPulse(finalText) {
  if (Store.busyTimer) {
    clearInterval(Store.busyTimer);
    Store.busyTimer = null;
  }
  if (finalText) showBusy(true, finalText, 100);
  else showBusy(false);
}
function banner(msg, isError) {
  const el = $("#banner");
  if (!msg) {
    el.classList.add("hidden");
    return;
  }
  el.textContent = msg;
  el.style.background = isError ? "#24180f" : "#182214";
  el.style.color = isError ? "#e0a14a" : "#cfe08a";
  el.classList.remove("hidden");
}

function stats(el, items) {
  el.innerHTML = items
    .map(
      (s) =>
        `<div class="stat ${s.tone || ""}"><div class="v">${s.value}</div><div class="l">${s.label}</div></div>`
    )
    .join("");
}

function tonePct(v) {
  if (v == null || Number.isNaN(v)) return "";
  return v > 0 ? "up" : v < 0 ? "down" : "";
}
function fmtPct(v) {
  if (v == null || Number.isNaN(v)) return "—";
  const n = Number(v);
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}
function fmt(v, d = 2) {
  if (v == null || Number.isNaN(v)) return "—";
  return Number(v).toFixed(d);
}

function symbol() {
  return $("#symbol").value.trim();
}
function range() {
  return { start: $("#start").value, end: $("#end").value };
}

const Store = {
  stocks: [],
  summary: {},
  builtAt: null,
  watch: new Set(),
  selected: "002195",
  deskFilter: { mode: "industry", cat: "all", q: "" },
  deskPage: 1,
  pageSize: 72,
  groupPageSize: 12,
  groupShown: {},
  deskGroupKey: null,
  limitUpInd: null,
  limitUpCon: null,
  calYear: new Date().getFullYear(),
  calMonth: new Date().getMonth() + 1,
  calSelected: null,
  simBox: false,
  simHasBox: false,
  drawerMatch: null,
  busyTimer: null,
  screenId: null,
  screenIds: new Set(),
  screenCache: {},
  screenFocusId: null,
  screenMode: null,
  lastScreenHits: [],
  screenList: [],
  live: { by: {}, session: null, asOf: null, timer: null, quoteTimer: null },
};

function isWatched(code) {
  return Store.watch.has(String(code));
}

function syncWatchButtons() {
  const code = Store.selected || symbol();
  const on = isWatched(code);
  const label = on ? "★ 已自选" : "☆ 自选";
  ["#hdr-watch", "#drawer-watch"].forEach((sel) => {
    const el = $(sel);
    if (!el) return;
    el.textContent = label;
    el.classList.toggle("on", on);
  });
  const badge = $("#watch-badge");
  const n = Store.watch.size;
  badge.textContent = n ? String(n) : "";
  badge.classList.toggle("hidden", !n);
}

function highlightSelected() {
  const code = Store.selected;
  $$(".stock-card").forEach((el) => el.classList.toggle("selected", el.dataset.code === code));
}

function paintQuoteBar(q, opts = {}) {
  const live = opts.live;
  const price = live?.price != null ? live.price : q.close;
  const pct = live?.pct_chg != null ? live.pct_chg : q.pct_chg;
  const vol = live?.volume != null ? live.volume : q.volume;
  const turn = live?.turnover != null ? live.turnover : q.turnover;
  const cls = pct >= 0 ? "up" : "down";
  const stamp = live
    ? `现价 ${Store.live.asOf || ""}`
    : `${q.date || ""} · 日线缓存`;
  $("#quote").innerHTML = `
      <span class="name">${live?.name || q.name || ""}</span>
      <span class="px ${cls}">${fmt(price, 3)}</span>
      <span class="${cls}">${fmtPct(pct)}</span>
      <span class="hint">量 ${fmtVol(vol)}</span>
      <span class="hint">换手 ${turn == null ? "—" : fmt(turn) + "%"}</span>
      <span class="hint">${stamp} · ${q.symbol || live?.symbol || ""}</span>`;
}

function setLivePill(session, asOf) {
  const el = $("#live-pill");
  if (!el) return;
  const on = !!(session && (session.in_session || session.near_session));
  el.classList.toggle("on", on);
  el.classList.toggle("off", !on);
  const label = session?.label || "—";
  el.textContent = on ? `准实时 · ${label}${asOf ? " · " + String(asOf).slice(11) : ""}` : `准实时 · ${label}`;
  el.title = session
    ? `建议轮询 ${session.poll_sec}s · 现价 TTL ${session.quote_ttl_sec}s · 分钟线 ${session.minute_ttl_sec}s`
    : "准实时行情";
}

async function loadQuote() {
  banner("");
  showBusy(true, "载入行情…");
  try {
    const q = await api(`/api/quote/${symbol()}?start=${range().start}&end=${range().end}`);
    window.__lastQuote = q;
    if (Store.selected && Store.selected !== q.symbol) {
      Store.simHasBox = false;
      Store.simBox = false;
      $("#sim-box")?.classList.remove("on");
    }
    Store.selected = q.symbol;
    const live = Store.live.by[q.symbol];
    paintQuoteBar(q, { live });
    syncWatchButtons();
    highlightSelected();
    if ($("#view-similar") && $("#view-similar").classList.contains("active")) loadSimKline();
    refreshSelectedLive(true).catch(() => {});
    return q;
  } catch (e) {
    banner(e.message, true);
    throw e;
  } finally {
    showBusy(false);
  }
}

function applyLiveMap(items) {
  const by = { ...Store.live.by };
  (items || []).forEach((it) => {
    if (it && it.symbol && it.price != null) by[it.symbol] = it;
  });
  Store.live.by = by;
}

function refreshLiveCards() {
  const homeOn = $("#view-home")?.classList.contains("active");
  const watchOn = $("#view-watch")?.classList.contains("active");
  if (homeOn) {
    // 只重绘网格/自选相关，避免整页闪烁图表
    renderDeskGrid();
    renderWatchView();
  } else if (watchOn) {
    renderWatchView();
  }
}

async function pollLiveSpot() {
  try {
    const codes = new Set([...Store.watch]);
    if (Store.selected) codes.add(Store.selected);
    // 首页可见卡片也带上，但限制数量避免过重
    if ($("#view-home")?.classList.contains("active")) {
      filteredStocks()
        .slice(0, 40)
        .forEach((s) => codes.add(s.symbol));
    }
    const list = [...codes].filter(Boolean);
    if (!list.length) {
      const st = await api("/api/live/status");
      Store.live.session = st.session;
      setLivePill(st.session, null);
      return st;
    }
    const pack = await api(`/api/live/spot?symbols=${encodeURIComponent(list.join(","))}`);
    Store.live.session = pack.session;
    Store.live.asOf = pack.as_of;
    applyLiveMap(pack.items);
    setLivePill(pack.session, pack.as_of);
    refreshLiveCards();
    const q = window.__lastQuote;
    if (q && Store.live.by[q.symbol]) paintQuoteBar(q, { live: Store.live.by[q.symbol] });
    return pack;
  } catch (_) {
    /* 网络抖动时保持上次现价 */
    return null;
  }
}

async function refreshSelectedLive(force) {
  const code = Store.selected || symbol();
  if (!code) return;
  try {
    const q = await api(`/api/live/quote/${encodeURIComponent(code)}${force ? "?force=1" : ""}`);
    if (q.session) {
      Store.live.session = q.session;
      setLivePill(q.session, q.as_of);
    }
    if (q.price != null) {
      Store.live.by[code] = q;
      Store.live.asOf = q.as_of;
      if (window.__lastQuote && window.__lastQuote.symbol === code) {
        paintQuoteBar(window.__lastQuote, { live: q });
      } else if (!window.__lastQuote) {
        paintQuoteBar({ symbol: code, name: q.name, close: q.price, pct_chg: q.pct_chg, volume: q.volume, turnover: q.turnover }, { live: q });
      }
    }
  } catch (_) {
    /* ignore */
  }
}

function scheduleLivePoll() {
  if (Store.live.timer) clearInterval(Store.live.timer);
  const tick = async () => {
    await pollLiveSpot();
    const sec = Store.live.session?.poll_sec || 30;
    if (Store.live.timer) clearInterval(Store.live.timer);
    Store.live.timer = setInterval(tick, Math.max(5, sec) * 1000);
  };
  tick();
}

async function runBacktest() {
  banner("");
  const strategies = $$("#bt-strategies input[type=checkbox]:checked").map((el) => el.value);
  if (!strategies.length) {
    banner("请至少勾选一个策略", true);
    return;
  }
  const source = $("#bt-source")?.value || "symbol";
  const body = {
    strategies,
    start: range().start,
    end: range().end,
    cash: Number($("#bt-cash").value) || 100000,
  };
  if (source === "pattern") {
    const pid = $("#bt-pattern")?.value;
    if (!pid) {
      banner("请选择已保存形态", true);
      return;
    }
    body.pattern_ids = [pid];
  } else if (source === "screen") {
    const sid = $("#bt-screen")?.value;
    if (!sid) {
      banner("请选择已保存条件/名单", true);
      return;
    }
    body.screen_id = sid;
    body.max_symbols = 8;
  } else {
    body.symbol = symbol();
  }

  if (strategies.length === 1) {
    startBusyPulse(`回测运行中（${strategies[0]}）…`);
    try {
      const pack = await api("/api/backtest", { method: "POST", body: JSON.stringify(body) });
      if (pack.warning) banner(pack.warning, true);
      renderBacktestPack(pack);
    } catch (e) {
      banner(e.message, true);
    } finally {
      stopBusyPulse();
    }
    return;
  }

  showBusy(true, `回测 0/${strategies.length}`, 0);
  try {
    const allResults = [];
    const allCompare = [];
    const warnings = [];
    for (let i = 0; i < strategies.length; i++) {
      const sk = strategies[i];
      showBusy(true, `回测 ${sk}（${i + 1}/${strategies.length}）…`, (i / strategies.length) * 100);
      const pack = await api("/api/backtest", {
        method: "POST",
        body: JSON.stringify({ ...body, strategies: [sk], strategy: sk }),
      });
      if (pack.warning) warnings.push(pack.warning);
      allResults.push(...(pack.results || []));
      allCompare.push(...(pack.compare || []));
    }
    showBusy(true, "回测完成", 100);
    let keptBars = false;
    const results = allResults.map((r) => {
      if (r.error || !(r.bars || []).length) return r;
      if (keptBars) return { ...r, bars: [] };
      keptBars = true;
      return r;
    });
    renderBacktestPack({
      count: results.length,
      strategies,
      results,
      compare: allCompare,
      primary: results.find((r) => !r.error) || null,
      warning: warnings.length ? warnings.join("；") : null,
    });
  } catch (e) {
    banner(e.message, true);
  } finally {
    showBusy(false);
  }
}

const BT_COLORS = ["#e6ff4a", "#7aa2ff", "#e4454a", "#2ea574", "#e0a14a", "#c98bdb", "#9ad7c2", "#8b8473"];

function renderBacktestPack(pack) {
  const results = (pack.results || []).filter((r) => !r.error);
  const compare = pack.compare || [];
  const primary = pack.primary || results[0];

  if (!results.length) {
    $("#bt-stats").innerHTML = "";
    $("#bt-compare").innerHTML = `<p class="alert-empty">回测全部失败：${(pack.compare || []).map((c) => c.error).join("；") || "未知错误"}</p>`;
    return;
  }

  if (primary) {
    stats($("#bt-stats"), [
      { value: primary.final_value?.toLocaleString?.() ?? "—", label: `${primary.strategy_name || ""} 期末净值` },
      { value: fmtPct(primary.return_pct), label: "策略收益", tone: tonePct(primary.return_pct) },
      { value: fmtPct(primary.buy_hold_pct), label: "买入持有", tone: tonePct(primary.buy_hold_pct) },
      { value: `${fmt(primary.max_drawdown_pct)}%`, label: "最大回撤", tone: "down" },
      { value: primary.sharpe == null ? "—" : fmt(primary.sharpe), label: "年化夏普" },
      { value: primary.win_rate_pct == null ? "—" : `${fmt(primary.win_rate_pct, 1)}%`, label: `胜率 · ${primary.round_trips || 0} 轮` },
    ]);
  }

  $("#bt-compare").innerHTML = `
    <h2 class="section-title">策略对比</h2>
    <table>
      <thead><tr><th>标的</th><th>策略</th><th class="num">收益</th><th class="num">买入持有</th>
      <th class="num">最大回撤</th><th class="num">夏普</th><th class="num">胜率</th><th class="num">轮次</th><th>备注</th></tr></thead>
      <tbody>
        ${compare
          .map(
            (c) =>
              `<tr><td>${c.symbol || ""} ${c.name || ""}</td><td>${c.strategy_name || c.strategy || ""}</td>
               <td class="num ${tonePct(c.return_pct)}">${c.error ? "—" : fmtPct(c.return_pct)}</td>
               <td class="num ${tonePct(c.buy_hold_pct)}">${c.error ? "—" : fmtPct(c.buy_hold_pct)}</td>
               <td class="num">${c.max_drawdown_pct == null ? "—" : fmt(c.max_drawdown_pct) + "%"}</td>
               <td class="num">${c.sharpe == null ? "—" : fmt(c.sharpe)}</td>
               <td class="num">${c.win_rate_pct == null ? "—" : fmt(c.win_rate_pct, 1) + "%"}</td>
               <td class="num">${c.round_trips ?? "—"}</td>
               <td>${c.error || ""}</td></tr>`
          )
          .join("")}
      </tbody>
    </table>`;

  const eqTraces = [];
  results.forEach((r, i) => {
    if (!(r.equity || []).length) return;
    const cash0 = r.cash || Number($("#bt-cash").value) || 100000;
    eqTraces.push({
      x: r.equity.map((e) => e.date),
      y: r.equity.map((e) => e.value),
      name: `${r.symbol} · ${r.strategy_name}`,
      line: { color: BT_COLORS[i % BT_COLORS.length], width: i === 0 ? 1.8 : 1.3 },
    });
    if (i === 0 && (r.bars || []).length) {
      const startClose = r.bars[0].close;
      eqTraces.push({
        x: r.bars.map((b) => b.date),
        y: r.bars.map((b) => (b.close / startClose) * cash0),
        name: "买入持有",
        line: { color: "#8b8473", width: 1.2, dash: "dot" },
      });
    }
  });
  if (eqTraces.length) renderPlot("bt-equity", eqTraces, { yaxis: { ...PLOT.yaxis, title: "净值" } });

  if (primary && (primary.bars || []).length) {
    const buys = (primary.trades || []).filter((t) => t.side === "buy");
    const sells = (primary.trades || []).filter((t) => t.side === "sell");
    renderPlot("bt-chart", [
      candleTrace(primary.bars),
      {
        x: buys.map((t) => t.date),
        y: buys.map((t) => t.price),
        mode: "markers",
        name: `${primary.strategy_name} 买入`,
        marker: { color: "#e4454a", size: 9, symbol: "triangle-up" },
      },
      {
        x: sells.map((t) => t.date),
        y: sells.map((t) => t.price),
        mode: "markers",
        name: `${primary.strategy_name} 卖出`,
        marker: { color: "#2ea574", size: 9, symbol: "triangle-down" },
      },
    ]);
    $("#bt-trades").innerHTML = `
      <h2 class="section-title">成交明细（${primary.symbol} · ${primary.strategy_name}）</h2>
      <table>
        <thead><tr><th>日期</th><th>方向</th><th class="num">价格</th><th class="num">数量</th><th class="num">佣金</th></tr></thead>
        <tbody>
          ${(primary.trades || [])
            .map(
              (t) =>
                `<tr><td>${t.date}</td><td>${t.side === "buy" ? "买入" : "卖出"}</td>
                 <td class="num">${fmt(t.price)}</td><td class="num">${fmt(t.size, 0)}</td>
                 <td class="num">${fmt(t.comm, 2)}</td></tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  } else {
    $("#bt-trades").innerHTML = "";
  }
}

function syncBacktestSourceUI() {
  const src = $("#bt-source")?.value || "symbol";
  $("#bt-pattern-wrap")?.classList.toggle("hidden", src !== "pattern");
  $("#bt-screen-wrap")?.classList.toggle("hidden", src !== "screen");
}

async function refreshBacktestSelectors() {
  try {
    const [pats, scrs] = await Promise.all([api("/api/patterns"), api("/api/screens")]);
    const pEl = $("#bt-pattern");
    const sEl = $("#bt-screen");
    if (pEl) {
      const items = pats.items || [];
      pEl.innerHTML = items.length
        ? items.map((p) => `<option value="${p.id}">${p.name} · ${p.symbol} ${p.start}~${p.end}</option>`).join("")
        : `<option value="">暂无保存形态</option>`;
    }
    if (sEl) {
      const items = scrs.items || [];
      sEl.innerHTML = items.length
        ? items.map((s) => `<option value="${s.id}">${s.name} · ${s.mode === "static" ? "静态" : "动态"}</option>`).join("")
        : `<option value="">暂无保存条件</option>`;
    }
  } catch (_) {
    /* ignore */
  }
}

async function runSignals() {
  banner("");
  startBusyPulse("扫描买卖点…");
  try {
    const r = await api(`/api/analyze/${symbol()}?start=${range().start}&end=${range().end}`);
    stats($("#sig-head"), [
      { value: r.stance, label: "当前倾向" },
      { value: r.regime, label: "市场状态" },
      { value: fmt(r.snapshot.rsi14, 1), label: "RSI(14)" },
      { value: fmt(r.snapshot.adx14, 1), label: "ADX" },
      { value: fmt(r.snapshot.close, 3), label: "收盘" },
      { value: String(r.signals.length), label: "区间信号数" },
    ]);
    const bars = r.bars;
    const buys = r.signals.filter((s) => s.action === "buy");
    const sells = r.signals.filter((s) => s.action === "sell");
    renderPlot(
      "sig-chart",
      withCandleFlow(bars, [
        {
          x: bars.map((b) => b.date),
          y: bars.map((b) => b.ema20),
          name: "EMA20",
          line: { color: "#e6ff4a", width: 1 },
        },
        {
          x: bars.map((b) => b.date),
          y: bars.map((b) => b.ema60),
          name: "EMA60",
          line: { color: "#7aa2ff", width: 1 },
        },
        {
          x: bars.map((b) => b.date),
          y: bars.map((b) => b.bb_upper),
          name: "布林上轨",
          line: { color: "#8b8473", width: 1, dash: "dot" },
        },
        {
          x: bars.map((b) => b.date),
          y: bars.map((b) => b.bb_lower),
          name: "布林下轨",
          line: { color: "#8b8473", width: 1, dash: "dot" },
        },
        {
          x: buys.map((s) => s.date),
          y: buys.map((s) => s.price),
          mode: "markers",
          name: "买点",
          marker: { color: "#e4454a", size: 10, symbol: "triangle-up" },
        },
        {
          x: sells.map((s) => s.date),
          y: sells.map((s) => s.price),
          mode: "markers",
          name: "卖点",
          marker: { color: "#2ea574", size: 10, symbol: "triangle-down" },
        },
      ])
    );
    const reasons = (r.latest_reasons || []).map(
      (s) =>
        `<div class="reason ${s.action}">${s.source} · ${s.action === "buy" ? "偏多" : s.action === "sell" ? "偏空" : "观察"} — ${s.reason || ""}</div>`
    );
    const rows = [...r.signals].reverse().slice(0, 40);
    $("#sig-list").innerHTML =
      `<p class="hint">${r.regime_reason} ${r.disclaimer}</p>` +
      reasons.join("") +
      `<table><thead><tr><th>日期</th><th>动作</th><th>来源</th><th>说明</th><th class="num">价格</th></tr></thead><tbody>` +
      rows
        .map(
          (s) =>
            `<tr><td>${s.date}</td><td>${s.action === "buy" ? "买入" : "卖出"}</td><td>${s.source}</td><td>${s.reason}</td><td class="num">${fmt(s.price)}</td></tr>`
        )
        .join("") +
      `</tbody></table>`;
  } catch (e) {
    banner(e.message, true);
  } finally {
    stopBusyPulse();
  }
}

async function runPredict() {
  banner("");
  startBusyPulse("在缓存股票中匹配价+量+换手相似形态…");
  try {
    const r = await api("/api/predict", {
      method: "POST",
      body: JSON.stringify({
        symbol: symbol(),
        lookback: Number($("#pred-lookback").value) || 30,
        horizon: Number($("#pred-horizon").value) || 10,
      }),
    });
    stats($("#pred-head"), [
      { value: r.bias, label: "合成倾向" },
      { value: fmtPct(r.blend_return_pct), label: `${r.horizon}日合成收益`, tone: tonePct(r.blend_return_pct) },
      { value: fmtPct(r.analog_return_pct), label: "形态类比中位", tone: tonePct(r.analog_return_pct) },
      { value: `${fmtPct(r.analog_band[0])} ~ ${fmtPct(r.analog_band[1])}`, label: "类比四分位区间", tone: "" },
      { value: String(r.n_analogs), label: "采用相似窗口" },
      { value: `${r.scanned ?? "—"}`, label: `扫描缓存股 · 趋势权 ${r.trend_weight}` },
    ]);
    const srcHint = (r.analog_sources || [])
      .slice(0, 6)
      .map((s) => `${s.symbol}${s.name ? " " + s.name : ""}(${fmt(s.score, 2)})`)
      .join("；");
    $("#pred-note").textContent =
      (r.disclaimer || "") + (srcHint ? ` 示例来源：${srcHint}` : "");
    const histX = r.history.map((h) => h.date);
    const histY = r.history.map((h) => h.close);
    // 配色与图例一一对应：类比蓝、区间浅蓝带、趋势灰、合成黄、换手紫
    const COL = {
      close: "#efe7d6",
      analog: "#7aa2ff",
      band: "rgba(122,162,255,0.18)",
      bandEdge: "rgba(122,162,255,0.45)",
      trend: "#8b8473",
      blend: "#e6ff4a",
      turnover: "#c98bdb",
      volume: "rgba(230,255,74,0.35)",
    };
    const predTraces = [
      { x: histX, y: histY, name: "收盘", line: { color: COL.close, width: 1.4 } },
      {
        x: r.dates,
        y: r.path_high,
        name: "类比上沿",
        line: { color: COL.bandEdge, width: 0 },
        showlegend: false,
        hoverinfo: "skip",
      },
      {
        x: r.dates,
        y: r.path_low,
        name: "类比区间(P25–P75)",
        fill: "tonexty",
        fillcolor: COL.band,
        line: { color: COL.bandEdge, width: 0 },
      },
      {
        x: r.dates,
        y: r.path_analog,
        name: "形态类比(中位)",
        line: { color: COL.analog, width: 2, dash: "dot" },
      },
      {
        x: r.dates,
        y: r.path_trend,
        name: "趋势外推",
        line: { color: COL.trend, width: 1.2, dash: "dash" },
      },
      {
        x: r.dates,
        y: r.path_blend,
        name: "合成路径",
        line: { color: COL.blend, width: 2.2 },
      },
    ];
    if (r.history.some((h) => h.volume != null)) {
      const vols = r.history.map((h) => h.volume);
      predTraces.push({
        type: "bar",
        x: histX,
        y: vols.map((v) => (v == null ? null : Number(v) / 1e4)),
        name: "成交量(万)",
        marker: { color: COL.volume },
        yaxis: "y2",
        customdata: vols.map(fmtVol),
        hovertemplate: "%{x|%Y-%m-%d}<br>成交量 %{customdata}<extra></extra>",
      });
    }
    if (r.history.some((h) => h.turnover != null)) {
      predTraces.push({
        type: "scatter",
        mode: "lines",
        x: histX,
        y: r.history.map((h) => h.turnover),
        name: "换手率%",
        line: { color: COL.turnover, width: 1.2 },
        yaxis: "y3",
      });
    }
    renderPlot("pred-chart", predTraces);
  } catch (e) {
    banner(e.message, true);
  } finally {
    stopBusyPulse();
  }
}

async function pollSync(key) {
  showBusy(true, "正在启动缓存更新…", 1);
  await api("/api/universe/sync", { method: "POST", body: JSON.stringify({ universe: key }) });
  return new Promise((resolve, reject) => {
    const t = setInterval(async () => {
      try {
        const s = await api("/api/universe/sync/status");
        if (s.status === "running") {
          const info = progressFromStatus(s);
          const phase = phaseLabel(info?.phase || s.phase);
          const done = info?.done ?? 0;
          const total = info?.total ?? 0;
          showBusy(
            true,
            `${phase} ${s.key || key}  ${done}/${total || "?"}  提醒 ${s.alert_buys || 0}/${s.alert_sells || 0}`,
            info?.pct ?? null
          );
        } else if (s.status === "done") {
          clearInterval(t);
          showBusy(true, "同步完成", 100);
          setTimeout(() => showBusy(false), 280);
          banner(`已同步 ${s.done}/${s.total} 只股票` + (s.errors?.length ? `，失败 ${s.errors.length}` : ""), false);
          resolve(s);
        } else if (s.status === "error") {
          clearInterval(t);
          showBusy(false);
          reject(new Error(s.error || "同步失败"));
        }
      } catch (e) {
        clearInterval(t);
        showBusy(false);
        reject(e);
      }
    }, 600);
  });
}

async function runSimilar() {
  banner("");
  startBusyPulse("在缓存股票的近期窗口里匹配价+量+换手相似形态…");
  try {
    const ids = $$("#sim-patterns input[type=checkbox]:checked").map((el) => el.dataset.id);
    const start = $("#sim-start").value;
    const end = $("#sim-end").value;
    const includeCurrent = ($("#sim-include-current").checked || !ids.length) && !!(start && end);
    if (!ids.length && !includeCurrent) {
      banner("请先框选或填写形态区间，或勾选已保存形态", true);
      return;
    }
    const r = await api("/api/similar", {
      method: "POST",
      body: JSON.stringify({
        symbol: symbol(),
        start,
        end,
        universe: $("#sim-univ").value,
        top_n: 12,
        lookback_days: Number($("#sim-lookback").value) || 0,
        pattern_ids: ids,
        include_current: includeCurrent,
        analyze: true,
      }),
    });
    renderSimilarResult(r);
  } catch (e) {
    banner(e.message, true);
  } finally {
    stopBusyPulse();
  }
}

function renderSimilarResult(r) {
  const queries = r.queries || [
    { name: r.name, query_norm: r.query_norm, symbol: r.symbol, start: r.start, end: r.end },
  ];
  const traces = [];
  const palette = ["#e6ff4a", "#7aa2ff", "#e4454a", "#2ea574", "#e0a14a", "#c98bdb", "#8b8473", "#9ad7c2"];
  queries.forEach((q, i) => {
    traces.push({
      y: q.query_norm || r.query_norm,
      name: `模板 ${q.name || q.symbol || ""}`,
      line: { color: palette[i % palette.length], width: 2.2 },
    });
  });
  (r.matches || []).slice(0, 8).forEach((m, i) => {
    traces.push({
      y: m.match_norm,
      name: `${m.symbol} ${m.name}  ${m.corr}`,
      line: { color: palette[(i + queries.length) % palette.length], width: 1.1 },
      opacity: 0.85,
    });
  });
  renderPlot(
    "sim-chart",
    traces,
    { yaxis: { ...PLOT.yaxis, title: "标准化价格" }, xaxis: { title: "窗口内第 n 日" } },
    false
  );
  const look = r.lookback_days ? `最近 ${r.lookback_days} 日` : "全部历史";
  $("#sim-table").innerHTML = `
    <p class="hint">${r.method_label || "z-score 皮尔逊相关"} · 查找范围 ${look} · 已扫描 ${r.scanned} 只。相关系数衡量形状而不是涨跌幅。</p>
    <table>
      <thead><tr><th>代码</th><th>名称</th><th>命中形态</th><th>匹配区间</th>
      <th class="num">合成</th><th class="num">价</th><th class="num">量</th><th class="num">换手</th>
      <th class="num">此后5日</th><th class="num">此后10日</th></tr></thead>
      <tbody>
        ${(r.matches || [])
          .map((m) => {
            const pats = (m.patterns || []).map((p) => p.name).join("、") || (r.name || "当前区间");
            return `<tr data-code="${m.symbol}" data-start="${m.start || ""}" data-end="${m.end || ""}"><td>${m.symbol}</td><td>${m.name || ""}</td>
              <td>${pats}</td><td>${m.start || "—"} → ${m.end || "—"}</td>
              <td class="num">${fmt(m.corr, 3)}</td>
              <td class="num">${fmt(m.corr_price, 3)}</td>
              <td class="num">${fmt(m.corr_volume, 3)}</td>
              <td class="num">${fmt(m.corr_turnover, 3)}</td>
              <td class="num ${tonePct(m.forward_5)}">${fmtPct(m.forward_5)}</td>
              <td class="num ${tonePct(m.forward_10)}">${fmtPct(m.forward_10)}</td></tr>`;
          })
          .join("")}
      </tbody>
    </table>`;
  $$("#sim-table tr[data-code]").forEach((tr) => {
    tr.style.cursor = "pointer";
    tr.onclick = () =>
      selectSymbol(tr.dataset.code, {
        drawer: true,
        matchStart: tr.dataset.start,
        matchEnd: tr.dataset.end,
        matchLabel: "相似区间",
      });
  });
  renderSimStudy(r.study);
}

function renderSimStudy(study) {
  const picksEl = $("#sim-picks");
  const studyEl = $("#sim-study");
  if (!study) {
    picksEl.innerHTML = "";
    studyEl.innerHTML = "";
    return;
  }
  const picks = study.picks || [];
  picksEl.innerHTML = `
    <div class="study-block">
      <h3>合适买入</h3>
      ${
        picks.length
          ? `<div class="pick-row">${picks
              .map(
                (p) =>
                  `<div class="pick-card" data-code="${p.symbol}" data-start="${p.match_start || ""}" data-end="${p.match_end || ""}">
                    <div class="code">${p.symbol} ${p.name || ""}</div>
                    <div>${p.stance || ""} · 预测 ${p.bias || "—"} ${p.blend_return_pct == null ? "" : fmtPct(p.blend_return_pct)}</div>
                    <div class="why">${p.why || ""}</div>
                  </div>`
              )
              .join("")}</div>`
          : `<p class="hint">这一批里还没有同时满足形态相关、偏多信号和预测偏上涨的标的。</p>`
      }
      <p class="hint">${study.disclaimer || ""}</p>
    </div>`;
  $$("#sim-picks .pick-card").forEach((el) => {
    el.onclick = () =>
      selectSymbol(el.dataset.code, {
        drawer: true,
        matchStart: el.dataset.start,
        matchEnd: el.dataset.end,
        matchLabel: "相似区间",
      });
  });
  const rows = study.rows || [];
  studyEl.innerHTML = `
    <div class="study-block">
      <h3>对比分析</h3>
      <table><thead><tr><th>代码</th><th>名称</th><th class="num">形态数</th><th class="num">相关</th>
      <th>匹配区间</th><th class="num">此后5日</th><th class="num">此后10日</th></tr></thead>
      <tbody>${rows
        .map(
          (h) =>
            `<tr data-code="${h.symbol}" data-start="${h.match_start || ""}" data-end="${h.match_end || ""}"><td>${h.symbol}</td><td>${h.name || ""}</td>
             <td class="num">${h.n_patterns || 1}</td><td class="num">${fmt(h.corr, 3)}</td>
             <td>${h.match_start || "—"} → ${h.match_end || "—"}</td>
             <td class="num ${tonePct(h.forward_5)}">${fmtPct(h.forward_5)}</td>
             <td class="num ${tonePct(h.forward_10)}">${fmtPct(h.forward_10)}</td></tr>`
        )
        .join("")}</tbody></table>
    </div>
    <div class="study-block">
      <h3>买卖分析</h3>
      <table><thead><tr><th>代码</th><th>倾向</th><th>状态</th><th class="num">收盘</th><th class="num">RSI</th><th>理由</th></tr></thead>
      <tbody>${rows
        .map((h) => {
          const why = (h.reasons || []).map((s) => `${s.source || ""} ${s.reason || ""}`).join("；") || "—";
          return `<tr data-code="${h.symbol}" data-start="${h.match_start || ""}" data-end="${h.match_end || ""}"><td>${h.symbol}</td><td>${h.stance || "—"}</td>
            <td>${h.regime || "—"}</td><td class="num">${fmt(h.close, 3)}</td>
            <td class="num">${fmt(h.rsi14, 1)}</td><td>${why}</td></tr>`;
        })
        .join("")}</tbody></table>
    </div>
    <div class="study-block">
      <h3>预测分析</h3>
      <table><thead><tr><th>代码</th><th>合成倾向</th><th class="num">8日合成</th><th class="num">形态类比</th><th>建议</th></tr></thead>
      <tbody>${rows
        .map(
          (h) =>
            `<tr data-code="${h.symbol}" data-start="${h.match_start || ""}" data-end="${h.match_end || ""}"><td>${h.symbol}</td><td>${h.bias || "—"}</td>
             <td class="num ${tonePct(h.blend_return_pct)}">${fmtPct(h.blend_return_pct)}</td>
             <td class="num ${tonePct(h.analog_return_pct)}">${fmtPct(h.analog_return_pct)}</td>
             <td>${h.suitable ? "可关注买入" : "暂不作为买点"} · ${h.why || ""}</td></tr>`
        )
        .join("")}</tbody></table>
    </div>`;
  $$("#sim-study tr[data-code]").forEach((tr) => {
    tr.style.cursor = "pointer";
    tr.onclick = () =>
      selectSymbol(tr.dataset.code, {
        drawer: true,
        matchStart: tr.dataset.start,
        matchEnd: tr.dataset.end,
        matchLabel: "相似区间",
      });
  });
}

function ymdLocal(v) {
  const d = v instanceof Date ? v : new Date(v);
  if (!isFinite(+d)) return "";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function simHighlightShape(start, end) {
  if (!start || !end) return [];
  return [
    {
      type: "rect",
      xref: "x",
      yref: "paper",
      x0: start,
      x1: end,
      y0: 0,
      y1: 1,
      fillcolor: "rgba(230,255,74,0.14)",
      line: { color: "#e6ff4a", width: 1 },
      layer: "above",
    },
  ];
}

function simBoxOverlay(start, end) {
  if (!start || !end) return { shapes: [], annotations: [] };
  return {
    shapes: simHighlightShape(start, end),
    annotations: [
      {
        x: end,
        xref: "x",
        y: 1,
        yref: "paper",
        text: "× 删除",
        showarrow: false,
        xanchor: "right",
        yanchor: "top",
        bgcolor: "rgba(18,20,14,0.88)",
        bordercolor: "#e6ff4a",
        borderwidth: 1,
        font: { color: "#e6ff4a", size: 11 },
        captureevents: true,
        name: "sim-box-x",
      },
    ],
  };
}

function applySimBoxOverlay() {
  const gd = $("#sim-kline");
  if (!gd || !window.Plotly || !gd.layout) return Promise.resolve();
  const overlay = Store.simHasBox
    ? simBoxOverlay($("#sim-start").value, $("#sim-end").value)
    : { shapes: [], annotations: [] };
  gd.__applyingSimShape = true;
  return Plotly.relayout(gd, {
    shapes: overlay.shapes,
    annotations: overlay.annotations,
    dragmode: Store.simBox ? "drawrect" : "pan",
  }).then(
    () => {
      gd.__applyingSimShape = false;
    },
    () => {
      gd.__applyingSimShape = false;
    }
  );
}

function clearSimBox() {
  Store.simHasBox = false;
  Store.simBox = false;
  $("#sim-box")?.classList.remove("on");
  return applySimBoxOverlay();
}

function onSimDatesChanged() {
  const start = $("#sim-start").value;
  const end = $("#sim-end").value;
  Store.simHasBox = !!(start && end);
  applySimBoxOverlay();
}

function inSimBoxRange(x) {
  const a = $("#sim-start").value;
  const b = $("#sim-end").value;
  if (!Store.simHasBox || !a || !b) return false;
  const t = ymdLocal(x);
  if (!t) return false;
  const lo = a < b ? a : b;
  const hi = a < b ? b : a;
  return t >= lo && t <= hi;
}

async function loadSimKline() {
  const el = $("#sim-kline");
  if (!el) return;
  try {
    const q = await api(`/api/quote/${symbol()}?start=${range().start}&end=${range().end}`);
    const bars = q.bars || [];
    const overlay = Store.simHasBox
      ? simBoxOverlay($("#sim-start").value, $("#sim-end").value)
      : { shapes: [], annotations: [] };
    await renderPlot(
      "sim-kline",
      withCandleFlow(bars),
      {
        ...overlay,
        dragmode: Store.simBox ? "drawrect" : "pan",
      }
    );
    el.__simBoxBound = false;
    bindSimBox(el);
  } catch (e) {
    banner(e.message, true);
  }
}

function bindSimBox(gd) {
  if (!gd || gd.__simBoxBound) return;
  gd.__simBoxBound = true;
  gd.on("plotly_relayout", (e) => {
    if (gd.__applyingSimShape) return;
    const keys = Object.keys(e || {});
    const drawn = keys.some((k) => k === "shapes" || k.startsWith("shapes["));
    if (!drawn) return;
    const list = (Array.isArray(e.shapes) && e.shapes.length ? e.shapes : null) || (gd.layout && gd.layout.shapes) || [];
    const last = list[list.length - 1];
    if (!last || last.x0 == null || last.x1 == null) return;
    const a = ymdLocal(last.x0);
    const b = ymdLocal(last.x1);
    if (!a || !b) return;
    const start = a < b ? a : b;
    const end = a < b ? b : a;
    if ($("#sim-start").value === start && $("#sim-end").value === end && Store.simHasBox && !Store.simBox) return;
    $("#sim-start").value = start;
    $("#sim-end").value = end;
    Store.simHasBox = true;
    Store.simBox = false;
    $("#sim-box").classList.remove("on");
    applySimBoxOverlay();
  });
  gd.on("plotly_click", (e) => {
    if (!Store.simHasBox || Store.simBox || gd.__applyingSimShape) return;
    const pt = (e.points && e.points[0]) || null;
    if (pt && inSimBoxRange(pt.x)) clearSimBox();
  });
  gd.on("plotly_clickannotation", (e) => {
    const name = (e.annotation && e.annotation.name) || "";
    const text = (e.annotation && e.annotation.text) || "";
    if (name === "sim-box-x" || String(text).includes("删除")) clearSimBox();
  });
}

function setSimBoxMode(on) {
  Store.simBox = on;
  $("#sim-box").classList.toggle("on", on);
  const gd = $("#sim-kline");
  if (!gd || !window.Plotly || !gd.layout) return;
  Plotly.relayout(gd, {
    dragmode: on ? "drawrect" : "pan",
    newshape: {
      fillcolor: "rgba(230,255,74,0.18)",
      line: { color: "#e6ff4a", width: 1 },
    },
  });
}

async function loadPatterns() {
  try {
    const data = await api("/api/patterns");
    renderPatternChips(data.items || []);
  } catch (_) {
    $("#sim-patterns").innerHTML = "";
  }
}

function renderPatternChips(items) {
  if (!items.length) {
    $("#sim-patterns").innerHTML = `<span class="hint">还没有保存的形态。框选或填好日期后写名称再点保存。</span>`;
    return;
  }
  $("#sim-patterns").innerHTML = items
    .map(
      (p) =>
        `<label class="chip check">
          <input type="checkbox" data-id="${p.id}" />
          <span>${p.name}</span>
          <span class="hint">${p.symbol} ${p.start}~${p.end}</span>
          <button type="button" class="chip-x" data-del="${p.id}" title="删除形态">×</button>
        </label>`
    )
    .join("");
  $$("#sim-patterns [data-del]").forEach((btn) => {
    btn.onclick = async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      try {
        await api(`/api/patterns/${btn.dataset.del}`, { method: "DELETE" });
        loadPatterns();
      } catch (e) {
        banner(e.message, true);
      }
    };
  });
}

async function saveCurrentPattern() {
  const name = ($("#sim-save-name").value || "").trim();
  if (!name) {
    banner("请先填写形态名称", true);
    return;
  }
  if (!$("#sim-start").value || !$("#sim-end").value) {
    banner("请先框选或填写形态区间再保存", true);
    return;
  }
  try {
    await api("/api/patterns", {
      method: "POST",
      body: JSON.stringify({
        name,
        symbol: symbol(),
        start: $("#sim-start").value,
        end: $("#sim-end").value,
      }),
    });
    $("#sim-save-name").value = "";
    banner(`已保存形态「${name}」`);
    loadPatterns();
  } catch (e) {
    banner(e.message, true);
  }
}

async function loadScreens() {
  try {
    const data = await api("/api/screens");
    Store.screenList = data.items || [];
    renderScreenChips(Store.screenList);
  } catch (_) {
    Store.screenList = [];
    $("#scr-saved").innerHTML = "";
  }
}

function renderScreenChips(items) {
  if (!items.length) {
    $("#scr-saved").innerHTML = `<span class="hint">还没有保存的条件。设好规则后填写名称，选动态或静态再保存。</span>`;
    syncScreenAddRow([]);
    return;
  }
  $("#scr-saved").innerHTML = items
    .map((s) => {
      const on = Store.screenIds.has(s.id) ? "on" : "";
      const mode = s.mode === "static" ? "静态" : "动态";
      return `<span class="chip ${on}" data-sid="${s.id}">${s.name} · ${mode}
        <button type="button" class="chip-x" data-sdel="${s.id}" title="删除条件">×</button></span>`;
    })
    .join("");
  $$("#scr-saved [data-sid]").forEach((el) => {
    el.onclick = (ev) => {
      if (ev.target.dataset.sdel) return;
      toggleSavedScreen(el.dataset.sid);
    };
  });
  $$("#scr-saved [data-sdel]").forEach((btn) => {
    btn.onclick = async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      try {
        await api(`/api/screens/${btn.dataset.sdel}`, { method: "DELETE" });
        Store.screenIds.delete(btn.dataset.sdel);
        delete Store.screenCache[btn.dataset.sdel];
        if (Store.screenId === btn.dataset.sdel) Store.screenId = null;
        if (Store.screenFocusId === btn.dataset.sdel) Store.screenFocusId = null;
        await loadScreens();
        await refreshSelectedScreens();
      } catch (e) {
        banner(e.message, true);
      }
    };
  });
}

function fillScreenForm(item) {
  Store.screenId = item.id;
  Store.screenMode = item.mode;
  $("#scr-univ").value = item.universe || $("#scr-univ").value;
  $("#scr-mode").value = item.mode || "dynamic";
  $("#scr-save-name").value = item.name || "";
  $("#scr-conds").innerHTML = "";
  (item.conditions || []).forEach((c) => addCondition(c));
}

async function toggleSavedScreen(sid) {
  if (Store.screenIds.has(sid)) {
    Store.screenIds.delete(sid);
    if (Store.screenId === sid) Store.screenId = null;
    if (Store.screenFocusId === sid) Store.screenFocusId = null;
    renderScreenChips(Store.screenList);
    await refreshSelectedScreens();
    return;
  }
  banner("");
  showBusy(true, "载入保存的条件…");
  try {
    const item = await api(`/api/screens/${sid}`);
    Store.screenIds.add(sid);
    Store.screenCache[sid] = item;
    Store.screenId = sid;
    if (item.mode === "static" || item.frozen) Store.screenFocusId = sid;
    fillScreenForm(item);
    renderScreenChips(Store.screenList);
    await refreshSelectedScreens();
  } catch (e) {
    banner(e.message, true);
  } finally {
    showBusy(false);
  }
}

function syncScreenAddRow(items) {
  const add = $("#scr-hit-add");
  if (!add) return;
  const selectedStatic = (items || []).filter(
    (s) => Store.screenIds.has(s.id) && (s.mode === "static" || s.frozen)
  );
  add.classList.toggle("hidden", !selectedStatic.length);
  if (!selectedStatic.length) {
    Store.screenFocusId = null;
    return;
  }
  if (!selectedStatic.some((s) => s.id === Store.screenFocusId)) Store.screenFocusId = selectedStatic[0].id;
  const focus = selectedStatic.find((s) => s.id === Store.screenFocusId) || selectedStatic[0];
  Store.screenFocusId = focus.id;
  $("#scr-add-target").textContent = `加入静态「${focus.name}」`;
}

async function refreshSelectedScreens() {
  const ids = [...Store.screenIds];
  if (!ids.length) {
    $("#scr-table").innerHTML = "";
    syncScreenAddRow([]);
    return;
  }
  const blocks = [];
  for (const sid of ids) {
    let item = Store.screenCache[sid];
    if (!item) {
      try {
        item = await api(`/api/screens/${sid}`);
        Store.screenCache[sid] = item;
      } catch (e) {
        banner(e.message, true);
        continue;
      }
    }
    blocks.push(item);
  }
  renderScreenTables(blocks);
  syncScreenAddRow(blocks);
}

function screenBlockHtml(r) {
  const frozen = !!(r.frozen || r.mode === "static");
  const title = r.name ? `${r.name} · ${frozen ? "静态" : "动态"}` : frozen ? "静态名单" : "本次选股";
  const extra = frozen ? `<th></th>` : "";
  const note = frozen
    ? (r.hits || []).length
      ? `静态名单 ${r.count || (r.hits || []).length} 只，不会随行情变化。点中该名称后可在上方加入或在右侧删除。`
      : "静态名单为空。点中该名称后，用上方搜索或「加入当前股票」添加。"
    : `扫描 ${r.scanned ?? "—"} 只，跳过 ${r.skipped ?? "—"} 只，命中 ${r.count} 只。`;
  const sid = r.id || "";
  return `
    <div class="screen-block" data-sid="${sid}">
      <h3>${title}</h3>
      <p class="hint">${note}</p>
      <table>
        <thead><tr><th>代码</th><th>名称</th><th class="num">收盘</th><th class="num">涨跌幅</th>
        <th class="num">RSI</th><th class="num">量比</th><th class="num">换手</th><th>MACD</th><th>均线</th><th class="num">PE</th><th class="num">20日涨跌</th>${extra}</tr></thead>
        <tbody>
          ${(r.hits || [])
            .map((h) => {
              const del = frozen && sid
                ? `<td><button type="button" class="btn row-del" data-sid="${sid}" data-sym="${h.symbol}">删除</button></td>`
                : frozen
                  ? "<td></td>"
                  : "";
              return `<tr data-code="${h.symbol}"><td>${h.symbol}</td><td>${h.name || ""}</td>
                   <td class="num">${fmt(h.close, 3)}</td>
                   <td class="num ${tonePct(h.pct_chg)}">${fmtPct(h.pct_chg)}</td>
                   <td class="num">${fmt(h.rsi14, 1)}</td>
                   <td class="num">${fmt(h.vol_ratio)}</td>
                   <td class="num">${h.turnover == null ? "—" : fmt(h.turnover) + "%"}</td>
                   <td>${h.macd_cross === "golden" ? "金叉" : h.macd_cross === "dead" ? "死叉" : "—"}</td>
                   <td>${h.ma_align === "bull" ? "多头" : h.ma_align === "bear" ? "空头" : "—"}</td>
                   <td class="num">${fmt(h.pe, 1)}</td>
                   <td class="num ${tonePct(h.pct_20)}">${fmtPct(h.pct_20)}</td>${del}</tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function renderScreenTables(items) {
  if (!items.length) {
    $("#scr-table").innerHTML = "";
    return;
  }
  Store.lastScreenHits = items[0].hits || [];
  $("#scr-table").innerHTML = items.map(screenBlockHtml).join("");
  bindScreenTable($("#scr-table"));
  $$("#scr-table .screen-block").forEach((block) => {
    const sid = block.dataset.sid;
    const item = items.find((x) => x.id === sid);
    if (!sid || !item || !(item.mode === "static" || item.frozen)) return;
    const head = block.querySelector("h3");
    if (!head) return;
    head.style.cursor = "pointer";
    head.title = "点这里指定加入哪份静态名单";
    head.onclick = () => {
      Store.screenFocusId = sid;
      syncScreenAddRow(items);
    };
  });
}

function renderScreenTable(r, opts = {}) {
  const frozen = opts.frozen || r.frozen;
  renderScreenTables([{ ...r, frozen, mode: frozen ? "static" : r.mode || "dynamic" }]);
}

function bindScreenTable(root) {
  $$("tr[data-code]", root).forEach((tr) => {
    tr.style.cursor = "pointer";
    tr.onclick = (ev) => {
      if (ev.target.closest(".row-del")) return;
      selectSymbol(tr.dataset.code, { drawer: true });
    };
  });
  $$(".row-del", root).forEach((btn) => {
    btn.onclick = async (ev) => {
      ev.stopPropagation();
      const sid = btn.dataset.sid;
      if (!sid) return;
      try {
        const out = await api(`/api/screens/${sid}/hits/${btn.dataset.sym}`, { method: "DELETE" });
        Store.screenCache[sid] = { ...out.item, frozen: true, mode: "static" };
        await refreshSelectedScreens();
        loadScreens();
      } catch (e) {
        banner(e.message, true);
      }
    };
  });
}

async function addSymbolToStatic(code) {
  const sid = Store.screenFocusId;
  const item = sid ? Store.screenCache[sid] : null;
  const selectedStatic = !!(sid && Store.screenIds.has(sid) && item && (item.mode === "static" || item.frozen));
  if (!selectedStatic) {
    banner("请先点选一个静态条件，未选中的和动态条件不能加股", true);
    return;
  }
  const next = String(code || "").trim();
  if (!next) {
    banner("请输入要加入的股票代码", true);
    return;
  }
  showBusy(true, "加入静态名单…");
  try {
    const out = await api(`/api/screens/${sid}/hits`, {
      method: "POST",
      body: JSON.stringify({ symbol: next }),
    });
    Store.screenCache[sid] = { ...out.item, frozen: true, mode: "static" };
    Store.screenFocusId = sid;
    $("#scr-add-symbol").value = "";
    banner(`已加入「${out.item.name}」`);
    await refreshSelectedScreens();
    loadScreens();
  } catch (e) {
    banner(e.message, true);
  } finally {
    showBusy(false);
  }
}

async function saveCurrentScreen() {
  const name = ($("#scr-save-name").value || "").trim();
  if (!name) {
    banner("请先填写条件名称", true);
    return;
  }
  if (!assertConditionsOk()) return;
  const mode = $("#scr-mode").value === "static" ? "static" : "dynamic";
  try {
    const out = await api("/api/screens", {
      method: "POST",
      body: JSON.stringify({
        name,
        mode,
        universe: $("#scr-univ").value,
        conditions: readConditions(),
        hits: [],
        limit: 50,
      }),
    });
    banner(`已保存${mode === "static" ? "静态" : "动态"}条件「${name}」`);
    if (out.item && out.item.id) {
      Store.screenIds.add(out.item.id);
      Store.screenCache[out.item.id] = { ...out.item, frozen: mode === "static" };
      Store.screenId = out.item.id;
      if (mode === "static") Store.screenFocusId = out.item.id;
    }
    await loadScreens();
    await refreshSelectedScreens();
  } catch (e) {
    banner(e.message, true);
  }
}

const SCREEN_FIELDS = [];
const PRESETS = [
  { name: "RSI 超卖", conds: [{ field: "rsi14", op: "<", value: 30 }] },
  { name: "MACD 金叉", conds: [{ field: "macd_cross", op: "=", value: "golden" }] },
  { name: "均线多头", conds: [{ field: "ma_align", op: "=", value: "bull" }] },
  {
    name: "放量站上 MA20",
    conds: [
      { field: "vol_ratio", op: ">", value: 1.5 },
      { field: "close_vs_sma20", op: "=", value: "above" },
    ],
  },
  { name: "贴近布林下轨", conds: [{ field: "bb_pct_b", op: "<", value: 0.05 }] },
  { name: "SuperTrend 多头", conds: [{ field: "st_dir", op: "=", value: "bull" }] },
  { name: "RSI2 超卖", conds: [{ field: "rsi2", op: "<", value: 10 }] },
  {
    name: "低 PE 且 20 日转强",
    conds: [
      { field: "pe", op: "<", value: 25 },
      { field: "pe", op: ">", value: 0 },
      { field: "pct_20", op: ">", value: 5 },
    ],
  },
  { name: "底部首板涨停/大涨", conds: [{ field: "first_limit_up", op: "=", value: "yes" }] },
  { name: "大阳线缩量回踩", conds: [{ field: "bull_pullback", op: "=", value: "yes" }] },
  { name: "底部放量启动", conds: [{ field: "vol_breakout", op: "=", value: "yes" }] },
  {
    name: "低估值",
    conds: [
      { field: "pe", op: ">", value: 0 },
      { field: "pe", op: "<", value: 20 },
      { field: "pb", op: "<", value: 2 },
    ],
  },
  {
    name: "绩优低估值",
    conds: [
      { field: "pe", op: ">", value: 0 },
      { field: "pe", op: "<", value: 20 },
      { field: "pb", op: "<", value: 3 },
      { field: "roe", op: ">", value: 10 },
      { field: "net_profit_yoy", op: ">", value: 0 },
    ],
  },
];

const ENUM_FIELDS = new Set([
  "macd_cross",
  "ma_align",
  "close_vs_sma20",
  "st_dir",
  "first_limit_up",
  "bull_pullback",
  "vol_breakout",
]);
const ENUM_LABEL = {
  golden: "金叉",
  dead: "死叉",
  bull: "多头",
  bear: "空头",
  above: "上方",
  below: "下方",
  yes: "是",
  no: "否",
};

function fieldLabel(id) {
  const f = SCREEN_FIELDS.find((x) => x.id === id);
  return (f && f.label) || id;
}

function tightenLo(cur, val, inclusive) {
  if (!cur) return [val, inclusive];
  if (val > cur[0]) return [val, inclusive];
  if (val < cur[0]) return cur;
  return [cur[0], cur[1] && inclusive];
}

function tightenHi(cur, val, inclusive) {
  if (!cur) return [val, inclusive];
  if (val < cur[0]) return [val, inclusive];
  if (val > cur[0]) return cur;
  return [cur[0], cur[1] && inclusive];
}

function findConditionConflicts(conditions) {
  const reasons = [];
  const fields = new Set();
  const byField = {};
  (conditions || []).forEach((c) => {
    if (!c.field) return;
    (byField[c.field] || (byField[c.field] = [])).push(c);
  });
  Object.keys(byField).forEach((field) => {
    const items = byField[field];
    const label = fieldLabel(field);
    if (ENUM_FIELDS.has(field)) {
      const equals = [];
      items.forEach((c) => {
        const raw = String(c.value ?? "").trim();
        if (!raw) return;
        if ((c.op || "=") !== "=") {
          reasons.push(`${label} 是分类字段，只能用「=」`);
          fields.add(field);
          return;
        }
        equals.push(raw);
      });
      const uniq = [...new Set(equals)];
      if (uniq.length > 1) {
        reasons.push(`${label} 不能同时为 ${uniq.map((v) => ENUM_LABEL[v] || v).join("、")}`);
        fields.add(field);
      }
      return;
    }
    let lo = null;
    let hi = null;
    const eqs = [];
    items.forEach((c) => {
      const raw = String(c.value ?? "").trim();
      const val = Number(c.value);
      if (!raw || !Number.isFinite(val)) return;
      const op = c.op || ">";
      if (op === ">") lo = tightenLo(lo, val, false);
      else if (op === ">=") lo = tightenLo(lo, val, true);
      else if (op === "<") hi = tightenHi(hi, val, false);
      else if (op === "<=") hi = tightenHi(hi, val, true);
      else if (op === "=") eqs.push(val);
    });
    const uniqEq = [...new Set(eqs)];
    if (uniqEq.length > 1) {
      reasons.push(`${label} 不能同时等于 ${uniqEq.join("、")}`);
      fields.add(field);
      return;
    }
    if (uniqEq.length === 1) {
      const v = uniqEq[0];
      if (lo && (v < lo[0] || (v === lo[0] && !lo[1]))) {
        reasons.push(`${label} 等于 ${v} 与下界冲突`);
        fields.add(field);
      }
      if (hi && (v > hi[0] || (v === hi[0] && !hi[1]))) {
        reasons.push(`${label} 等于 ${v} 与上界冲突`);
        fields.add(field);
      }
    }
    if (lo && hi && (lo[0] > hi[0] || (lo[0] === hi[0] && !(lo[1] && hi[1])))) {
      const loS = `${lo[1] ? "≥" : ">"} ${lo[0]}`;
      const hiS = `${hi[1] ? "≤" : "<"} ${hi[0]}`;
      reasons.push(`${label} 同时要求 ${loS} 且 ${hiS}，没有交集`);
      fields.add(field);
    }
  });
  return { reasons, fields };
}

function markConditionConflicts() {
  const { reasons, fields } = findConditionConflicts(readConditions());
  $$("#scr-conds .cond-row").forEach((row) => {
    const field = row.querySelector("select") && row.querySelector("select").value;
    row.classList.toggle("conflict", fields.has(field));
  });
  const el = $("#scr-conflict");
  if (el) el.textContent = reasons.length ? `条件冲突：${reasons.join("；")}` : "";
  return reasons;
}

function assertConditionsOk() {
  const conds = readConditions();
  const missing = conds.filter((c) => !String(c.value ?? "").trim()).map((c) => fieldLabel(c.field));
  if (missing.length) {
    banner(`请填写条件阈值：${missing.join("、")}`, true);
    markConditionConflicts();
    return false;
  }
  const reasons = markConditionConflicts();
  if (reasons.length) {
    banner(`条件冲突：${reasons.join("；")}`, true);
    return false;
  }
  return true;
}

function addCondition(prefill) {
  const fields = SCREEN_FIELDS.length
    ? SCREEN_FIELDS
    : [
        { id: "rsi14", label: "RSI(14)", type: "number" },
        { id: "macd_cross", label: "MACD 交叉", type: "enum", options: ["golden", "dead"] },
      ];
  const row = document.createElement("div");
  row.className = "cond-row";
  const sel = document.createElement("select");
  fields.forEach((f) => {
    const o = document.createElement("option");
    o.value = f.id;
    o.textContent = f.label;
    sel.appendChild(o);
  });
  const op = document.createElement("select");
  [">", ">=", "<", "<=", "="].forEach((x) => {
    const o = document.createElement("option");
    o.value = x;
    o.textContent = x;
    op.appendChild(o);
  });
  const val = document.createElement("input");
  val.placeholder = "阈值";
  const del = document.createElement("button");
  del.className = "btn";
  del.textContent = "删";
  del.onclick = () => {
    row.remove();
    markConditionConflicts();
  };
  if (prefill) {
    sel.value = prefill.field;
    op.value = prefill.op;
    val.value = prefill.value;
  }
  [sel, op, val].forEach((el) => el.addEventListener("change", markConditionConflicts));
  val.addEventListener("input", markConditionConflicts);
  row.append(sel, op, val, del);
  $("#scr-conds").appendChild(row);
  markConditionConflicts();
}

function readConditions() {
  return $$("#scr-conds .cond-row").map((row) => {
    const [field, op, val] = row.querySelectorAll("select, input");
    return { field: field.value, op: op.value, value: val.value };
  });
}

async function runScreen() {
  banner("");
  if (!assertConditionsOk()) return;
  Store.screenIds.clear();
  Store.screenId = null;
  Store.screenMode = null;
  Store.screenFocusId = null;
  startBusyPulse("按条件过滤样本池（未缓存的股票会现场拉取）…");
  try {
    const r = await api("/api/screen", {
      method: "POST",
      body: JSON.stringify({
        universe: $("#scr-univ").value,
        conditions: readConditions(),
        limit: 50,
      }),
    });
    renderScreenChips(Store.screenList);
    syncScreenAddRow([]);
    renderScreenTable(r, { frozen: false });
  } catch (e) {
    banner(e.message, true);
  } finally {
    stopBusyPulse();
  }
}

function auctionPathTraces(path) {
  const vols = path.map((p) => p.volume);
  return [
    {
      x: path.map((p) => p.time),
      y: path.map((p) => p.price),
      name: "价格",
      mode: "lines+markers",
      line: { color: "#e6ff4a", width: 2 },
      marker: { size: 8 },
    },
    {
      x: path.map((p) => p.time),
      y: vols.map((v) => (v == null ? null : Number(v) / 1e4)),
      name: "量(万)",
      type: "bar",
      yaxis: "y2",
      marker: { color: "rgba(230,255,74,0.32)" },
      customdata: vols.map(fmtVol),
      hovertemplate: "%{x}<br>量 %{customdata}<extra></extra>",
    },
  ];
}

function renderAuctionPath(id, path) {
  const el = document.getElementById(id);
  if (!path || !path.length) {
    if (el && el.data) Plotly.purge(el);
    if (el) el.innerHTML = "";
    return;
  }
  renderPlot(
    id,
    auctionPathTraces(path),
    {
      yaxis: { ...PLOT.yaxis, title: "价格" },
      yaxis2: { overlaying: "y", side: "right", showgrid: false, title: "量" },
      xaxis: { title: "时间" },
      margin: { t: 16, r: 52, b: 40, l: 52 },
    },
    false
  );
}

async function runAuction() {
  const code = symbol();
  if (!code) return banner("请先输入股票代码", true);
  startBusyPulse("正在分析早盘/尾盘竞价…");
  try {
    refreshSelectedLive(true).catch(() => {});
    api(`/api/live/minutes/${encodeURIComponent(code)}?ndays=1`).catch(() => {});
    const r = await api(`/api/auction/${encodeURIComponent(code)}`);
    const o = r.opening || {};
    const c = r.closing || {};
    const h = r.history || {};
    stats($("#auc-open-head"), [
      { value: `${r.symbol} ${r.name || ""}`, label: o.session || "早盘集合竞价" },
      { value: o.date || "—", label: "日期" },
      { value: fmt(o.price, 3), label: "竞价成交价", tone: tonePct(o.gap_pct) },
      { value: fmtPct(o.gap_pct), label: "相对昨收", tone: tonePct(o.gap_pct) },
      { value: o.bias || "—", label: "开盘定性", tone: tonePct(o.gap_pct) },
      { value: fmtVol(o.volume), label: "竞价量" },
    ]);
    $("#auc-open-note").textContent = o.why || o.source || "";
    renderAuctionPath("auc-open-chart", o.path);
    stats($("#auc-close-head"), [
      { value: c.date || "—", label: c.session || "尾盘集合竞价" },
      { value: fmt(c.price, 3), label: "竞价收盘价", tone: tonePct(c.auc_pct) },
      { value: fmtPct(c.auc_pct), label: "相对 14:56", tone: tonePct(c.auc_pct) },
      { value: fmtPct(c.vs_open_pct), label: "相对开盘", tone: tonePct(c.vs_open_pct) },
      { value: c.bias || "—", label: "尾盘定性", tone: tonePct(c.auc_pct) },
      { value: fmtVol(c.volume), label: "尾盘量" },
    ]);
    $("#auc-close-note").textContent = c.why || "";
    renderAuctionPath("auc-close-chart", c.path);
    stats($("#auc-hist"), [
      { value: h.days || "—", label: "统计天数" },
      { value: fmtPct(h.avg_gap_pct), label: "平均高开幅度", tone: tonePct(h.avg_gap_pct) },
      { value: `${h.gap_up ?? "—"} / ${h.gap_down ?? "—"} / ${h.gap_flat ?? "—"}`, label: "高开 / 低开 / 平开" },
      { value: h.gap_up_then_red ?? "—", label: "高开后收涨天数" },
      { value: h.close_up_vs_open ?? "—", label: "收盘高于开盘天数" },
    ]);
    const rows = r.sessions || [];
    $("#auc-table").innerHTML = rows.length
      ? `<table>
          <thead><tr><th>日期</th><th>开盘定性</th><th class="num">开盘价</th><th class="num">高开%</th>
          <th>尾盘定性</th><th class="num">收盘价</th><th class="num">相对14:56</th><th class="num">相对开盘</th></tr></thead>
          <tbody>${rows
            .slice()
            .reverse()
            .map(
              (s) => `<tr>
                <td>${s.date}</td>
                <td>${s.open_bias || "—"}</td>
                <td class="num ${tonePct(s.open_gap_pct)}">${fmt(s.open_price, 3)}</td>
                <td class="num ${tonePct(s.open_gap_pct)}">${fmtPct(s.open_gap_pct)}</td>
                <td>${s.close_bias || "—"}</td>
                <td class="num ${tonePct(s.close_vs_cont_pct)}">${fmt(s.close_price, 3)}</td>
                <td class="num ${tonePct(s.close_vs_cont_pct)}">${fmtPct(s.close_vs_cont_pct)}</td>
                <td class="num ${tonePct(s.close_vs_open_pct)}">${fmtPct(s.close_vs_open_pct)}</td>
              </tr>`
            )
            .join("")}</tbody></table>`
      : "<p class=\"hint\">最近交易日还没有分钟竞价明细，已用日线开收盘作为竞价结果。</p>";
    $("#auc-notes").textContent = (r.notes || []).join(" ");
    banner(`${r.symbol} ${r.name || ""} 竞价分析完成`);
  } catch (e) {
    banner(e.message, true);
  } finally {
    stopBusyPulse();
  }
}

function setView(id) {
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${id}`));
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === id));
  if (id === "home") loadHome();
  if (id === "watch") renderWatchView();
  if (id === "calendar") loadCalendar();
  if (id === "similar") {
    loadSimKline();
    loadPatterns();
  }
  if (id === "screen") {
    loadScreens().then(() => {
      if (Store.screenIds.size) refreshSelectedScreens();
    });
  }
  if (id === "backtest") {
    refreshBacktestSelectors();
    syncBacktestSourceUI();
  }
  if (id === "auction" && symbol()) runAuction();
}

function calShift(delta) {
  let y = Store.calYear;
  let m = Store.calMonth + delta;
  while (m < 1) {
    m += 12;
    y -= 1;
  }
  while (m > 12) {
    m -= 12;
    y += 1;
  }
  Store.calYear = y;
  Store.calMonth = m;
  loadCalendar();
}

async function loadCalendar() {
  const y = Store.calYear;
  const m = Store.calMonth;
  $("#cal-title").textContent = `${y}年${m}月 · 题材日历`;
  try {
    const data = await api(`/api/calendar?year=${y}&month=${m}&live=1`);
    const themes = data.month_themes || {};
    const reports = data.report_windows || [];
    $("#cal-month-themes").innerHTML = `
      <div class="cal-theme-row">
        <strong>本月适宜关注</strong>
        ${(themes.themes || []).map((t) => `<span class="tag">${t}</span>`).join("") || "<span class='hint'>—</span>"}
      </div>
      <p class="hint">${themes.note || ""}</p>
      ${
        reports.length
          ? `<div class="cal-theme-row"><strong>财报窗口</strong>${reports
              .map((r) => `<span class="tag report">${r.name} · ${r.peak || ""}</span>`)
              .join("")}</div>`
          : ""
      }
      <p class="hint">${data.disclaimer || ""}</p>`;

    const firstWeekday = (data.days && data.days[0] && data.days[0].weekday) || 0;
    const weekLabels = ["一", "二", "三", "四", "五", "六", "日"];
    let cells = weekLabels.map((w) => `<div class="cal-dow">${w}</div>`).join("");
    for (let i = 0; i < firstWeekday; i++) cells += `<div class="cal-cell empty"></div>`;
    (data.days || []).forEach((d) => {
      const flags = d.flags || {};
      const cls = [
        "cal-cell",
        flags.has_major ? "major" : "",
        flags.has_event ? "has-event" : "",
        flags.has_report ? "report" : "",
        Store.calSelected === d.date ? "on" : "",
      ]
        .filter(Boolean)
        .join(" ");
      const dots = [];
      if (flags.has_major) dots.push('<i class="dot major"></i>');
      else if (flags.has_event) dots.push('<i class="dot"></i>');
      if (flags.has_report) dots.push('<i class="dot report"></i>');
      cells += `<button type="button" class="${cls}" data-date="${d.date}">
        <span class="num">${d.day}</span>
        <span class="dots">${dots.join("")}</span>
        <span class="ev">${(d.events || [])
          .slice(0, 1)
          .map((e) => e.title)
          .join("")}</span>
      </button>`;
    });
    $("#cal-grid").innerHTML = cells;
    $$("#cal-grid [data-date]").forEach((btn) => {
      btn.onclick = () => selectCalDay(btn.dataset.date);
    });
    if (!Store.calSelected) {
      const today = new Date().toISOString().slice(0, 10);
      const hit = (data.days || []).find((d) => d.date === today) || (data.days || [])[0];
      if (hit) selectCalDay(hit.date);
    } else if ((data.days || []).some((d) => d.date === Store.calSelected)) {
      selectCalDay(Store.calSelected);
    }
  } catch (e) {
    banner(e.message, true);
  }
}

async function selectCalDay(dateStr) {
  Store.calSelected = dateStr;
  $$("#cal-grid [data-date]").forEach((btn) => btn.classList.toggle("on", btn.dataset.date === dateStr));
  const box = $("#cal-detail");
  box.innerHTML = `<p class="hint">载入 ${dateStr}…</p>`;
  try {
    const d = await api(`/api/calendar/day?date=${encodeURIComponent(dateStr)}&live=1`);
    const evHtml = (d.events || []).length
      ? (d.events || [])
          .map(
            (e) =>
              `<article class="cal-event ${e.level || ""}">
                <div class="t">${e.level === "major" ? "★ " : ""}${e.title}</div>
                <div class="meta">${(e.themes || []).join(" · ")}</div>
                <p>${e.note || ""}</p>
              </article>`
          )
          .join("")
      : `<p class="hint">当日无内置重大事件标记。</p>`;
    const liveHtml = (d.live_events || []).length
      ? `<h3 class="section-title">外接资讯</h3>${(d.live_events || [])
          .map(
            (e) =>
              `<article class="cal-event live ${e.level || ""}">
                <div class="t">${e.level === "major" ? "★ " : ""}${e.title}</div>
                <div class="meta">${e.source || ""} ${(e.themes || []).join(" · ")}</div>
                <p>${e.note || ""}</p>
              </article>`
          )
          .join("")}`
      : `<p class="hint">暂无外接资讯（网络不可用或当日无匹配快讯）。</p>`;
    const themes = d.month_themes || {};
    box.innerHTML = `
      <h2 class="section-title">${d.date}</h2>
      <div class="cal-theme-row">${(themes.themes || []).map((t) => `<span class="tag">${t}</span>`).join("")}</div>
      <p class="hint">${themes.note || ""}</p>
      ${(d.report_windows || [])
        .map((r) => `<p class="hint">财报：${r.name} · ${r.peak || ""} — ${r.note || ""}</p>`)
        .join("")}
      <h3 class="section-title">内置事件</h3>
      ${evHtml}
      ${liveHtml}
      <p class="hint">${d.disclaimer || ""}</p>`;
  } catch (e) {
    box.innerHTML = `<p class="alert-empty">${e.message}</p>`;
  }
}

function openSymbol(code) {
  selectSymbol(code, { drawer: true });
}

function sparkSvg(values) {
  if (!values || values.length < 2) return "";
  const nums = values.map(Number).filter((v) => Number.isFinite(v));
  if (nums.length < 2) return "";
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const w = 72;
  const h = 28;
  const span = max - min || 1;
  const pts = nums
    .map((v, i) => {
      const x = (i / (nums.length - 1)) * w;
      const y = h - ((v - min) / span) * (h - 2) - 1;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const up = nums[nums.length - 1] >= nums[0];
  return `<svg viewBox="0 0 ${w} ${h}" class="spark ${up ? "up" : "down"}"><polyline points="${pts}" /></svg>`;
}

function withLive(s) {
  const live = Store.live.by[s.symbol];
  if (!live || live.price == null) return { ...s, _live: false };
  return {
    ...s,
    close: live.price,
    pct_chg: live.pct_chg != null ? live.pct_chg : s.pct_chg,
    name: live.name || s.name,
    _live: true,
  };
}

function stockCard(raw) {
  const s = withLive(raw);
  const chgCls = tonePct(s.pct_chg);
  const watched = isWatched(s.symbol);
  const tags = [
    s._live ? "现价" : null,
    s.limit_up ? "涨停" : null,
    s.industry && s.industry !== "未分类" ? s.industry : null,
    ...(s.concepts || []).slice(0, 2),
    s.stance,
    s.alert === "buy" ? "偏多提醒" : s.alert === "sell" ? "偏空提醒" : null,
  ]
    .filter(Boolean)
    .map((t) => {
      const cls =
        t === "现价"
          ? "watch"
          : t === "涨停"
            ? "limit"
            : t === "偏多提醒" || t === "偏多"
              ? "buy"
              : t === "偏空提醒" || t === "偏空"
                ? "sell"
                : "";
      return `<span class="tag ${cls}">${t}</span>`;
    })
    .join("");
  return `<article class="stock-card ${Store.selected === s.symbol ? "selected" : ""} ${s.limit_up ? "limit-up" : ""}" data-code="${s.symbol}">
    <div class="row">
      <div>
        <div class="code">${s._live ? '<span class="live-dot"></span>' : ""}${s.symbol}</div>
        <div class="name">${s.name || ""}</div>
      </div>
      <button type="button" class="card-star ${watched ? "on" : ""}" data-star="${s.symbol}">${watched ? "★" : "☆"}</button>
    </div>
    <div class="row" style="margin-top:6px">
      <div>
        <div class="px ${chgCls}">${fmt(s.close, 3)}</div>
        <div class="chg ${chgCls}">${fmtPct(s.pct_chg)}</div>
      </div>
      ${sparkSvg(s.spark)}
    </div>
    <div class="tags">${tags}</div>
  </article>`;
}

function bindCardEvents(root) {
  $$(".stock-card", root).forEach((card) => {
    card.onclick = (ev) => {
      if (ev.target.closest("[data-star]")) return;
      selectSymbol(card.dataset.code, { drawer: true });
    };
  });
  $$("[data-star]", root).forEach((btn) => {
    btn.onclick = (ev) => {
      ev.stopPropagation();
      toggleWatch(btn.dataset.star);
    };
  });
}

function filteredStocks() {
  const { cat, q } = Store.deskFilter;
  const query = (q || "").trim().toLowerCase();
  return Store.stocks.filter((s) => {
    if (query) {
      const hay = `${s.symbol} ${s.name || ""} ${s.industry || ""} ${(s.concepts || []).join(" ")}`.toLowerCase();
      if (!hay.includes(query) && !s.symbol.startsWith(query)) return false;
    }
    if (!cat || cat === "all") return true;
    if (cat === "limit_up") return !!s.limit_up;
    if (cat.startsWith("ind:")) return (s.industry || "未分类") === cat.slice(4);
    if (cat.startsWith("con:")) return (s.concepts || []).includes(cat.slice(4));
    if (cat === "watch") return isWatched(s.symbol);
    if (cat === "buy") return s.alert === "buy" || s.stance_id === "buy";
    if (cat === "sell") return s.alert === "sell" || s.stance_id === "sell";
    if (cat === "bull") return s.stance === "偏多";
    if (cat === "bear") return s.stance === "偏空";
    if (cat === "hold") return s.stance === "观望";
    if (cat === "oversold") return s.rsi_zone === "超卖";
    if (cat === "overbought") return s.rsi_zone === "超买";
    if (cat === "up") return s.pct_chg > 0;
    if (cat === "down") return s.pct_chg < 0;
    if (cat === "sh") return s.board === "沪市主板";
    if (cat === "sz") return s.board === "深市主板";
    if (cat === "sme") return s.board === "中小板";
    if (cat === "p5") return s.band === "5元以下";
    if (cat === "p10") return s.band === "5–10元";
    if (cat === "p15") return s.band === "10–15元";
    if (cat === "p20") return s.band === "15–20元";
    return true;
  });
}

function renderDeskModes() {
  const modes = [
    ["industry", "按行业"],
    ["concept", "按概念"],
    ["basic", "倾向/价位"],
  ];
  const el = $("#desk-filter-modes");
  if (!el) return;
  el.innerHTML = modes
    .map(
      ([id, label]) =>
        `<button class="chip ${Store.deskFilter.mode === id ? "on" : ""}" data-mode="${id}">${label}</button>`
    )
    .join("");
  $$("#desk-filter-modes [data-mode]").forEach((btn) => {
    btn.onclick = () => {
      Store.deskFilter.mode = btn.dataset.mode;
      Store.deskFilter.cat = "all";
      Store.deskPage = 1;
      Store.groupShown = {};
      Store.deskGroupKey = null;
      renderDeskModes();
      renderDeskFilters();
      renderDeskGrid();
      renderChangeTree();
    };
  });
}

function renderDeskFilters() {
  const mode = Store.deskFilter.mode || "basic";
  let cats;
  if (mode === "industry") {
    const inds = Object.entries(Store.summary?.industries || {});
    cats = [["all", "全部行业"], ["limit_up", `涨停 ${Store.summary?.limit_up || 0}`], ...inds.map(([k, n]) => [`ind:${k}`, `${k} ${n}`])];
  } else if (mode === "concept") {
    const cons = Object.entries(Store.summary?.concepts || {});
    cats = [["all", "全部概念"], ["limit_up", `涨停 ${Store.summary?.limit_up || 0}`], ...cons.map(([k, n]) => [`con:${k}`, `${k} ${n}`])];
  } else {
    cats = [
      ["all", "全部"],
      ["limit_up", `涨停 ${Store.summary?.limit_up || 0}`],
      ["watch", "自选"],
      ["buy", "偏多提醒"],
      ["sell", "偏空提醒"],
      ["bull", "偏多"],
      ["hold", "观望"],
      ["bear", "偏空"],
      ["oversold", "超卖"],
      ["overbought", "超买"],
      ["up", "上涨"],
      ["down", "下跌"],
      ["sh", "沪市主板"],
      ["sz", "深市主板"],
      ["sme", "中小板"],
      ["p5", "5元以下"],
      ["p10", "5–10元"],
      ["p15", "10–15元"],
      ["p20", "15–20元"],
    ];
  }
  $("#desk-filters").innerHTML = cats
    .map(([id, label]) => `<button class="chip ${Store.deskFilter.cat === id ? "on" : ""}" data-cat="${id}">${label}</button>`)
    .join("");
  $$("#desk-filters [data-cat]").forEach((btn) => {
    btn.onclick = () => {
      Store.deskFilter.cat = btn.dataset.cat;
      Store.deskPage = 1;
      Store.groupShown = {};
      renderDeskFilters();
      renderDeskGrid();
      renderChangeTree();
    };
  });
}

function renderLimitUpPanel() {
  const el = $("#limit-up-panel");
  if (!el) return;
  const sum = Store.summary || {};
  const n = sum.limit_up || 0;
  const byInd = Object.entries(sum.limit_up_by_industry || {});
  const byCon = Object.entries(sum.limit_up_by_concept || {});
  if (!n) {
    el.innerHTML = `<div class="limit-up-head"><strong>今日涨停</strong> <span class="hint">缓存池内 0 只</span></div>`;
    return;
  }
  if (!Store.limitUpInd || !byInd.some(([k]) => k === Store.limitUpInd)) {
    Store.limitUpInd = byInd[0]?.[0] || null;
  }
  if (!Store.limitUpCon || !byCon.some(([k]) => k === Store.limitUpCon)) {
    Store.limitUpCon = byCon[0]?.[0] || null;
  }
  const indRows = Array.isArray(sum.limit_up_by_industry?.[Store.limitUpInd])
    ? sum.limit_up_by_industry[Store.limitUpInd]
    : [];
  const conRows = Array.isArray(sum.limit_up_by_concept?.[Store.limitUpCon])
    ? sum.limit_up_by_concept[Store.limitUpCon]
    : [];

  const stockBtns = (rows) =>
    rows.length
      ? `<div class="limit-rows">${rows
          .map(
            (r) =>
              `<button type="button" class="limit-chip" data-code="${r.symbol}">${r.symbol} ${r.name || ""} <span class="up">${fmtPct(r.pct_chg)}</span></button>`
          )
          .join("")}</div>`
      : `<p class="hint">该分类下暂无涨停股</p>`;

  el.innerHTML = `
    <div class="limit-up-head">
      <strong>今日涨停</strong>
      <span class="limit-count">${n}</span>
      <button type="button" class="chip" id="limit-filter-btn">筛选涨停</button>
      <span class="hint">下拉切换行业/概念，股票显示在同一区域</span>
    </div>
    <div class="limit-cols">
      <div class="limit-group">
        <div class="limit-select-row">
          <label>行业
            <select id="limit-ind-select">
              ${byInd
                .map(([name, rows]) => {
                  const list = Array.isArray(rows) ? rows : [];
                  return `<option value="${name}" ${name === Store.limitUpInd ? "selected" : ""}>${name}（${list.length}）</option>`;
                })
                .join("")}
            </select>
          </label>
        </div>
        <div id="limit-ind-stocks" class="limit-stock-area">${stockBtns(indRows)}</div>
      </div>
      <div class="limit-group">
        <div class="limit-select-row">
          <label>概念
            <select id="limit-con-select">
              ${byCon
                .map(([name, rows]) => {
                  const list = Array.isArray(rows) ? rows : [];
                  return `<option value="${name}" ${name === Store.limitUpCon ? "selected" : ""}>${name}（${list.length}）</option>`;
                })
                .join("")}
            </select>
          </label>
        </div>
        <div id="limit-con-stocks" class="limit-stock-area">${stockBtns(conRows)}</div>
      </div>
    </div>`;

  $("#limit-filter-btn")?.addEventListener("click", () => {
    Store.deskFilter.cat = "limit_up";
    Store.deskPage = 1;
    renderDeskFilters();
    renderDeskGrid();
    renderChangeTree();
  });
  $("#limit-ind-select")?.addEventListener("change", (ev) => {
    Store.limitUpInd = ev.target.value;
    const rows = sum.limit_up_by_industry?.[Store.limitUpInd] || [];
    const box = $("#limit-ind-stocks");
    if (box) {
      box.innerHTML = stockBtns(rows);
      $$("#limit-ind-stocks [data-code]").forEach((btn) => {
        btn.onclick = () => selectSymbol(btn.dataset.code, { drawer: true });
      });
    }
  });
  $("#limit-con-select")?.addEventListener("change", (ev) => {
    Store.limitUpCon = ev.target.value;
    const rows = sum.limit_up_by_concept?.[Store.limitUpCon] || [];
    const box = $("#limit-con-stocks");
    if (box) {
      box.innerHTML = stockBtns(rows);
      $$("#limit-con-stocks [data-code]").forEach((btn) => {
        btn.onclick = () => selectSymbol(btn.dataset.code, { drawer: true });
      });
    }
  });
  $$("#limit-up-panel [data-code]").forEach((btn) => {
    btn.onclick = () => selectSymbol(btn.dataset.code, { drawer: true });
  });
}

async function refreshSectorsStatus() {
  const el = $("#sectors-status");
  try {
    const s = await api("/api/sectors");
    if (!el) return;
    if (s.building) {
      el.textContent = `正在拉取分类… 已映射行业股 ${s.industry_count || 0}`;
    } else if (s.built_at) {
      el.textContent = `本地分类 ${s.built_at} · 行业股 ${s.industry_count} · 概念股 ${s.concept_stock_count} · 来源 ${s.source || ""}`;
    } else {
      el.textContent = "尚未生成行业/概念映射，请点击「刷新行业/概念分类」";
    }
  } catch (e) {
    if (el) el.textContent = e.message;
  }
}

async function runSectorsRefresh() {
  startBusyPulse("正在从申万/巨潮拉取行业与概念并保存到本地…");
  try {
    await api("/api/sectors/refresh", { method: "POST", body: "{}" });
    const t = setInterval(async () => {
      try {
        const s = await api("/api/sectors");
        refreshSectorsStatus();
        const pct = s.industry_count > 100 ? Math.min(95, 20 + s.industry_count / 50) : 15;
        showBusy(true, `分类写入中… 行业股 ${s.industry_count || 0}`, pct);
        if (s.built_at && !s.building && s.industry_count > 100) {
          clearInterval(t);
          Store.builtAt = null;
          await loadDesk(true);
          stopBusyPulse();
          banner(`分类完成：行业 ${s.industry_count} / 概念覆盖 ${s.concept_stock_count}`, false);
        }
      } catch (_) {
        /* keep polling */
      }
    }, 2000);
    setTimeout(() => {
      clearInterval(t);
      stopBusyPulse();
      loadDesk(true).catch(() => {});
      refreshSectorsStatus();
    }, 180000);
  } catch (e) {
    banner(e.message, true);
    stopBusyPulse();
  }
}

function pieLayout() {
  return {
    ...PLOT,
    margin: { t: 32, r: 8, b: 8, l: 8 },
    showlegend: false,
  };
}

function renderDeskCharts() {
  const sum = Store.summary || {};
  const board = sum.industries && Object.keys(sum.industries).length ? sum.industries : sum.boards || {};
  const stance = sum.stances || {};
  const bands = sum.bands || {};
  const pieCfg = {
    type: "pie",
    hole: 0.55,
    textinfo: "label+value",
    textfont: { size: 11, color: "#efe7d6" },
    marker: { colors: ["#e6ff4a", "#7aa2ff", "#e4454a", "#2ea574", "#e0a14a", "#8b8473"] },
  };
  renderPlot(
    "viz-board",
    [{ ...pieCfg, labels: Object.keys(board).slice(0, 10), values: Object.values(board).slice(0, 10), name: "行业" }],
    { ...pieLayout(), title: { text: "行业分布", font: { size: 12, color: "#8b8473" } } },
    false
  );
  renderPlot(
    "viz-stance",
    [{ ...pieCfg, labels: Object.keys(stance), values: Object.values(stance), name: "倾向" }],
    { ...pieLayout(), title: { text: "多空倾向", font: { size: 12, color: "#8b8473" } } },
    false
  );
  renderPlot(
    "viz-band",
    [{ ...pieCfg, labels: Object.keys(bands), values: Object.values(bands), name: "价位" }],
    { ...pieLayout(), title: { text: "价格带", font: { size: 12, color: "#8b8473" } } },
    false
  );
  renderChangeTree();
}

function renderChangeTree() {
  const el = $("#viz-tree");
  if (!el || !window.Plotly) return;
  const rows = filteredStocks()
    .filter((s) => s.close != null)
    .slice()
    .sort((a, b) => Math.abs(b.pct_chg || 0) - Math.abs(a.pct_chg || 0))
    .slice(0, 300);
  if (!rows.length) {
    el.innerHTML = `<p class="alert-empty" style="padding:16px">当前筛选下没有可显示的涨跌分布。</p>`;
    return;
  }
  const groups = [...new Set(rows.map((s) => s.industry || "未分类"))];
  const ids = ["root", ...groups.map((b) => `ind:${b}`), ...rows.map((s) => s.symbol)];
  const labels = [
    "缓存池",
    ...groups,
    ...rows.map((s) => `${s.symbol} ${s.name || ""}`.trim()),
  ];
  const parents = ["", ...groups.map(() => "root"), ...rows.map((s) => `ind:${s.industry || "未分类"}`)];
  const values = [
    0,
    ...groups.map(() => 0),
    ...rows.map((s) => Math.max(0.08, Math.abs(Number(s.pct_chg) || 0) + 0.25)),
  ];
  const colors = [0, ...groups.map(() => 0), ...rows.map((s) => Number(s.pct_chg) || 0)];
  const texts = ["", ...groups.map(() => ""), ...rows.map((s) => fmtPct(s.pct_chg))];
  const custom = [null, ...groups.map(() => null), ...rows.map((s) => s.symbol)];
  Plotly.newPlot(
    el,
    [
      {
        type: "treemap",
        ids,
        labels,
        parents,
        values,
        text: texts,
        customdata: custom,
        branchvalues: "remainder",
        textinfo: "label",
        hovertemplate: "%{label}<br>%{text}<extra></extra>",
        pathbar: { visible: true, side: "top", thickness: 18 },
        tiling: { packing: "squarify", pad: 2 },
        level: "root",
        maxdepth: -1,
        marker: {
          colors,
          colorscale: [
            [0, "#2ea574"],
            [0.5, "#2a3122"],
            [1, "#e4454a"],
          ],
          cmid: 0,
          cmin: -6,
          cmax: 6,
          line: { width: 1, color: "#0e100c" },
          pad: { t: 22, l: 2, r: 2, b: 2 },
        },
      },
    ],
    {
      paper_bgcolor: PLOT.paper_bgcolor,
      plot_bgcolor: PLOT.plot_bgcolor,
      font: PLOT.font,
      margin: { t: 36, r: 8, b: 8, l: 8 },
      title: { text: "涨跌分布（按行业）", font: { size: 12, color: "#8b8473" } },
    },
    PLOT_CFG
  ).then((gd) => {
    gd.on("plotly_treemapclick", (ev) => {
      const pt = ev && ev.points && ev.points[0];
      const code = pt && pt.customdata;
      if (!code) return;
      selectSymbol(code, { drawer: true });
      return false;
    });
  });
}

function renderDeskGrid() {
  const rows = filteredStocks();
  const mode = Store.deskFilter.mode || "industry";
  const groupsEl = $("#desk-groups");
  const gridEl = $("#desk-grid");
  const moreWrap = $(".desk-more");
  $("#desk-meta").textContent = `筛选 ${rows.length} / 缓存 ${Store.stocks.length} 只 · 小卡片点开看 K 线`;

  const useGroups = mode === "industry" || mode === "concept";
  if (!useGroups) {
    groupsEl?.classList.add("hidden");
    if (groupsEl) groupsEl.innerHTML = "";
    gridEl?.classList.remove("hidden");
    moreWrap?.classList.remove("hidden");
    const shown = rows.slice(0, Store.deskPage * Store.pageSize);
    if (gridEl) {
      gridEl.innerHTML = shown.map(stockCard).join("");
      bindCardEvents(gridEl);
    }
    $("#desk-more")?.classList.toggle("hidden", shown.length >= rows.length);
  } else {
    gridEl?.classList.add("hidden");
    moreWrap?.classList.add("hidden");
    groupsEl?.classList.remove("hidden");
    renderDeskGroups(rows, mode);
  }

  const cats = $("#desk-cats");
  const sum = Store.summary || {};
  cats.innerHTML = [
    `涨停 ${sum.limit_up || 0}`,
    `行业 ${Object.keys(sum.industries || {}).length}`,
    `概念 ${Object.keys(sum.concepts || {}).length}`,
    `偏多 ${sum.stances?.["偏多"] || 0}`,
    `上涨 ${sum.up || 0}`,
    `下跌 ${sum.down || 0}`,
  ]
    .map((t) => `<span class="tag">${t}</span>`)
    .join("");
}

function groupKeyForStock(s, mode) {
  if (mode === "concept") {
    const cons = s.concepts || [];
    return cons.length ? cons : ["未标注概念"];
  }
  return [s.industry || "未分类"];
}

function renderDeskGroups(rows, mode) {
  const el = $("#desk-groups");
  if (!el) return;
  const map = new Map();
  rows.forEach((s) => {
    groupKeyForStock(s, mode).forEach((g) => {
      if (!map.has(g)) map.set(g, []);
      map.get(g).push(s);
    });
  });
  const groups = [...map.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], "zh"));
  const pageSize = Store.groupPageSize || 12;
  if (!groups.length) {
    el.innerHTML = `<p class="alert-empty">当前筛选下没有股票。可点「刷新行业/概念分类」生成本地映射。</p>`;
    return;
  }
  const label = mode === "concept" ? "概念" : "行业";
  if (!Store.deskGroupKey || !map.has(Store.deskGroupKey)) {
    Store.deskGroupKey = groups[0][0];
  }
  const list = map.get(Store.deskGroupKey) || [];
  const shownN = Store.groupShown[Store.deskGroupKey] || pageSize;
  const slice = list.slice(0, shownN);
  const left = list.length - slice.length;

  el.innerHTML = `
    <section class="desk-group single">
      <div class="desk-group-head">
        <label class="desk-group-select">${label}
          <select id="desk-group-select">
            ${groups
              .map(
                ([name, items]) =>
                  `<option value="${name}" ${name === Store.deskGroupKey ? "selected" : ""}>${name}（${items.length}）</option>`
              )
              .join("")}
          </select>
        </label>
        <span class="hint">共 ${list.length} 只 · 同一区域切换显示</span>
      </div>
      <div class="stock-grid" id="desk-group-cards">${slice.map(stockCard).join("")}</div>
      ${
        left > 0
          ? `<button type="button" class="btn group-more" id="desk-group-more">加载更多（还剩 ${left}）</button>`
          : ""
      }
    </section>`;

  bindCardEvents(el);
  $("#desk-group-select")?.addEventListener("change", (ev) => {
    Store.deskGroupKey = ev.target.value;
    Store.groupShown[Store.deskGroupKey] = pageSize;
    renderDeskGroups(filteredStocks(), mode);
  });
  $("#desk-group-more")?.addEventListener("click", () => {
    Store.groupShown[Store.deskGroupKey] = (Store.groupShown[Store.deskGroupKey] || pageSize) + pageSize;
    renderDeskGroups(filteredStocks(), mode);
  });
}

function renderWatchView() {
  const rows = Store.stocks.filter((s) => isWatched(s.symbol));
  $("#watch-empty").classList.toggle("hidden", rows.length > 0);
  $("#watch-grid").innerHTML = rows.map(stockCard).join("");
  bindCardEvents($("#watch-grid"));
}

function hideSuggest(box) {
  box.classList.add("hidden");
  box.innerHTML = "";
}

function renderSuggest(box, hits, onPick) {
  if (!hits.length) {
    hideSuggest(box);
    return;
  }
  box.innerHTML = hits
    .map(
      (h) => `<button type="button" data-code="${h.symbol}">
        <span class="code">${h.symbol}</span>
        <span class="name">${h.name || ""}</span>
        <span class="px ${tonePct(h.pct_chg)}">${h.close != null ? fmt(h.close, 3) : ""} ${h.pct_chg != null ? fmtPct(h.pct_chg) : ""}</span>
      </button>`
    )
    .join("");
  box.classList.remove("hidden");
  $$("button", box).forEach((btn) => {
    btn.onclick = () => {
      hideSuggest(box);
      onPick(btn.dataset.code);
    };
  });
}

async function lookupSuggest(q) {
  const query = (q || "").trim();
  if (query.length < 1) return [];
  const low = query.toLowerCase();

  const rankLocal = (s) => {
    const code = String(s.symbol || "");
    const name = String(s.name || "");
    const nameLow = name.toLowerCase();
    if (code === query || code.startsWith(query)) return 0;
    if (name === query || nameLow.startsWith(low)) return 1;
    if (nameLow.includes(low) || code.includes(query)) return 2;
    return -1;
  };

  if (Store.stocks.length) {
    const scored = [];
    for (const s of Store.stocks) {
      const rank = rankLocal(s);
      if (rank < 0) continue;
      scored.push({ rank, s });
    }
    scored.sort((a, b) => a.rank - b.rank || String(a.s.symbol).localeCompare(String(b.s.symbol)));
    if (scored.length) return scored.slice(0, 12).map((x) => x.s);
  }

  try {
    const r = await api(`/api/search?q=${encodeURIComponent(query)}`);
    return r.hits || [];
  } catch (_) {
    return [];
  }
}

async function resolveSymbolInput(raw) {
  const q = String(raw || "").trim();
  if (!q) return "";
  if (/^\d{6}$/.test(q)) return q;
  const hits = await lookupSuggest(q);
  return hits[0]?.symbol || "";
}

function bindSuggest(input, box, onPick) {
  let t = null;
  input.addEventListener("input", () => {
    clearTimeout(t);
    const q = input.value;
    t = setTimeout(async () => {
      const hits = await lookupSuggest(q);
      renderSuggest(box, hits, onPick);
    }, 80);
  });
  input.addEventListener("focus", async () => {
    if (input.value.trim()) {
      const hits = await lookupSuggest(input.value);
      renderSuggest(box, hits, onPick);
    }
  });
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") hideSuggest(box);
    if (ev.key === "Enter") {
      const first = box.querySelector("button");
      if (first && !box.classList.contains("hidden")) {
        ev.preventDefault();
        first.click();
      }
    }
  });
  document.addEventListener("click", (ev) => {
    if (!box.contains(ev.target) && ev.target !== input) hideSuggest(box);
  });
}

function matchHighlightOverlay(start, end, label) {
  if (!start || !end) return {};
  const a = start < end ? start : end;
  const b = start < end ? end : start;
  return {
    shapes: [
      {
        type: "rect",
        xref: "x",
        yref: "paper",
        x0: a,
        x1: b,
        y0: 0,
        y1: 1,
        fillcolor: "rgba(122,162,255,0.16)",
        line: { color: "#7aa2ff", width: 1.5 },
        layer: "above",
      },
    ],
    annotations: [
      {
        x: a,
        xref: "x",
        y: 1,
        yref: "paper",
        text: label || "相似区间",
        showarrow: false,
        xanchor: "left",
        yanchor: "top",
        bgcolor: "rgba(18,20,14,0.88)",
        bordercolor: "#7aa2ff",
        borderwidth: 1,
        font: { color: "#7aa2ff", size: 11 },
      },
    ],
  };
}

async function selectSymbol(code, opts = {}) {
  const next = String(code || "").trim();
  if (!next) return;
  $("#symbol").value = next;
  Store.selected = next;
  Store.drawerMatch = opts.matchStart && opts.matchEnd
    ? { start: opts.matchStart, end: opts.matchEnd, label: opts.matchLabel || "相似区间" }
    : null;
  syncWatchButtons();
  highlightSelected();
  loadQuote().catch(() => {});
  if (opts.drawer !== false) openDrawer(next, { match: Store.drawerMatch });
  else if (isDrawerOpen()) openDrawer(next, { match: Store.drawerMatch });
  if (opts.view) {
    setView(opts.view);
    if (opts.view === "signals") runSignals();
    if (opts.view === "backtest") runBacktest();
    if (opts.view === "predict") runPredict();
  } else if (document.querySelector(".nav-item.active")?.dataset.view === "auction") {
    runAuction();
  }
}

async function toggleWatch(code) {
  const symbolCode = String(code || Store.selected || symbol());
  try {
    if (isWatched(symbolCode)) {
      const r = await api(`/api/watchlist/${symbolCode}`, { method: "DELETE" });
      Store.watch = new Set((r.items || []).map((m) => m.symbol));
    } else {
      const r = await api("/api/watchlist", { method: "POST", body: JSON.stringify({ symbol: symbolCode }) });
      Store.watch = new Set((r.items || []).map((m) => m.symbol));
    }
    Store.stocks.forEach((s) => {
      if (s.symbol === symbolCode) s.watched = isWatched(symbolCode);
    });
    syncWatchButtons();
    renderDeskGrid();
    renderWatchView();
    maybeWatchPopup();
  } catch (e) {
    banner(e.message, true);
  }
}

const DRAWER_MIN = 360;
const DRAWER_DEFAULT = 540;

function railWidth() {
  const rail = document.querySelector(".rail");
  return rail ? rail.getBoundingClientRect().width : 220;
}

function contentWidth() {
  return Math.max(DRAWER_MIN, window.innerWidth - railWidth());
}

function isDrawerOpen() {
  return !$("#drawer").classList.contains("hidden");
}

function resizeDrawerChart() {
  const el = $("#drawer-chart");
  if (el && window.Plotly && el.data) {
    Plotly.Plots.resize(el);
    fitYToVisible(el, true);
  }
}

function applyDrawerSize(opts = {}) {
  const drawer = $("#drawer");
  const fillBtn = $("#drawer-fill");
  const max = contentWidth();
  const saved = Number(localStorage.getItem("xingji.drawer.w")) || DRAWER_DEFAULT;
  const wantFill = opts.fill === true || (opts.fill !== false && opts.width == null && localStorage.getItem("xingji.drawer.fill") === "1");
  let nextWidth = opts.width != null ? opts.width : saved;
  if (opts.fill === false && nextWidth >= max - 12) {
    nextWidth = Math.max(DRAWER_MIN, Math.round(max * 0.55));
  }
  if (wantFill || (opts.fill !== false && nextWidth >= max - 12)) {
    drawer.classList.add("fill");
    drawer.style.width = `${max}px`;
    localStorage.setItem("xingji.drawer.fill", "1");
    if (fillBtn) {
      fillBtn.textContent = "还原";
      fillBtn.classList.add("on");
    }
  } else {
    drawer.classList.remove("fill");
    const w = Math.max(DRAWER_MIN, Math.min(nextWidth, max));
    drawer.style.width = `${w}px`;
    localStorage.setItem("xingji.drawer.w", String(w));
    localStorage.setItem("xingji.drawer.fill", "0");
    if (fillBtn) {
      fillBtn.textContent = "铺满";
      fillBtn.classList.remove("on");
    }
  }
  requestAnimationFrame(resizeDrawerChart);
}

function toggleDrawerFill() {
  applyDrawerSize({ fill: !$("#drawer").classList.contains("fill") });
}

function bindDrawerResize() {
  const handle = $("#drawer-handle");
  if (!handle || handle.__bound) return;
  handle.__bound = true;
  handle.addEventListener("mousedown", (ev) => {
    if (ev.button !== 0) return;
    ev.preventDefault();
    const drawer = $("#drawer");
    drawer.classList.add("resizing");
    document.body.classList.add("drawer-resizing");
    const move = (e) => {
      applyDrawerSize({ fill: false, width: window.innerWidth - e.clientX });
    };
    const up = () => {
      drawer.classList.remove("resizing");
      document.body.classList.remove("drawer-resizing");
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      resizeDrawerChart();
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  });
  handle.addEventListener("dblclick", (ev) => {
    ev.preventDefault();
    toggleDrawerFill();
  });
}

async function openDrawer(code, opts = {}) {
  const drawer = $("#drawer");
  $("#drawer-mask").classList.remove("hidden");
  drawer.classList.remove("hidden");
  applyDrawerSize();
  const row = Store.stocks.find((s) => s.symbol === code);
  const match = opts.match || Store.drawerMatch;
  $("#drawer-title").textContent = `${code}  ${row?.name || ""}`;
  $("#drawer-sub").textContent = [
    row?.board,
    row?.stance,
    row?.regime,
    row?.as_of,
    match ? `相似 ${match.start}→${match.end}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  syncWatchButtons();
  showBusy(true, "载入 K 线与提醒…");
  try {
    let start = $("#start").value || "2022-01-01";
    if (match?.start && match.start < start) start = match.start;
    const end = range().end;
    const r = await api(`/api/analyze/${code}?start=${start}&end=${end}`);
    stats($("#drawer-stats"), [
      { value: r.stance, label: "当前倾向" },
      { value: r.regime, label: "市场状态" },
      { value: fmt(r.snapshot.close, 3), label: "收盘" },
      { value: fmtPct(row?.pct_chg), label: "涨跌幅", tone: tonePct(row?.pct_chg) },
      { value: fmt(r.snapshot.rsi14, 1), label: "RSI(14)" },
      { value: r.snapshot.vol_ratio != null ? fmt(r.snapshot.vol_ratio) : "—", label: "量比" },
      {
        value: (() => {
          const last = (r.bars || [])[(r.bars || []).length - 1];
          return last && last.turnover != null ? `${fmt(last.turnover)}%` : "—";
        })(),
        label: "换手",
      },
      { value: String((r.signals || []).length), label: "区间信号" },
    ]);
    const bars = r.bars || [];
    const buys = (r.signals || []).filter((s) => s.action === "buy");
    const sells = (r.signals || []).filter((s) => s.action === "sell");
    const overlay = match
      ? matchHighlightOverlay(match.start, match.end, match.label || "相似区间")
      : {};
    renderPlot(
      "drawer-chart",
      withCandleFlow(bars, [
        {
          x: buys.map((s) => s.date),
          y: buys.map((s) => s.price),
          mode: "markers",
          name: "买点",
          marker: { color: "#e4454a", size: 9, symbol: "triangle-up" },
        },
        {
          x: sells.map((s) => s.date),
          y: sells.map((s) => s.price),
          mode: "markers",
          name: "卖点",
          marker: { color: "#2ea574", size: 9, symbol: "triangle-down" },
        },
      ]),
      overlay
    ).then(resizeDrawerChart);
    const reasons = (r.latest_reasons || [])
      .map(
        (s) =>
          `<div class="reason ${s.action}">${s.source} · ${s.action === "buy" ? "偏多" : s.action === "sell" ? "偏空" : "观察"} — ${s.reason || ""}</div>`
      )
      .join("");
    const recent = [...(r.signals || [])].reverse().slice(0, 12);
    $("#drawer-alerts").innerHTML =
      `<p class="hint">${r.regime_reason || ""} ${r.disclaimer || ""}</p>` +
      (match ? `<p class="hint">蓝框标注形态匹配区间：${match.start} → ${match.end}</p>` : "") +
      (reasons || `<p class="alert-empty">近期没有触发买卖规则，可结合均线与 RSI 观察。</p>`) +
      (recent.length
        ? `<table><thead><tr><th>日期</th><th>动作</th><th>来源</th><th>说明</th><th class="num">价格</th></tr></thead><tbody>${recent
            .map(
              (s) =>
                `<tr><td>${s.date}</td><td>${s.action === "buy" ? "买入" : "卖出"}</td><td>${s.source}</td><td>${s.reason}</td><td class="num">${fmt(s.price)}</td></tr>`
            )
            .join("")}</tbody></table>`
        : "");
  } catch (e) {
    $("#drawer-alerts").innerHTML = `<p class="alert-empty">${e.message}</p>`;
  } finally {
    showBusy(false);
  }
}

function closeDrawer() {
  $("#drawer").classList.add("hidden");
  $("#drawer-mask").classList.add("hidden");
}

function popupKey(a) {
  return `${a.symbol}|${a.kind || a.stance}|${a.as_of || ""}`;
}

function seenPopupKeys() {
  try {
    return new Set(JSON.parse(localStorage.getItem("xingji.popup.seen") || "[]"));
  } catch (_) {
    return new Set();
  }
}

function saveSeenPopupKeys(keys) {
  localStorage.setItem("xingji.popup.seen", JSON.stringify([...keys].slice(-200)));
}

async function maybeWatchPopup() {
  if (!$("#popup").classList.contains("hidden")) return;
  try {
    const data = await api("/api/alerts/watchlist");
    const items = data.items || [...(data.buys || []), ...(data.sells || [])];
    const seen = seenPopupKeys();
    const fresh = items.filter((a) => !seen.has(popupKey(a)));
    if (!fresh.length) return;
    $("#popup-list").innerHTML = fresh
      .map((a) => {
        const kind = a.kind === "sell" || a.stance === "偏空" ? "sell" : "buy";
        return `<div class="popup-item" data-code="${a.symbol}">
          <div><div class="code">${a.symbol}</div><div class="meta">${a.name || ""}</div></div>
          <div>${a.stance || ""} · ${a.regime || ""}<div class="meta">${(a.reasons || [])
            .slice(0, 2)
            .map((r) => r.reason)
            .join("；")}</div></div>
          <div class="px ${kind}">${fmt(a.close, 3)}</div>
        </div>`;
      })
      .join("");
    $("#popup").classList.remove("hidden");
    $("#popup").dataset.keys = JSON.stringify(fresh.map(popupKey));
    $$("#popup-list .popup-item").forEach((el) => {
      el.onclick = () => {
        ackPopup();
        selectSymbol(el.dataset.code, { drawer: true });
      };
    });
  } catch (_) {
    /* ignore popup errors */
  }
}

function ackPopup() {
  const keys = JSON.parse($("#popup").dataset.keys || "[]");
  const seen = seenPopupKeys();
  keys.forEach((k) => seen.add(k));
  saveSeenPopupKeys(seen);
  $("#popup").classList.add("hidden");
}

function laterPopup() {
  $("#popup").classList.add("hidden");
}

function renderAlerts(el, rows, kind) {
  if (!rows || !rows.length) {
    el.innerHTML = `<p class="alert-empty">暂无${kind === "buy" ? "偏多" : "偏空"}提醒。更新缓存后会自动扫描最近买卖点。</p>`;
    return;
  }
  el.innerHTML = rows
    .map((a) => {
      const reasons = (a.reasons || [])
        .map((r) => `<li>${r.source} · ${r.reason}${r.date ? "（" + r.date + "）" : ""}</li>`)
        .join("");
      const watched = isWatched(a.symbol);
      return `<article class="alert-card ${kind}" data-code="${a.symbol}">
        <div>
          <div class="code">${a.symbol} ${watched ? "★" : ""}</div>
          <div class="meta">${a.name || ""}</div>
        </div>
        <div>
          <div class="px">${fmt(a.close, 3)}</div>
          <div class="meta">RSI ${fmt(a.rsi14, 1)}</div>
        </div>
        <div>
          <div>${a.stance} · ${a.regime || ""} · 评分 ${fmt(a.score, 2)}</div>
          <div class="meta">截至 ${a.as_of || ""}</div>
          <ul>${reasons}</ul>
        </div>
      </article>`;
    })
    .join("");
  $$(".alert-card", el).forEach((card) => {
    card.onclick = () => selectSymbol(card.dataset.code, { drawer: true });
  });
}

async function loadDesk(force) {
  try {
    const dash = await api("/api/dashboard");
    if (!force && dash.built_at && dash.built_at === Store.builtAt) {
      renderDeskGrid();
      return;
    }
    Store.stocks = dash.stocks || [];
    Store.summary = dash.summary || {};
    Store.builtAt = dash.built_at;
    Store.stocks.forEach((s) => {
      if (s.watched) Store.watch.add(s.symbol);
    });
    renderDeskModes();
    renderDeskFilters();
    renderLimitUpPanel();
    renderDeskCharts();
    renderDeskGrid();
    renderWatchView();
    syncWatchButtons();
    refreshSectorsStatus();
  } catch (e) {
    $("#desk-meta").textContent = e.message;
  }
}

async function loadHome() {
  try {
    const [st, al, wl] = await Promise.all([
      api("/api/cache/status"),
      api("/api/alerts"),
      api("/api/watchlist"),
    ]);
    Store.watch = new Set((wl.items || []).map((m) => m.symbol));
    syncWatchButtons();
    stats($("#home-cache"), [
      { value: st.last_success || "尚未完成", label: "上次缓存更新" },
      { value: st.schedule || "交易日 16:30", label: "定时任务" },
      { value: st.next_run || "—", label: "下次计划" },
      { value: String(st.cached || 0), label: "已缓存股票" },
      { value: String((al.buys || []).length), label: "偏多提醒", tone: "up" },
      { value: String((al.sells || []).length), label: "偏空提醒", tone: "down" },
    ]);
    const n = (al.buys || []).length + (al.sells || []).length;
    const badge = $("#alert-badge");
    badge.textContent = n ? String(n) : "";
    badge.classList.toggle("hidden", !n);
    renderAlerts($("#home-buys"), al.buys, "buy");
    renderAlerts($("#home-sells"), al.sells, "sell");
    await loadDesk(st.phase === "dashboard" || !Store.builtAt);
    if (st.status === "running") {
      const info = progressFromStatus(st);
      const phase = phaseLabel(info?.phase || st.phase);
      const done = info?.done ?? 0;
      const total = info?.total ?? 0;
      showBusy(true, `${phase} ${done}/${total || "?"}`, info?.pct ?? null);
    } else {
      showBusy(false);
    }
    maybeWatchPopup();
  } catch (e) {
    banner(e.message, true);
  }
}

async function boot() {
  if (!window.Plotly) {
    banner("图表库未加载。请按 Ctrl+F5 强制刷新；若仍不行，检查 /vendor/plotly.min.js 是否可访问。", true);
  }
  const end = $("#end");
  if (!end.value) end.value = new Date().toISOString().slice(0, 10);
  $$(".nav-item").forEach((btn) => btn.addEventListener("click", () => setView(btn.dataset.view)));
  $("#symbol-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const code = await resolveSymbolInput(symbol());
    if (!code) {
      banner("未找到匹配股票，请输入代码或名称", true);
      return;
    }
    selectSymbol(code, { drawer: false });
  });
  $("#bt-run").onclick = runBacktest;
  $("#bt-source")?.addEventListener("change", syncBacktestSourceUI);
  $("#sig-run").onclick = runSignals;
  $("#pred-run").onclick = runPredict;
  $("#sim-run").onclick = runSimilar;
  $("#sim-box").onclick = () => setSimBoxMode(!Store.simBox);
  $("#sim-save").onclick = saveCurrentPattern;
  $("#sim-start").addEventListener("change", onSimDatesChanged);
  $("#sim-end").addEventListener("change", onSimDatesChanged);
  $("#scr-run").onclick = runScreen;
  $("#auc-run").onclick = runAuction;
  $("#scr-add").onclick = () => addCondition();
  $("#scr-save").onclick = saveCurrentScreen;
  if ($("#scr-add-symbol")) {
    bindSuggest($("#scr-add-symbol"), $("#scr-add-suggest"), (code) => addSymbolToStatic(code));
    $("#scr-add-current").onclick = () => addSymbolToStatic(symbol());
  }
  $("#univ-sync").onclick = () => pollSync($("#sim-univ").value).then(loadHome).catch((e) => banner(e.message, true));
  $("#scr-sync").onclick = () => pollSync($("#scr-univ").value).then(loadHome).catch((e) => banner(e.message, true));
  $("#home-update").onclick = () => pollSync("low20").then(loadHome).catch((e) => banner(e.message, true));
  $("#sectors-refresh")?.addEventListener("click", () => runSectorsRefresh());
  $("#cal-prev")?.addEventListener("click", () => calShift(-1));
  $("#cal-next")?.addEventListener("click", () => calShift(1));
  $("#cal-today")?.addEventListener("click", () => {
    const n = new Date();
    Store.calYear = n.getFullYear();
    Store.calMonth = n.getMonth() + 1;
    Store.calSelected = n.toISOString().slice(0, 10);
    loadCalendar();
  });
  $("#home-alerts").onclick = async () => {
    startBusyPulse("正在根据缓存扫描买卖点…");
    try {
      await api("/api/alerts/refresh", { method: "POST", body: "{}" });
      Store.builtAt = null;
      await loadHome();
    } catch (e) {
      banner(e.message, true);
    } finally {
      stopBusyPulse();
    }
  };
  $("#desk-more").onclick = () => {
    Store.deskPage += 1;
    renderDeskGrid();
  };
  $("#desk-search").addEventListener("input", () => {
    Store.deskFilter.q = $("#desk-search").value;
    Store.deskPage = 1;
    renderDeskGrid();
    renderChangeTree();
  });
  bindSuggest($("#symbol"), $("#symbol-suggest"), (code) => selectSymbol(code, { drawer: false }));
  bindSuggest($("#desk-search"), $("#desk-suggest"), (code) => {
    $("#desk-search").value = code;
    Store.deskFilter.q = code;
    Store.deskPage = 1;
    renderDeskGrid();
    selectSymbol(code, { drawer: false });
  });
  $("#hdr-watch").onclick = () => toggleWatch(symbol());
  $("#drawer-watch").onclick = () => toggleWatch(Store.selected || symbol());
  $("#drawer-close").onclick = closeDrawer;
  $("#drawer-mask").onclick = closeDrawer;
  $("#drawer-fill").onclick = toggleDrawerFill;
  bindDrawerResize();
  window.addEventListener("resize", () => {
    if (isDrawerOpen()) applyDrawerSize({ fill: $("#drawer").classList.contains("fill") });
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    const openSuggest = $$(".suggest").find((el) => !el.classList.contains("hidden"));
    if (openSuggest) {
      hideSuggest(openSuggest);
      return;
    }
    if (!$("#popup").classList.contains("hidden")) {
      laterPopup();
      return;
    }
    if (Store.simBox || Store.simHasBox) {
      ev.preventDefault();
      clearSimBox();
      return;
    }
    if (isDrawerOpen()) {
      ev.preventDefault();
      closeDrawer();
    }
  });
  $("#drawer-signals").onclick = () => {
    closeDrawer();
    setView("signals");
    runSignals();
  };
  $("#drawer-backtest").onclick = () => {
    closeDrawer();
    setView("backtest");
    runBacktest();
  };
  $("#popup-ack").onclick = ackPopup;
  $("#popup-later").onclick = laterPopup;
  setInterval(() => {
    const homeOn = $("#view-home").classList.contains("active");
    if (homeOn) loadHome();
    else maybeWatchPopup();
  }, 30000);
  scheduleLivePoll();

  try {
    const s = await api("/api/strategies");
    const box = $("#bt-strategies");
    if (box) {
      box.innerHTML = (s.strategies || [])
        .map(
          (x, i) =>
            `<label class="${i === 0 ? "on" : ""}"><input type="checkbox" value="${x.id}" ${i === 0 ? "checked" : ""} /> ${x.name}</label>`
        )
        .join("");
      $$("#bt-strategies input").forEach((inp) => {
        inp.addEventListener("change", () => {
          inp.closest("label")?.classList.toggle("on", inp.checked);
        });
      });
    }
  } catch (e) {
    banner("后端未启动或策略列表加载失败：" + e.message, true);
  }
  refreshBacktestSelectors();
  syncBacktestSourceUI();
  try {
    const f = await api("/api/screen/fields");
    SCREEN_FIELDS.splice(0, SCREEN_FIELDS.length, ...f.fields);
  } catch (_) {
    /* presets still work */
  }
  PRESETS.forEach((p) => {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = p.name;
    b.onclick = () => {
      $("#scr-conds").innerHTML = "";
      p.conds.forEach(addCondition);
    };
    $("#scr-presets").appendChild(b);
  });
  addCondition({ field: "rsi14", op: "<", value: 40 });
  loadQuote().catch(() => {});
  loadHome();
}

boot();
