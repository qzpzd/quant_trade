/** Canvas 图表：K线 / 预测多线 / 权益曲线 · 平移缩放 */

function pickBars(bars, maxN = 80) {
  if (!Array.isArray(bars) || !bars.length) return [];
  if (bars.length <= maxN) return bars;
  return bars.slice(bars.length - maxN);
}

function yScale(values, top, bottom) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (v == null || !isFinite(v)) continue;
    lo = Math.min(lo, v);
    hi = Math.max(hi, v);
  }
  if (!isFinite(lo) || !isFinite(hi)) {
    lo = 0;
    hi = 1;
  }
  if (lo === hi) {
    const pad = Math.abs(lo) * 0.02 || 0.05;
    lo -= pad;
    hi += pad;
  }
  const span = hi - lo || 1;
  return {
    lo,
    hi,
    map(v) {
      return bottom - ((v - lo) / span) * (bottom - top);
    },
  };
}

function clampWindow(start, count, total) {
  const c = Math.max(8, Math.min(count, total || 0));
  let s = Math.max(0, Math.min(start, Math.max(0, (total || 0) - c)));
  return { start: s, count: c };
}

function fmtPrice(v) {
  const n = Number(v);
  if (!isFinite(n)) return "";
  if (Math.abs(n) >= 100) return n.toFixed(2);
  if (Math.abs(n) >= 10) return n.toFixed(2);
  return n.toFixed(3);
}

function fmtVol(v) {
  if (v == null || !isFinite(Number(v))) return "—";
  const n = Number(v);
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(abs >= 1e6 ? 1 : 2)}万`;
  return `${Math.round(n)}`;
}

function fmtAmount(v) {
  if (v == null || !isFinite(Number(v))) return "—";
  const n = Number(v);
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(2)}万`;
  return n.toFixed(2);
}

function strokeDash(ctx, style) {
  if (style === "dot") ctx.setLineDash([2, 4]);
  else if (style === "dash") ctx.setLineDash([6, 4]);
  else if (style === "dashdot") ctx.setLineDash([6, 3, 2, 3]);
  else ctx.setLineDash([]);
}

