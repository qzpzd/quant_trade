const api = require("../../utils/api");
const chart = require("../../utils/chart");
const { rangeFromApp, toastErr } = require("../../utils/format");
const { createBusy, busyData } = require("../../utils/busy");

Page({
  data: {
    busy: false,
    ...busyData(),
    head: null,
    reasons: [],
    signals: [],
  },

  _busy: null,

  onLoad() {
    this._busy = createBusy(this);
  },

  onShow() {
    // 不自动跑，避免每次切页都重算
  },

  async run() {
    const { symbol, start, end } = rangeFromApp();
    this.setData({ busy: true });
    this._busy.start("扫描买卖点…");
    try {
      const r = await api.get(`/api/analyze/${encodeURIComponent(symbol)}?start=${start}&end=${end}`);
      this.setData({
        head: {
          symbol: r.symbol,
          name: r.name,
          stance: r.stance,
          regime: r.regime,
          score: r.score,
          signal_count: r.signal_count,
          regime_reason: r.regime_reason,
        },
        reasons: r.latest_reasons || [],
        signals: (r.signals || []).slice(-40).reverse(),
      });
      await chart.bindCanvas(this, "sigchart", (canvas, dpr) => {
        chart.drawCandles(canvas, chart.pickBars(r.bars || [], 90), { dpr });
      });
      this._busy.stop("分析完成");
    } catch (e) {
      toastErr(e);
      this._busy.stop();
    } finally {
      this.setData({ busy: false });
    }
  },
});
