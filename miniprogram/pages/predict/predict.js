const api = require("../../utils/api");
const chart = require("../../utils/chart");
const { rangeFromApp, setSymbol, pct, chgClass, toastErr } = require("../../utils/format");
const { createBusy, busyData } = require("../../utils/busy");

const SOURCES = [
  { key: "symbol", label: "当前股票" },
  { key: "pattern", label: "已保存形态" },
  { key: "screen", label: "已保存条件/名单" },
];

Page({
  data: {
    lookback: "30",
    horizon: "10",
    busy: false,
    ...busyData(),
    result: null,
    retText: "",
    retClass: "",
    analogRet: "",
    hasChart: false,
    winText: "",
    sourceLabels: SOURCES.map((s) => s.label),
    sourceIndex: 0,
    patternLabels: ["（无已存形态）"],
    patternIndex: 0,
    screenLabels: ["（无已存条件）"],
    screenIndex: 0,
    hitLabels: [],
    hitIndex: 0,
    showPattern: false,
    showScreen: false,
    showHits: false,
  },

  _pack: null,
  _winStart: 0,
  _winCount: 80,
  _total: 0,
  _layout: null,
  _pz: null,
  _crossIndex: null,
  _busy: null,
  _canvas: null,
  _dpr: 1,
  _paintSeq: 0,
  _patterns: [],
  _screens: [],
  _hits: [],

  onLoad() {
    this._busy = createBusy(this);
  },

  onShow() {
    this.loadLibraries();
  },

  noop() {},

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
        patternIndex: 0,
        screenIndex: 0,
      });
    } catch (e) {
      /* ignore */
    }
  },

  onLookback(e) {
    this.setData({ lookback: e.detail.value });
  },
  onHorizon(e) {
    this.setData({ horizon: e.detail.value });
  },
  onSource(e) {
    const sourceIndex = Number(e.detail.value);
    const key = SOURCES[sourceIndex].key;
    this.setData({
      sourceIndex,
      showPattern: key === "pattern",
      showScreen: key === "screen",
      showHits: false,
      hitLabels: [],
      hitIndex: 0,
    });
    if (key === "screen" && this._screens.length) this.loadScreenHits(0);
  },
  onPattern(e) {
    this.setData({ patternIndex: Number(e.detail.value) });
  },
  onScreen(e) {
    const screenIndex = Number(e.detail.value);
    this.setData({ screenIndex });
    this.loadScreenHits(screenIndex);
  },
  onHit(e) {
    this.setData({ hitIndex: Number(e.detail.value) });
  },

  async loadScreenHits(screenIndex) {
    const scr = this._screens[screenIndex];
    if (!scr) {
      this.setData({ showHits: false, hitLabels: [] });
      return;
    }
    try {
      const item = await api.get(`/api/screens/${scr.id}`);
      const hits = item.hits || [];
      this._hits = hits;
      this.setData({
        showHits: hits.length > 0,
        hitLabels: hits.length
          ? hits.map((h) => `${h.name || ""} ${h.symbol}`.trim())
          : ["（名单为空，将用条件结果第一只）"],
        hitIndex: 0,
      });
    } catch (e) {
      this._hits = [];
      this.setData({ showHits: false });
    }
  },

  async resolveSymbol() {
    const key = SOURCES[this.data.sourceIndex].key;
    if (key === "pattern") {
      const p = this._patterns[this.data.patternIndex];
      if (!p) throw new Error("请先在形态页保存形态");
      setSymbol(p.symbol);
      // 用形态窗口长度作为回看参考
      if (p.start && p.end) {
        const a = new Date(p.start).getTime();
        const b = new Date(p.end).getTime();
        if (isFinite(a) && isFinite(b) && b >= a) {
          const days = Math.max(15, Math.min(80, Math.round((b - a) / 86400000) + 1));
          this.setData({ lookback: String(days) });
        }
      }
      return p.symbol;
    }
    if (key === "screen") {
      const scr = this._screens[this.data.screenIndex];
      if (!scr) throw new Error("请先在选股页保存条件");
      if (this._hits.length) {
        const h = this._hits[this.data.hitIndex] || this._hits[0];
        setSymbol(h.symbol);
        return h.symbol;
      }
      // 动态条件当场重跑拿第一只
      const item = await api.get(`/api/screens/${scr.id}`);
      const hits = item.hits || [];
      if (!hits.length) throw new Error("该条件暂无命中股票");
      setSymbol(hits[0].symbol);
      return hits[0].symbol;
    }
    return rangeFromApp().symbol;
  },

  applyCross(idx) {
    this._crossIndex = idx;
  },

  ensurePz() {
    if (this._pz) return this._pz;
    this._pz = chart.makePanZoom(
      () => ({
        winStart: this._winStart,
        winCount: this._winCount,
        total: this._total,
        slot: (this._layout && this._layout.slot) || 6,
        layout: this._layout,
      }),
      (partial) => {
        if (partial.winStart != null) this._winStart = partial.winStart;
        if (partial.winCount != null) this._winCount = partial.winCount;
        const w = chart.clampWindow(this._winStart, this._winCount, this._total);
        this._winStart = w.start;
        this._winCount = w.count;
      },
      () => this.paint(),
      { onCross: (idx) => this.applyCross(idx) }
    );
    return this._pz;
  },

  shiftWin(delta) {
    this._winStart += delta;
    const w = chart.clampWindow(this._winStart, this._winCount, this._total);
    this._winStart = w.start;
    this._winCount = w.count;
    this.paint();
  },
  panLeft() {
    this.shiftWin(-Math.max(3, Math.floor(this._winCount / 5)));
  },
  panRight() {
    this.shiftWin(Math.max(3, Math.floor(this._winCount / 5)));
  },

  async onRun() {
    this.setData({ busy: true });
    this._crossIndex = null;
    this._canvas = null;
    this._busy.start("在缓存股票中匹配价+量+换手相似形态…");
    try {
      const symbol = await this.resolveSymbol();
      const result = await api.post("/api/predict", {
        symbol,
        lookback: Number(this.data.lookback) || 30,
        horizon: Number(this.data.horizon) || 10,
      });
      const hist = result.history || [];
      const fwd = result.dates || [];
      this._pack = result;
      this._total = hist.length + fwd.length;
      this._winCount = Math.min(80, this._total);
      this._winStart = Math.max(0, this._total - this._winCount);
      this.setData({
        result,
        retText: pct(result.blend_return_pct),
        retClass: chgClass(result.blend_return_pct),
        analogRet: pct(result.analog_return_pct),
        hasChart: this._total > 1,
      });
      await this.paint();
      this._busy.stop("预测完成");
    } catch (e) {
      toastErr(e);
      this._busy.stop();
    } finally {
      this.setData({ busy: false });
    }
  },

  async paint() {
    if (!this._pack) return;
    const seq = ++this._paintSeq;
    const w = chart.clampWindow(this._winStart, this._winCount, this._total);
    this._winStart = w.start;
    this._winCount = w.count;
    this.setData({ winText: `${this._winCount}/${this._total}` });
    const crossIndex = this._crossIndex;
    const drawer = (canvas, dpr) =>
      chart.drawPredict(canvas, this._pack, {
        dpr,
        winStart: this._winStart,
        winCount: this._winCount,
        crossIndex,
      });
    let layout = null;
    if (this._canvas) {
      layout = drawer(this._canvas, this._dpr);
    } else {
      const pack = await chart.bindCanvas(this, "pred", drawer);
      if (seq !== this._paintSeq) return;
      if (pack) {
        this._canvas = pack.canvas;
        this._dpr = pack.dpr;
        layout = pack.layout;
      }
    }
    if (seq !== this._paintSeq) return;
    this._layout = layout;
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