function drawCandles(canvas, bars, opts = {}) {
  if (!canvas || !bars || !bars.length) return null;
  const ctx = canvas.getContext("2d");
  const dpr = opts.dpr || 1;
  const W = canvas.width / dpr;
  const H = canvas.height / dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const showVol =
    opts.showVolume !== false && bars.some((b) => b.volume != null && isFinite(Number(b.volume)));
  const padL = 6;
  const padR = 52;
  const padT = 10;
  const padB = 28;
  const gap = 6;
  const volH = showVol ? Math.floor((H - padT - padB - gap) * 0.22) : 0;
  const priceBottom = H - padB - (showVol ? volH + gap : 0);
  const priceTop = padT;
  const volTop = priceBottom + gap;
  const volBottom = H - padB;

  const n = bars.length;
  const slot = (W - padL - padR) / n;
  const bodyW = Math.max(1, slot * 0.62);

  const highs = bars.map((b) => Number(b.high));
  const lows = bars.map((b) => Number(b.low));
  const ys = yScale(highs.concat(lows), priceTop, priceBottom);

  ctx.fillStyle = "#10130e";
  ctx.fillRect(0, 0, W, H);

  const rows = 4;
  ctx.font = "10px sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  for (let i = 0; i <= rows; i++) {
    const y = priceTop + ((priceBottom - priceTop) * i) / rows;
    const price = ys.hi - ((ys.hi - ys.lo) * i) / rows;
    ctx.strokeStyle = "#2c3224";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(W - padR, y);
    ctx.stroke();
    ctx.fillStyle = "#8b8473";
    ctx.fillText(fmtPrice(price), W - padR + 4, y);
  }

  const sel = opts.selection;
  if (sel && sel.i0 != null && sel.i1 != null) {
    const a = Math.min(sel.i0, sel.i1);
    const b = Math.max(sel.i0, sel.i1);
    const x0 = padL + slot * a;
    const x1 = padL + slot * (b + 1);
    ctx.fillStyle = "rgba(230,255,74,0.16)";
    ctx.fillRect(x0, priceTop, Math.max(2, x1 - x0), priceBottom - priceTop);
    ctx.strokeStyle = "rgba(230,255,74,0.85)";
    ctx.strokeRect(x0, priceTop, Math.max(2, x1 - x0), priceBottom - priceTop);
  }

  for (let i = 0; i < n; i++) {
    const b = bars[i];
    const o = Number(b.open);
    const c = Number(b.close);
    const h = Number(b.high);
    const l = Number(b.low);
    const x = padL + slot * i + slot / 2;
    const up = c >= o;
    const color = up ? "#e4454a" : "#2ea574";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x, ys.map(h));
    ctx.lineTo(x, ys.map(l));
    ctx.stroke();
    const y1 = ys.map(o);
    const y2 = ys.map(c);
    const top = Math.min(y1, y2);
    const bh = Math.max(1, Math.abs(y2 - y1));
    ctx.fillRect(x - bodyW / 2, top, bodyW, bh);
  }

  const crossIdx = opts.crossIndex;

  if (showVol) {
    const vols = bars.map((b) => Number(b.volume) || 0);
    const vmax = Math.max(...vols, 1);
    for (let i = 0; i < n; i++) {
      const b = bars[i];
      const v = Number(b.volume) || 0;
      const up = Number(b.close) >= Number(b.open);
      const vh = (v / vmax) * (volBottom - volTop);
      const x = padL + slot * i + slot / 2;
      ctx.fillStyle = up ? "rgba(228,69,74,0.55)" : "rgba(46,165,116,0.55)";
      ctx.fillRect(x - bodyW / 2, volBottom - vh, bodyW, Math.max(1, vh));
    }
    ctx.fillStyle = "#8b8473";
    ctx.font = "9px sans-serif";
    ctx.textAlign = "left";
    // 右侧为窗口最大量（刻度参考），当日量在底部指标行
    ctx.fillText(`量 ${fmtVol(vmax)}`, W - padR + 2, volTop + 8);
  }

  // 十字竖线：相对窗口固定位置，滑动 K 线时竖线钉在触点，下方指标随当日变化
  if (crossIdx != null && crossIdx >= 0 && crossIdx < n) {
    const cx = padL + slot * crossIdx + slot / 2;
    ctx.strokeStyle = "rgba(230,255,74,0.85)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(cx, priceTop);
    ctx.lineTo(cx, showVol ? volBottom : priceBottom);
    ctx.stroke();
    ctx.setLineDash([]);
    const close = Number(bars[crossIdx].close);
    if (isFinite(close)) {
      const cy = ys.map(close);
      ctx.beginPath();
      ctx.moveTo(padL, cy);
      ctx.lineTo(W - padR, cy);
      ctx.stroke();
      ctx.fillStyle = "#e6ff4a";
      ctx.font = "10px sans-serif";
      ctx.fillText(fmtPrice(close), W - padR + 4, cy);
    }
  }

  const first = bars[0];
  const last = bars[n - 1];
  const tipBar =
    crossIdx != null && crossIdx >= 0 && crossIdx < n ? bars[crossIdx] : last;
  ctx.fillStyle = "#efe7d6";
  ctx.font = "9px sans-serif";
  ctx.textAlign = "left";
  if (tipBar) {
    let foot =
      crossIdx != null
        ? candleFootText(tipBar)
        : first && last
          ? `${first.date || ""} → ${last.date || ""}  量${fmtVol(last.volume)}  额${fmtAmount(last.amount)}`
          : candleFootText(tipBar);
    // 过长则截断，避免画出画布
    const maxW = W - padL - 4;
    while (foot.length > 8 && ctx.measureText(foot).width > maxW) {
      foot = foot.slice(0, -2);
    }
    ctx.fillText(foot, padL, H - 8);
  }

  return {
    padL,
    padR,
    padT,
    padB,
    slot,
    W,
    H,
    n,
    priceTop,
    priceBottom,
    showVol,
    kind: "candle",
  };
}

