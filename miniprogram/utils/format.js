function num(v, digits = 2) {
  const n = Number(v);
  if (!isFinite(n)) return "—";
  return n.toFixed(digits);
}

function pct(v, digits = 2) {
  const n = Number(v);
  if (!isFinite(n)) return "—";
  const s = n.toFixed(digits);
  return n > 0 ? `+${s}%` : `${s}%`;
}

function chgClass(v) {
  const n = Number(v);
  if (!isFinite(n) || n === 0) return "";
  return n > 0 ? "up" : "down";
}

/** 成交量：股 → 万/亿 */
function fmtVol(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (!isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(abs >= 1e6 ? 1 : 2)}万`;
  return `${Math.round(n)}`;
}

/** 成交额：元 → 万/亿 */
function fmtAmount(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (!isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(2)}万`;
  return n.toFixed(2);
}

/** 通用金额/权益显示 */
function money(v) {
  return fmtAmount(v);
}

/** 权益轴刻度：带「元/万/亿」 */
function fmtEquity(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (!isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(1)}万`;
  return `${Math.round(n)}元`;
}

function todayStr() {
  const d = new Date();
  const m = `${d.getMonth() + 1}`.padStart(2, "0");
  const day = `${d.getDate()}`.padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  const m = `${d.getMonth() + 1}`.padStart(2, "0");
  const day = `${d.getDate()}`.padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function rangeFromApp() {
  const app = getApp();
  const g = app.globalData || {};
  return {
    symbol: g.symbol || "002195",
    start: g.start || "2020-01-01",
    end: g.end || todayStr(),
  };
}

function setSymbol(code) {
  const app = getApp();
  app.globalData.symbol = String(code || "").trim();
}

function setRange(partial) {
  const app = getApp();
  if (partial.symbol != null) app.globalData.symbol = String(partial.symbol).trim();
  if (partial.start != null) app.globalData.start = partial.start;
  if (partial.end != null) app.globalData.end = partial.end;
}

function toastErr(e, fallback) {
  wx.showToast({
    title: (e && e.message) || fallback || "失败",
    icon: "none",
    duration: 3500,
  });
}

module.exports = {
  num,
  pct,
  chgClass,
  money,
  fmtEquity,
  fmtVol,
  fmtAmount,
  todayStr,
  daysAgo,
  rangeFromApp,
  setSymbol,
  setRange,
  toastErr,
};
