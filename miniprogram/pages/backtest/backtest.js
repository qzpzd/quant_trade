const api = require("../../utils/api");
const chart = require("../../utils/chart");
const { rangeFromApp, num, money, fmtEquity, toastErr } = require("../../utils/format");
const { createBusy, busyData } = require("../../utils/busy");

const SOURCES = [
  { key: "symbol", label: "当前股票" },
  { key: "pattern", label: "已保存形态" },
  { key: "screen", label: "已保存条件/名单" },
];

Page({
  data: {
    cash: "100000",
    strategies: [],
    busy: false,
    ...busyData(),
    stats: [],
    hasChart: false,
    winText: "",
    sourceLabels: SOURCES.map((s) => s.label),
    sourceIndex: 0,
    patternLabels: ["（无已存形态）"],
    patternIndex: 0,
    screenLabels: ["（无已存条件）"],
    screenIndex: 0,
    showPattern: false,
    showScreen: false,
  },

  _points: [],
  _winStart: 0,
  _winCount: 80,
  _layout: null,
  _pz: null,
  _busy: null,
  _patterns: [],
  _screens: [],

  onLoad() {
    this._busy = createBusy(this);
  },

  onShow() {
    this.loadStrategies();
    this.loadLibraries();
  },

  noop() {},

  async loadStrategies() {
    try {
      const r = await api.get("/api/strategies");
      const list = (r && r.strategies) || [];
      this.setData({
        strategies: list.map((s, i) => ({ id: s.id, name: s.name, on: i === 0 })),
      });
    } catch (e) {
      toastErr(e);
    }
  },

  async loadLibraries() {
    try {
      const [pats, scrs] = await Promise.all([
        api.get("/api/patterns").catch(() => ({ items: [] })),
        api.get("/api/screens").catch(() => ({ items: [] })),
      ]);
      this._patterns = pats.items || [];
      this._screens = scrs.items || [];
      this.setData({
        patternLabels: this._patterns.length
          ? this._patterns.map((p) => `${p.name} · ${p.symbol}`)
          : ["（无已存形态）"],
        screenLabels: this._screens.length
          ? this._screens.map((s) => `${s.name}（${s.mode === "static" ? "静态" : "动态"}）`)
          : ["（无已存条件）"],
      });
    } catch (e) {
      /* ignore */
    }
  },

  onCash(e) {
    this.setData({ cash: e.detail.value });
  },

  onSource(e) {
    const sourceIndex = Number(e.detail.value);
    const key = SOURCES[sourceIndex].key;
    this.setData({
      sourceIndex,
      showPattern: key === "pattern",
      showScreen: key === "screen",
    });
  },
  onPattern(e) {
    this.setData({ patternIndex: Number(e.detail.value) });
  },
  onScreen(e) {
    this.setData({ screenIndex: Number(e.detail.value) });
  },

  toggleStrategy(e) {
    const id = e.currentTarget.dataset.id;
    this.setData({
      strategies: this.data.strategies.map((s) => (s.id === id ? { ...s, on: !s.on } : s)),
    });
  },

  ensurePz() {
    if (this._pz) return this._pz;
    this._pz = chart.makePanZoom(
      () => ({
        winStart: this._winStart,
        winCount: this._winCount,
        total: this._points.length,
        slot: (this._layout && this._layout.slot) || 6,
      }),
      (partial) => {
        if (partial.winStart != null) this._winStart = partial.winStart;
        if (partial.winCount != null) this._winCount = partial.winCount;
        const w = chart.clampWindow(this._winStart, this._winCount, this._points.length);
        this._winStart = w.start;
        this._winCount = w.count;
      },
      () => this.paint()
    );
    return this._pz;
  },

  async onRun() {
    const picked = this.data.strategies.filter((s) => s.on).map((s) => s.id);
    if (!picked.length) {
      wx.showToast({ title: "请选择策略", icon: "none" });
      return;
    }
    const { symbol, start, end } = rangeFromApp();
    const key = SOURCES[this.data.sourceIndex].key;
    const body = {
      strategies: picked,
      start,
      end,
      cash: Number(this.data.cash) || 100000,
    };
    if (key === "pattern") {
      const p = this._patterns[this.data.patternIndex];
      if (!p) {
        wx.showToast({ title: "请选择已保存形态", icon: "none" });
        return;
      }
      body.pattern_ids = [p.id];
    } else if (key === "screen") {
      const s = this._screens[this.data.screenIndex];
      if (!s) {
        wx.showToast({ title: "请选择已保存条件", icon: "none" });
        return;
      }
      body.screen_id = s.id;
      body.max_symbols = 8;
    } else {
      body.symbol = symbol;
    }

    const msg =
      picked.length === 1
        ? `回测运行中（${picked[0]}）…`
        : `回测 ${picked.length} 个策略…`;
    this.setData({ busy: true });
    this._busy.start(msg);
    try {
      const pack = await api.post("/api/backtest", body);
      const results = (pack && pack.results) || [];
      const stats = results.map((r) => ({
        label: `${r.job_label || r.symbol || ""} · ${r.strategy_name || r.strategy || ""}`,
        ret: r.error ? r.error : `${num(r.return_pct)}%`,
        dd: r.error ? "—" : `${num(r.max_drawdown_pct)}%`,
        sharpe: r.error ? "—" : num(r.sharpe, 2),
        win: r.error ? "—" : `${num(r.win_rate_pct, 1)}%`,
        final: r.error ? "—" : money(r.final_value),
      }));
      this.setData({ stats, hasChart: false });
      const first = results.find((r) => !r.error && r.equity && r.equity.length);
      if (first) {
        this._points = first.equity.map((p) => ({
          y: typeof p === "number" ? p : Number(p.value),
          date: p.date || "",
        }));
        this._winCount = Math.min(120, this._points.length);
        this._winStart = Math.max(0, this._points.length - this._winCount);
        this.setData({ hasChart: true });
        await this.paint();
      }
      this._busy.stop("回测完成");
    } catch (e) {
      toastErr(e);
      this._busy.stop();
    } finally {
      this.setData({ busy: false });
    }
  },

  async paint() {
    if (!this._points.length) return;
    const w = chart.clampWindow(this._winStart, this._winCount, this._points.length);
    this._winStart = w.start;
    this._winCount = w.count;
    const slice = this._points.slice(w.start, w.start + w.count);
    const a = slice[0];
    const b = slice[slice.length - 1];
    this.setData({
      winText: a && b ? `${a.date || ""} ~ ${b.date || ""}（${slice.length}/${this._points.length}）` : "",
    });
    const pack = await chart.bindCanvas(this, "equity", (canvas, dpr) => {
      return chart.drawLineSeries(canvas, slice, {
        dpr,
        color: "#e6ff4a",
        padR: 72,
        axisFmt: fmtEquity,
        label: b ? `账户净值 ${fmtEquity(b.y)}` : "",
      });
    });
    this._layout = pack && pack.layout;
  },

  onTouchStart(e) {
    this.ensurePz().onStart(e);
  },
  onTouchMove(e) {
    this.ensurePz().onMove(e);
  },
  onTouchEnd() {
    this.ensurePz().onEnd();
  },
  zoomIn() {
    this.ensurePz().zoomIn();
  },
  zoomOut() {
    this.ensurePz().zoomOut();
  },
});