/**
 * 预测图（对齐 Web）：
 * 收盘实线、类比区间带、形态类比点线、趋势外推虚线、合成实线 + 成交量
 * series 为全长数组，winStart/winCount 控制可见窗口（历史+预测拼接后）
 */
function drawPredict(canvas, pack, opts = {}) {
  if (!canvas || !pack) return null;
  const ctx = canvas.getContext("2d");
  const dpr = opts.dpr || 1;
  const W = canvas.width / dpr;
  const H = canvas.height / dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#10130e";
  ctx.fillRect(0, 0, W, H);

  const hist = pack.history || [];
  const dates = pack.dates || [];
  const histN = hist.length;
  const fwdN = dates.length;
  const total = histN + fwdN;
  if (!total) return null;

  const win = clampWindow(opts.winStart || 0, opts.winCount || total, total);
  const i0 = win.start;
  const i1 = win.start + win.count;

  const closes = [];
  const vols = [];
  const xs = [];
  for (let i = i0; i < i1; i++) {
    if (i < histN) {
      closes.push(Number(hist[i].close));
      vols.push(hist[i].volume);
      xs.push(hist[i].date);
    } else {
      const fi = i - histN;
      closes.push(null);
      vols.push(null);
      xs.push(dates[fi]);
    }
  }

  const pathSlice = (arr) => {
    if (!arr || !arr.length) return [];
    const out = [];
    for (let i = i0; i < i1; i++) {
      if (i < histN) out.push(null);
      else out.push(Number(arr[i - histN]));
    }
    return out;
  };

  const blend = pathSlice(pack.path_blend);
  const analog = pathSlice(pack.path_analog);
  const trend = pathSlice(pack.path_trend);
  const high = pathSlice(pack.path_high);
  const low = pathSlice(pack.path_low);

  const priceVals = []
    .concat(closes.filter((v) => v != null))
    .concat(blend.filter((v) => v != null && isFinite(v)))
    .concat(analog.filter((v) => v != null && isFinite(v)))
    .concat(trend.filter((v) => v != null && isFinite(v)))
    .concat(high.filter((v) => v != null && isFinite(v)))
    .concat(low.filter((v) => v != null && isFinite(v)));

  const showVol = vols.some((v) => v != null && isFinite(Number(v)));
  const padL = 6;
  const padR = 52;
  const padT = 28; // legend
  const padB = 28;
  const gap = 6;
  const volH = showVol ? Math.floor((H - padT - padB - gap) * 0.18) : 0;
  const priceBottom = H - padB - (showVol ? volH + gap : 0);
  const priceTop = padT;
  const volTop = priceBottom + gap;
  const volBottom = H - padB;
  const n = xs.length;
  const slot = (W - padL - padR) / Math.max(1, n - 1);
  const ys = yScale(priceVals, priceTop, priceBottom);

  // grid
  ctx.font = "10px sans-serif";
  for (let i = 0; i <= 4; i++) {
    const y = priceTop + ((priceBottom - priceTop) * i) / 4;
    const price = ys.hi - ((ys.hi - ys.lo) * i) / 4;
    ctx.strokeStyle = "#2c3224";
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(W - padR, y);
    ctx.stroke();
    ctx.fillStyle = "#8b8473";
    ctx.textAlign = "left";
    ctx.fillText(fmtPrice(price), W - padR + 4, y);
  }

  const xAt = (i) => padL + slot * i;

  // band fill P25-P75
  const hasBand = high.some((v) => v != null) && low.some((v) => v != null);
  if (hasBand) {
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < n; i++) {
      if (high[i] == null || !isFinite(high[i])) continue;
      const x = xAt(i);
      const y = ys.map(high[i]);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else ctx.lineTo(x, y);
    }
    for (let i = n - 1; i >= 0; i--) {
      if (low[i] == null || !isFinite(low[i])) continue;
      ctx.lineTo(xAt(i), ys.map(low[i]));
    }
    ctx.closePath();
    ctx.fillStyle = "rgba(122,162,255,0.18)";
    ctx.fill();
  }

  function drawSeg(arr, color, width, dash) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    strokeDash(ctx, dash);
    ctx.beginPath();
    let pen = false;
    for (let i = 0; i < n; i++) {
      const v = arr[i];
      if (v == null || !isFinite(v)) {
        pen = false;
        continue;
      }
      const x = xAt(i);
      const y = ys.map(v);
      if (!pen) {
        ctx.moveTo(x, y);
        pen = true;
      } else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // 历史收盘
  drawSeg(closes, "#efe7d6", 1.4, "solid");
  // 形态类比(中位) · 点线
  drawSeg(analog, "#7aa2ff", 2, "dot");
  // 趋势外推 · 虚线
  drawSeg(trend, "#8b8473", 1.2, "dash");
  // 合成路径 · 实线黄
  drawSeg(blend, "#e6ff4a", 2.2, "solid");

  // volume
  if (showVol) {
    const vmax = Math.max(...vols.map((v) => Number(v) || 0), 1);
    const bodyW = Math.max(1, slot * 0.5);
    for (let i = 0; i < n; i++) {
      const v = Number(vols[i]);
      if (!isFinite(v)) continue;
      const vh = (v / vmax) * (volBottom - volTop);
      ctx.fillStyle = "rgba(230,255,74,0.35)";
      ctx.fillRect(xAt(i) - bodyW / 2, volBottom - vh, bodyW, Math.max(1, vh));
    }
    ctx.fillStyle = "#8b8473";
    ctx.font = "9px sans-serif";
    const crossIdxEarly = opts.crossIndex;
    const vShow =
      crossIdxEarly != null && vols[crossIdxEarly] != null
        ? vols[crossIdxEarly]
        : vmax;
    ctx.fillText(`量 ${fmtVol(vShow)}`, W - padR + 2, volTop + 8);
  }

  // legend
  const legend = [
    { c: "#efe7d6", t: "收盘", d: "solid" },
    { c: "#7aa2ff", t: "类比中位", d: "dot" },
    { c: "#8b8473", t: "趋势外推", d: "dash" },
    { c: "#e6ff4a", t: "合成", d: "solid" },
    { c: "rgba(122,162,255,0.5)", t: "类比区间", d: "solid" },
  ];
  let lx = padL;
  ctx.font = "10px sans-serif";
  legend.forEach((L) => {
    ctx.strokeStyle = L.c;
    ctx.fillStyle = L.c;
    ctx.lineWidth = 2;
    strokeDash(ctx, L.d);
    ctx.beginPath();
    ctx.moveTo(lx, 12);
    ctx.lineTo(lx + 14, 12);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#8b8473";
    ctx.fillText(L.t, lx + 18, 15);
    lx += 18 + ctx.measureText(L.t).width + 12;
  });

  // 十字竖线
  let crossIdx = opts.crossIndex;
  if (crossIdx != null && crossIdx >= 0 && crossIdx < n) {
    const cx = xAt(crossIdx);
    ctx.strokeStyle = "rgba(230,255,74,0.85)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(cx, priceTop);
    ctx.lineTo(cx, showVol ? volBottom : priceBottom);
    ctx.stroke();
    ctx.setLineDash([]);
    const yv =
      closes[crossIdx] != null
        ? closes[crossIdx]
        : blend[crossIdx] != null
          ? blend[crossIdx]
          : analog[crossIdx];
    if (yv != null && isFinite(yv)) {
      const cy = ys.map(yv);
      ctx.beginPath();
      ctx.moveTo(padL, cy);
      ctx.lineTo(W - padR, cy);
      ctx.stroke();
      ctx.fillStyle = "#e6ff4a";
      ctx.fillText(fmtPrice(yv), W - padR + 4, cy);
    }
  }

  // 底部指标行
  ctx.fillStyle = "#efe7d6";
  ctx.font = "9px sans-serif";
  ctx.textAlign = "left";
  let foot =
    crossIdx != null
      ? predictFootText(
          { xs, closes, blend, analog, trend, vols },
          crossIdx
        )
      : xs.length
        ? `${xs[0] || ""} → ${xs[xs.length - 1] || ""}`
        : "";
  if (foot) {
    const maxW = W - padL - 4;
    while (foot.length > 8 && ctx.measureText(foot).width > maxW) {
      foot = foot.slice(0, -2);
    }
    ctx.fillText(foot, padL, H - 6);
  }

  return {
    padL,
    padR,
    padT,
    padB,
    slot,
    W,
    H,
    n,
    total,
    win,
    closes,
    blend,
    analog,
    trend,
    high,
    low,
    vols,
    xs,
    kind: "line",
  };
}

