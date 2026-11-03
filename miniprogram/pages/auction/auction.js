const api = require("../../utils/api");
const { rangeFromApp, num, fmtVol, fmtAmount, toastErr } = require("../../utils/format");
const { createBusy, busyData } = require("../../utils/busy");

const VOL_KEYS = new Set([
  "volume",
  "vol",
  "open_volume",
  "close_volume",
  "auction_volume",
  "量",
]);
const AMT_KEYS = new Set([
  "amount",
  "amt",
  "open_amount",
  "close_amount",
  "auction_amount",
  "额",
]);
const PCT_KEYS = new Set(["pct", "pct_chg", "change_pct", "涨跌%"]);

function formatStatValue(key, v) {
  if (v == null) return "—";
  if (typeof v !== "number") return String(v);
  const k = String(key).toLowerCase();
  if (VOL_KEYS.has(k) || /volume|成交量|_vol$|^vol$/i.test(key)) return fmtVol(v);
  if (AMT_KEYS.has(k) || /amount|成交额|_amt$|^amt$/i.test(key)) return fmtAmount(v);
  if (PCT_KEYS.has(k) || /pct|涨跌|change/i.test(key)) {
    const s = num(v);
    return v > 0 ? `+${s}%` : `${s}%`;
  }
  return num(v);
}

function pickStats(obj, pairs) {
  if (!obj || typeof obj !== "object") return [];
  return pairs
    .map(([k, label]) => {
      const v = obj[k];
      if (v == null || typeof v === "object") return null;
      return { k: label, v: formatStatValue(k, v) };
    })
    .filter(Boolean);
}

function flattenStats(obj) {
  if (!obj || typeof obj !== "object") return [];
  const prefer = [
    ["price", "价格"],
    ["auction_price", "竞价价"],
    ["close", "收盘"],
    ["pct", "涨跌%"],
    ["pct_chg", "涨跌%"],
    ["change_pct", "涨跌%"],
    ["volume", "成交量"],
    ["amount", "成交额"],
    ["open_volume", "开盘量"],
    ["open_amount", "开盘额"],
    ["close_volume", "尾盘量"],
    ["close_amount", "尾盘额"],
    ["bias", "偏向"],
    ["label", "结论"],
    ["signal", "信号"],
    ["score", "分数"],
  ];
  const out = pickStats(obj, prefer);
  if (out.length) return out;
  return Object.keys(obj)
    .filter((k) => typeof obj[k] !== "object")
    .slice(0, 8)
    .map((k) => ({
      k,
      v: formatStatValue(k, obj[k]),
    }));
}

Page({
  data: {
    busy: false,
    ...busyData(),
    open: null,
    close: null,
    openStats: [],
    closeStats: [],
    openNote: "",
    closeNote: "",
    hist: [],
    notes: "",
  },

  _busy: null,

  onLoad() {
    this._busy = createBusy(this);
  },

  async run() {
    const { symbol } = rangeFromApp();
    this.setData({ busy: true });
    this._busy.start("正在分析早盘/尾盘竞价…");
    try {
      const r = await api.get(`/api/auction/${encodeURIComponent(symbol)}`);
      const open = r.opening || r.open || r.open_auction || r.morning || null;
      const close = r.closing || r.close || r.close_auction || r.afternoon || null;
      const histRaw = r.history || r.hist || r.sessions || [];
      const hist = (Array.isArray(histRaw) ? histRaw : []).slice(0, 30).map((h, i) => {
        if (typeof h === "string") return { title: h, sub: "" };
        const vol =
          h.volume != null || h.open_volume != null
            ? `量${fmtVol(h.volume != null ? h.volume : h.open_volume)}`
            : "";
        const amt =
          h.amount != null || h.open_amount != null
            ? `额${fmtAmount(h.amount != null ? h.amount : h.open_amount)}`
            : "";
        return {
          title: h.date || h.day || h.session || `记录 ${i + 1}`,
          sub:
            h.summary ||
            h.note ||
            h.label ||
            [h.bias, h.pct_chg != null ? `${h.pct_chg}%` : "", vol, amt]
              .filter(Boolean)
              .join(" · ") ||
            "",
        };
      });
      const notes = Array.isArray(r.notes)
        ? r.notes.join("；")
        : r.notes || r.disclaimer || r.message || "";
      this.setData({
        open,
        close,
        openStats: flattenStats(open),
        closeStats: flattenStats(close),
        openNote: (open && (open.note || open.summary || open.reason || open.label)) || "",
        closeNote: (close && (close.note || close.summary || close.reason || close.label)) || "",
        hist,
        notes,
      });
      this._busy.stop("竞价分析完成");
    } catch (e) {
      toastErr(e);
      this._busy.stop();
    } finally {
      this.setData({ busy: false });
    }
  },
});
