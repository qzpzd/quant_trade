const api = require("../../utils/api");
const chart = require("../../utils/chart");
const { rangeFromApp, setSymbol, pct, chgClass, fmtVol, fmtAmount, num, toastErr } = require("../../utils/format");

Page({
  data: {
    busy: false,
    quote: null,
    closeText: "",
    chgText: "",
    chgClass: "",
    volText: "",
    amountText: "—",
    volRatioText: "—",
    turnoverText: "—",
    rsiText: "—",
    stance: "—",
    regime: "—",
    subText: "",
    winText: "",
    analyze: null,
    reasons: [],
    watching: false,
  },

  _allBars: [],
  _winStart: 0,
  _winCount: 60,
  _layout: null,
  _touch: null,
  _crossIndex: null,
  _canvas: null,
  _dpr: 1,
  _paintSeq: 0,

  onShow() {
    this.loadQuote();
  },

  onBarChange() {
    this._canvas = null;
    this.loadQuote();
  },

  go(e) {
    wx.navigateTo({ url: e.currentTarget.dataset.url });
  },

  async refreshWatchFlag(symbol) {
    try {
      const w = await api.get("/api/watchlist");
      const items = (w && w.items) || [];
      this.setData({ watching: items.some((x) => x.symbol === symbol) });
    } catch (e) {
      this.setData({ watching: false });
    }
  },

  async loadQuote() {
    const { symbol, start, end } = rangeFromApp();
    this.setData({ busy: true });
    this._crossIndex = null;
    this._canvas = null;
    try {
      const analyze = await api.get(
        `/api/analyze/${encodeURIComponent(symbol)}?start=${start}&end=${end}`
      );
      setSymbol(analyze.symbol);
      const snap = analyze.snapshot || {};
      const bars = analyze.bars || [];
      const last = bars[bars.length - 1] || {};
      const close = snap.close != null ? snap.close : last.close;
      const pctChg = last.pct_chg != null ? last.pct_chg : snap.pct_chg;
      const volRatio = snap.vol_ratio != null ? snap.vol_ratio : last.vol_ratio;
      const turnover = last.turnover != null ? last.turnover : snap.turnover;
      const volume = last.volume != null ? last.volume : snap.volume;
      const amount = last.amount != null ? last.amount : snap.amount;

      this._allBars = bars;
      this._winCount = Math.min(60, Math.max(20, bars.length));
      this._winStart = Math.max(0, bars.length - this._winCount);

      this.setData({
        quote: {
          symbol: analyze.symbol,
          name: analyze.name,
          date: snap.date || last.date,
          close,
          open: last.open,
          high: last.high,
          low: last.low,
          volume,
          amount,
        },
        closeText: close != null ? Number(close).toFixed(3) : "—",
        chgText: pct(pctChg),
        chgClass: chgClass(pctChg),
        volText: fmtVol(volume),
        amountText: fmtAmount(amount),
        volRatioText: volRatio != null ? num(volRatio, 2) : "—",
        turnoverText: turnover != null ? `${num(turnover, 2)}%` : "—",
        rsiText: snap.rsi14 != null ? num(snap.rsi14, 1) : "—",
        stance: analyze.stance || "—",
        regime: analyze.regime || "—",
        subText: [analyze.stance, analyze.regime, snap.date || last.date].filter(Boolean).join(" · "),
        analyze: null,
        reasons: [],
      });
      await this.refreshWatchFlag(analyze.symbol);
      await this.paintK();
    } catch (e) {
      try {
        const quote = await api.get(
          `/api/quote/${encodeURIComponent(symbol)}?start=${start}&end=${end}`
        );
        setSymbol(quote.symbol);
        this._allBars = quote.bars || [];
        this._winCount = Math.min(60, this._allBars.length);
        this._winStart = Math.max(0, this._allBars.length - this._winCount);
        this.setData({
          quote,
          closeText: Number(quote.close).toFixed(3),
          chgText: pct(quote.pct_chg),
          chgClass: chgClass(quote.pct_chg),
          volText: fmtVol(quote.volume),
          amountText: fmtAmount(quote.amount),
          volRatioText: "—",
          turnoverText: quote.turnover != null ? `${num(quote.turnover, 2)}%` : "—",
          rsiText: "—",
          stance: "—",
          regime: "—",
          subText: `${quote.date} · ${quote.symbol}`,
        });
        await this.paintK();
      } catch (e2) {
        toastErr(e, "加载失败");
      }
    } finally {
      this.setData({ busy: false });
    }
  },

  visibleBars() {
    const all = this._allBars || [];
    const { start, count } = chart.clampWindow(this._winStart, this._winCount, all.length || 0);
    this._winStart = start;
    this._winCount = count;
    return all.slice(start, start + count);
  },

  async paintK() {
    const seq = ++this._paintSeq;
    const bars = this.visibleBars();
    const all = this._allBars || [];
    const a = all[this._winStart];
    const b = all[Math.min(all.length - 1, this._winStart + this._winCount - 1)];
    this.setData({
      winText: a && b ? `${a.date} ~ ${b.date}（${bars.length}/${all.length}）` : "",
    });
    const crossIndex = this._crossIndex;
    const drawer = (canvas, dpr) =>
      chart.drawCandles(canvas, bars, {
        dpr,
        showVolume: true,
        crossIndex,
      });

    if (this._canvas) {
      const layout = drawer(this._canvas, this._dpr);
      if (seq !== this._paintSeq) return;
      this._layout = layout;
      return;
    }

    const pack = await chart.bindCanvas(this, "kline", drawer);
    if (seq !== this._paintSeq) return;
    if (pack) {
      this._canvas = pack.canvas;
      this._dpr = pack.dpr;
      this._layout = pack.layout;
    }
  },

  shiftWin(delta) {
    if (!this._allBars.length) return;
    this._winStart += delta;
    this.paintK();
  },

  panLeft() {
    this.shiftWin(-Math.max(3, Math.floor(this._winCount / 5)));
  },

  panRight() {
    this.shiftWin(Math.max(3, Math.floor(this._winCount / 5)));
  },

  zoomIn() {
    if (!this._allBars.length) return;
    const mid = this._winStart + this._winCount / 2;
    this._winCount = Math.max(15, Math.floor(this._winCount * 0.7));
    this._winStart = Math.round(mid - this._winCount / 2);
    this.paintK();
  },

  zoomOut() {
    if (!this._allBars.length) return;
    const mid = this._winStart + this._winCount / 2;
    this._winCount = Math.min(this._allBars.length, Math.floor(this._winCount * 1.4));
    this._winStart = Math.round(mid - this._winCount / 2);
    this.paintK();
  },

  onTouchStart(e) {
    const touches = e.touches || [];
    if (!touches.length) return;
    if (touches.length >= 2) {
      const dx = touches[0].x - touches[1].x;
      const dy = touches[0].y - touches[1].y;
      this._touch = {
        mode: "pinch",
        dist: Math.sqrt(dx * dx + dy * dy) || 1,
        count0: this._winCount,
        start0: this._winStart,
      };
      return;
    }
    // 单指：平移 K 线；竖线钉在按下位置，底部指标随滑入的当日变化
    const crossRel = this._layout ? chart.xToIndex(touches[0].x, this._layout) : null;
    this._touch = {
      mode: "pan",
      x0: touches[0].x,
      start0: this._winStart,
      crossRel,
    };
    if (crossRel != null) this._crossIndex = crossRel;
    this.paintK();
  },

  onTouchMove(e) {
    if (!this._touch || !this._allBars.length) return;
    const touches = e.touches || [];
    const layout = this._layout;
    const slot = (layout && layout.slot) || 8;

    if (this._touch.mode === "pinch" && touches.length >= 2) {
      const dx = touches[0].x - touches[1].x;
      const dy = touches[0].y - touches[1].y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const scale = this._touch.dist / dist;
      const mid = this._touch.start0 + this._touch.count0 / 2;
      let count = Math.round(this._touch.count0 * scale);
      count = Math.max(15, Math.min(this._allBars.length, count));
      this._winCount = count;
      this._winStart = Math.round(mid - count / 2);
      this.paintK();
      return;
    }

    if (this._touch.mode === "pan" && touches.length === 1) {
      const dx = touches[0].x - this._touch.x0;
      const shift = Math.round(-dx / Math.max(4, slot));
      this._winStart = this._touch.start0 + shift;
      if (this._touch.crossRel != null) this._crossIndex = this._touch.crossRel;
      this.paintK();
    }
  },

  onTouchEnd() {
    this._touch = null;
  },

  async onAnalyze() {
    const { symbol, start, end } = rangeFromApp();
    this.setData({ busy: true });
    try {
      const analyze = await api.get(
        `/api/analyze/${encodeURIComponent(symbol)}?start=${start}&end=${end}`
      );
      this.setData({
        analyze,
        reasons: analyze.latest_reasons || analyze.signals || [],
        stance: analyze.stance || this.data.stance,
        regime: analyze.regime || this.data.regime,
      });
      if (analyze.bars && analyze.bars.length) {
        this._allBars = analyze.bars;
        this._winCount = Math.min(60, analyze.bars.length);
        this._winStart = Math.max(0, analyze.bars.length - this._winCount);
        await this.paintK();
      }
    } catch (e) {
      toastErr(e, "分析失败");
    } finally {
      this.setData({ busy: false });
    }
  },

  async onToggleWatch() {
    const { symbol } = rangeFromApp();
    try {
      if (this.data.watching) {
        await api.del(`/api/watchlist/${symbol}`);
        this.setData({ watching: false });
        wx.showToast({ title: "已取消", icon: "success" });
      } else {
        await api.post("/api/watchlist", { symbol });
        this.setData({ watching: true });
        wx.showToast({ title: "已加入", icon: "success" });
      }
    } catch (e) {
      toastErr(e);
    }
  },
});