function drawLineSeries(canvas, points, opts = {}) {
  if (!canvas || !points || points.length < 2) return null;
  const ctx = canvas.getContext("2d");
  const dpr = opts.dpr || 1;
  const W = canvas.width / dpr;
  const H = canvas.height / dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#10130e";
  ctx.fillRect(0, 0, W, H);

  const padL = 8;
  const padR = opts.padR != null ? opts.padR : 64;
  const padT = 12;
  const padB = 24;
  const vals = points.map((p) => Number(p.y));
  const ys = yScale(vals, padT, H - padB);
  const n = points.length;
  const slot = (W - padL - padR) / Math.max(1, n - 1);
  const axisFmt =
    typeof opts.axisFmt === "function"
      ? opts.axisFmt
      : (v) => fmtPrice(v);

  ctx.font = "10px sans-serif";
  for (let i = 0; i <= 4; i++) {
    const y = padT + ((H - padB - padT) * i) / 4;
    const price = ys.hi - ((ys.hi - ys.lo) * i) / 4;
    ctx.strokeStyle = "#2c3224";
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(W - padR, y);
    ctx.stroke();
    ctx.fillStyle = "#8b8473";
    ctx.fillText(axisFmt(price), W - padR + 4, y);
  }

  ctx.strokeStyle = opts.color || "#e6ff4a";
  ctx.lineWidth = opts.width || 1.6;
  strokeDash(ctx, opts.dash || "solid");
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = padL + slot * i;
    const y = ys.map(Number(p.y));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.setLineDash([]);

  if (opts.label) {
    ctx.fillStyle = "#8b8473";
    ctx.fillText(opts.label, padL, H - 6);
  }

  return { padL, padR, padT, padB, slot, W, H, n };
}

// backward compat
function drawLine(canvas, points, opts = {}) {
  return drawLineSeries(canvas, points, opts);
}

function bindCanvas(component, canvasId, drawer) {
  return new Promise((resolve) => {
    const q = wx.createSelectorQuery().in(component);
    q.select(`#${canvasId}`)
      .fields({ node: true, size: true })
      .exec((res) => {
        const item = res && res[0];
        if (!item || !item.node) {
          resolve(null);
          return;
        }
        const canvas = item.node;
        const dpr = wx.getSystemInfoSync().pixelRatio || 1;
        canvas.width = item.width * dpr;
        canvas.height = item.height * dpr;
        let layout = null;
        if (typeof drawer === "function") layout = drawer(canvas, dpr) || null;
        resolve({ canvas, dpr, width: item.width, height: item.height, layout });
      });
  });
}

function xToIndex(x, layout) {
  if (!layout || !layout.n) return 0;
  const slot = Math.max(1, layout.slot);
  const raw = (x - layout.padL) / slot;
  // K 线按柱宽取整；折线按点间距四舍五入
  const idx = layout.kind === "candle" ? Math.floor(raw) : Math.round(raw);
  return Math.max(0, Math.min(layout.n - 1, idx));
}

/** 图底单行指标：日期 开高低收 涨跌 量 额 … */
function candleFootText(bar) {
  if (!bar) return "";
  const parts = [bar.date || ""];
  if (bar.open != null && isFinite(Number(bar.open))) parts.push(`开${fmtPrice(bar.open)}`);
  if (bar.high != null && isFinite(Number(bar.high))) parts.push(`高${fmtPrice(bar.high)}`);
  if (bar.low != null && isFinite(Number(bar.low))) parts.push(`低${fmtPrice(bar.low)}`);
  if (bar.close != null && isFinite(Number(bar.close))) parts.push(`收${fmtPrice(bar.close)}`);
  if (bar.pct_chg != null && isFinite(Number(bar.pct_chg))) {
    const p = Number(bar.pct_chg);
    parts.push(`${p > 0 ? "+" : ""}${p.toFixed(2)}%`);
  }
  if (bar.volume != null) parts.push(`量${fmtVol(bar.volume)}`);
  if (bar.amount != null) parts.push(`额${fmtAmount(bar.amount)}`);
  if (bar.turnover != null && isFinite(Number(bar.turnover))) {
    parts.push(`换${Number(bar.turnover).toFixed(2)}%`);
  }
  if (bar.vol_ratio != null && isFinite(Number(bar.vol_ratio))) {
    parts.push(`量比${Number(bar.vol_ratio).toFixed(2)}`);
  }
  if (bar.rsi14 != null && isFinite(Number(bar.rsi14))) {
    parts.push(`RSI${Number(bar.rsi14).toFixed(1)}`);
  }
  return parts.filter(Boolean).join(" ");
}

function predictFootText(layout, idx) {
  if (!layout || idx == null) return "";
  const parts = [(layout.xs && layout.xs[idx]) || ""];
  const push = (label, arr) => {
    const v = arr && arr[idx];
    if (v == null || !isFinite(v)) return;
    parts.push(`${label}${fmtPrice(v)}`);
  };
  push("收", layout.closes);
  push("合", layout.blend);
  push("类", layout.analog);
  push("趋", layout.trend);
  if (layout.vols && layout.vols[idx] != null) parts.push(`量${fmtVol(layout.vols[idx])}`);
  return parts.filter(Boolean).join(" ");
}

/** 单根 K 线指标文案（保留兼容） */
function candleTip(bar) {
  if (!bar) return null;
  const up = Number(bar.close) >= Number(bar.open);
  const rows = [
    { k: "日期", v: bar.date || "—" },
    { k: "开", v: fmtPrice(bar.open) },
    { k: "高", v: fmtPrice(bar.high) },
    { k: "低", v: fmtPrice(bar.low) },
    { k: "收", v: fmtPrice(bar.close) },
  ];
  if (bar.pct_chg != null && isFinite(Number(bar.pct_chg))) {
    const p = Number(bar.pct_chg);
    rows.push({ k: "涨跌", v: `${p > 0 ? "+" : ""}${p.toFixed(2)}%`, cls: p > 0 ? "up" : p < 0 ? "down" : "" });
  }
  if (bar.volume != null) rows.push({ k: "成交量", v: fmtVol(bar.volume) });
  if (bar.amount != null) rows.push({ k: "成交额", v: fmtAmount(bar.amount) });
  if (bar.turnover != null) rows.push({ k: "换手", v: `${Number(bar.turnover).toFixed(2)}%` });
  if (bar.vol_ratio != null) rows.push({ k: "量比", v: Number(bar.vol_ratio).toFixed(2) });
  if (bar.rsi14 != null) rows.push({ k: "RSI", v: Number(bar.rsi14).toFixed(1) });
  return { title: bar.date || "", up, rows };
}

function predictTip(layout, idx) {
  if (!layout || idx == null) return null;
  const rows = [{ k: "日期", v: (layout.xs && layout.xs[idx]) || "—" }];
  const push = (k, arr, color) => {
    const v = arr && arr[idx];
    if (v == null || !isFinite(v)) return;
    rows.push({ k, v: fmtPrice(v), color });
  };
  push("收盘", layout.closes, "#efe7d6");
  push("类比中位", layout.analog, "#7aa2ff");
  push("趋势外推", layout.trend, "#8b8473");
  push("合成", layout.blend, "#e6ff4a");
  push("类比上沿", layout.high, "#7aa2ff");
  push("类比下沿", layout.low, "#7aa2ff");
  if (layout.vols && layout.vols[idx] != null) {
    rows.push({ k: "成交量", v: fmtVol(layout.vols[idx]) });
  }
  return { title: (layout.xs && layout.xs[idx]) || "", rows };
}

/** 通用窗口控制器：单指平移+十字线、双指缩放
 * opts.onCross(index, touchX) 在单指移动时回调
 */
function makePanZoom(getState, setState, repaint, opts = {}) {
  let touch = null;
  return {
    onStart(e) {
      const touches = e.touches || [];
      const st = getState();
      if (touches.length >= 2) {
        const dx = touches[0].x - touches[1].x;
        const dy = touches[0].y - touches[1].y;
        touch = {
          mode: "pinch",
          dist: Math.sqrt(dx * dx + dy * dy) || 1,
          count0: st.winCount,
          start0: st.winStart,
        };
        return;
      }
      if (touches.length === 1) {
        const crossRel =
          st.layout != null ? xToIndex(touches[0].x, st.layout) : null;
        touch = {
          mode: "pan",
          x0: touches[0].x,
          start0: st.winStart,
          lastX: touches[0].x,
          crossRel,
        };
        if (typeof opts.onCross === "function" && crossRel != null) {
          opts.onCross(crossRel, touches[0].x);
        }
        repaint();
      }
    },
    onMove(e) {
      if (!touch) return;
      const touches = e.touches || [];
      const st = getState();
      const slot = st.slot || 6;
      if (touch.mode === "pinch" && touches.length >= 2) {
        const dx = touches[0].x - touches[1].x;
        const dy = touches[0].y - touches[1].y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const scale = touch.dist / dist;
        const mid = touch.start0 + touch.count0 / 2;
        let count = Math.round(touch.count0 * scale);
        count = Math.max(12, Math.min(st.total, count));
        setState({
          winCount: count,
          winStart: Math.round(mid - count / 2),
        });
        repaint();
        return;
      }
      if (touch.mode === "pan" && touches.length === 1) {
        const x = touches[0].x;
        const dx = x - touch.x0;
        const shift = Math.round(-dx / Math.max(3, slot));
        setState({ winStart: touch.start0 + shift });
        touch.lastX = x;
        // 竖线钉在按下时的相对位置，滑动 K 线时指标随当日变化
        if (typeof opts.onCross === "function" && touch.crossRel != null) {
          opts.onCross(touch.crossRel, touch.x0);
        }
        repaint();
      }
    },
    onEnd() {
      touch = null;
      if (typeof opts.onCrossEnd === "function") opts.onCrossEnd();
    },
    zoomIn() {
      const st = getState();
      const mid = st.winStart + st.winCount / 2;
      const count = Math.max(12, Math.floor(st.winCount * 0.7));
      setState({ winCount: count, winStart: Math.round(mid - count / 2) });
      repaint();
    },
    zoomOut() {
      const st = getState();
      const mid = st.winStart + st.winCount / 2;
      const count = Math.min(st.total, Math.floor(st.winCount * 1.4));
      setState({ winCount: count, winStart: Math.round(mid - count / 2) });
      repaint();
    },
  };
}

module.exports = {
  pickBars,
  drawCandles,
  drawLine,
  drawLineSeries,
  drawPredict,
  bindCanvas,
  clampWindow,
  xToIndex,
  makePanZoom,
  candleTip,
  candleFootText,
  predictTip,
  predictFootText,
  fmtPrice,
  fmtVol,
  fmtAmount,
};
