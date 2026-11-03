const api = require("../../utils/api");
const chart = require("../../utils/chart");
const {
  rangeFromApp,
  setSymbol,
  num,
  toastErr,
} = require("../../utils/format");
const { createBusy, busyData } = require("../../utils/busy");

const UNIV = [
  { key: "demo", label: "核心样本" },
  { key: "low20", label: "主板低价股" },
  { key: "sz50", label: "上证50" },
  { key: "hs300", label: "沪深300" },
  { key: "zz500", label: "中证500" },
];
const LOOKS = [
  { v: 30, label: "最近30日" },
  { v: 60, label: "最近60日" },
  { v: 90, label: "最近90日" },
  { v: 120, label: "最近120日" },
  { v: 0, label: "全部历史" },
];

Page({
  data: {
    simStart: "",
    simEnd: "",
    univLabels: UNIV.map((u) => u.label),
    univIndex: 0,
    lookLabels: LOOKS.map((x) => x.label),
    lookIndex: 1,
    busy: false,
    ...busyData(),
    picks: [],
    study: "",
    boxMode: false,
    hasBox: false,
    boxHint: "未框选",
    saveName: "",
    patterns: [],
    patternLabels: ["（不选已存形态）"],
    patternIndex: 0,
    includeCurrent: true,
  },

  _bars: [],
  _layout: null,
  _sel: null,
  _touch: null,
  _winStart: 0,
  _winCount: 80,
  _crossIndex: null,
  _busy: null,
  _patternsRaw: [],

  onLoad() {
    this._busy = createBusy(this);
  },

  onShow() {
    this.loadPatterns();
    this.loadKline();
  },

  onSymbolChange() {
    this._sel = null;
    this.setData({
      hasBox: false,
      boxMode: false,
      boxHint: "未框选",
      simStart: "",
      simEnd: "",
      picks: [],
      study: "",
    });
    this.loadKline();
  },

  onSimStart(e) {
    this.setData({ simStart: e.detail.value, hasBox: true, boxHint: "日期已设" });
    this.paint();
  },
  onSimEnd(e) {
    this.setData({ simEnd: e.detail.value, hasBox: true, boxHint: "日期已设" });
    this.paint();
  },
  onUniv(e) {
    this.setData({ univIndex: Number(e.detail.value) });
  },
  onLook(e) {
    this.setData({ lookIndex: Number(e.detail.value) });
  },
  onSaveName(e) {
    this.setData({ saveName: e.detail.value });
  },
  toggleInclude() {
    this.setData({ includeCurrent: !this.data.includeCurrent });
  },

  async loadPatterns() {
    try {
      const r = await api.get("/api/patterns");
      const items = (r && r.items) || [];
      this._patternsRaw = items;
      this.setData({
        patterns: items,
        patternLabels: ["（不选已存形态）"].concat(
          items.map((p) => `${p.name} · ${p.symbol} ${p.start}~${p.end}`)
        ),
      });
    } catch (e) {
      this._patternsRaw = [];
      this.setData({ patterns: [], patternLabels: ["（不选已存形态）"] });
    }
  },

  onPickPattern(e) {
    const idx = Number(e.detail.value);
    this.setData({ patternIndex: idx });
    if (idx <= 0) return;
    const p = this._patternsRaw[idx - 1];
    if (!p) return;
    this.applyPattern(p);
  },

  selectPatternRow(e) {
    const id = e.currentTarget.dataset.id;
    const idx = this._patternsRaw.findIndex((p) => p.id === id);
    if (idx < 0) return;
    this.setData({ patternIndex: idx + 1 });
    this.applyPattern(this._patternsRaw[idx]);
  },

  applyPattern(p) {
    setSymbol(p.symbol);
    this.setData({
      simStart: p.start || "",
      simEnd: p.end || "",
      hasBox: !!(p.start && p.end),
      boxHint: p.start && p.end ? `${p.start} ~ ${p.end}` : "已选形态",
    });
    this.loadKline();
  },

  async onSavePattern() {
    const name = (this.data.saveName || "").trim();
    const { simStart, simEnd } = this.data;
    if (!name) {
      wx.showToast({ title: "请填写形态名称", icon: "none" });
      return;
    }
    if (!simStart || !simEnd) {
      wx.showToast({ title: "请先框选或选日期", icon: "none" });
      return;
    }
    const { symbol } = rangeFromApp();
    this.setData({ busy: true });
    this._busy.start("保存形态…");
    try {
      await api.post("/api/patterns", { name, symbol, start: simStart, end: simEnd });
      this.setData({ saveName: "" });
      await this.loadPatterns();
      this._busy.stop("形态已保存");
      wx.showToast({ title: "已保存", icon: "success" });
    } catch (e) {
      toastErr(e);
      this._busy.stop();
    } finally {
      this.setData({ busy: false });
    }
  },

  async delPattern(e) {
    const id = e.currentTarget.dataset.id;
    try {
      await api.del(`/api/patterns/${id}`);
      wx.showToast({ title: "已删除", icon: "success" });
      await this.loadPatterns();
    } catch (err) {
      toastErr(err);
    }
  },

  toggleBox() {
    const boxMode = !this.data.boxMode;
    this.setData({
      boxMode,
      boxHint: boxMode ? "请在图上拖出区间" : this.data.hasBox ? "已选区间" : "未框选",
    });
    if (boxMode) {
      wx.showToast({ title: "在 K 线上拖动画框", icon: "none" });
    }
  },

  clearBox() {
    this._sel = null;
    this.setData({
      hasBox: false,
      boxMode: false,
      boxHint: "未框选",
      simStart: "",
      simEnd: "",
    });
    this.paint();
  },

  async loadKline() {
    const { symbol, start, end } = rangeFromApp();
    this.setData({ busy: true });
    try {
      const quote = await api.get(
        `/api/quote/${encodeURIComponent(symbol)}?start=${start}&end=${end}`
      );
      this._bars = quote.bars || [];
      this._winCount = Math.min(90, this._bars.length);
      this._winStart = Math.max(0, this._bars.length - this._winCount);
      this._sel = null;
      this.setData({ hasBox: false, boxHint: "未框选" });
      await this.paint();
    } catch (e) {
      toastErr(e);
    } finally {
      this.setData({ busy: false });
    }
  },

  visible() {
    const all = this._bars || [];
    const { start, count } = chart.clampWindow(this._winStart, this._winCount, all.length || 0);
    this._winStart = start;
    this._winCount = count;
    return all.slice(start, start + count);
  },

  selectionForDraw(vis) {
    if (!this._sel) return null;
    return { i0: this._sel.i0, i1: this._sel.i1 };
  },

  async paint() {
    const vis = this.visible();
    // 仅在已框选 / 手动设日期后画黄框；初始不画
    let sel = this.selectionForDraw(vis);
    if (!sel && this.data.hasBox && this.data.simStart && this.data.simEnd && vis.length) {
      let i0 = -1;
      let i1 = -1;
      for (let i = 0; i < vis.length; i++) {
        const d = vis[i].date;
        if (d >= this.data.simStart && i0 < 0) i0 = i;
        if (d <= this.data.simEnd) i1 = i;
      }
      if (i0 >= 0 && i1 >= i0) sel = { i0, i1 };
    }
    const pack = await chart.bindCanvas(this, "simk", (canvas, dpr) => {
      return chart.drawCandles(canvas, vis, {
        dpr,
        selection: sel,
        showVolume: true,
        crossIndex: this.data.boxMode ? null : this._crossIndex,
      });
    });
    this._layout = pack && pack.layout;
  },

  setCrossTip(idx) {
    this._crossIndex = idx;
  },

  applySelToDates(vis) {
    if (!this._sel || !vis.length) return;
    const a = Math.min(this._sel.i0, this._sel.i1);
    const b = Math.max(this._sel.i0, this._sel.i1);
    const s = vis[a];
    const e = vis[b];
    if (!s || !e) return;
    this.setData({
      simStart: s.date,
      simEnd: e.date,
      hasBox: true,
      boxHint: `${s.date} ~ ${e.date}`,
      boxMode: false,
    });
  },

  onTouchStart(e) {
    const t = (e.touches || [])[0];
    if (!t || !this._layout) return;
    if (!this.data.boxMode) {
      // 平移 K 线，竖线钉在触点
      const crossRel = chart.xToIndex(t.x, this._layout);
      this._touch = { mode: "pan", x0: t.x, start0: this._winStart, crossRel };
      this._crossIndex = crossRel;
      this.paint();
      return;
    }
    const idx = chart.xToIndex(t.x, this._layout);
    this._sel = { i0: idx, i1: idx };
    this._touch = { mode: "box", active: true };
    this._crossIndex = null;
    this.paint();
  },

  onTouchMove(e) {
    const t = (e.touches || [])[0];
    if (!t || !this._touch) return;
    if (this._touch.mode === "pan") {
      const slot = (this._layout && this._layout.slot) || 8;
      const shift = Math.round(-(t.x - this._touch.x0) / Math.max(4, slot));
      this._winStart = this._touch.start0 + shift;
      if (this._touch.crossRel != null) this._crossIndex = this._touch.crossRel;
      this.paint();
      return;
    }
    if (this._touch.mode === "box" && this._sel) {
      this._sel.i1 = chart.xToIndex(t.x, this._layout);
      this.paint();
    }
  },

  onTouchEnd() {
    if (this._touch && this._touch.mode === "box") {
      this.applySelToDates(this.visible());
      this.paint();
      wx.showToast({ title: "已框选形态区间", icon: "success" });
    }
    this._touch = null;
  },

  async onSync() {
    this.setData({ busy: true });
    try {
      await api.post("/api/universe/sync", { universe: UNIV[this.data.univIndex].key });
      await this._busy.pollSync(api);
    } catch (e) {
      toastErr(e);
      this._busy.stop();
    } finally {
      this.setData({ busy: false });
    }
  },

  async onRun() {
    const { symbol } = rangeFromApp();
    const { simStart, simEnd, univIndex, lookIndex, patternIndex, includeCurrent } = this.data;
    const patternIds =
      patternIndex > 0 && this._patternsRaw[patternIndex - 1]
        ? [this._patternsRaw[patternIndex - 1].id]
        : [];
    if (!patternIds.length && (!simStart || !simEnd)) {
      wx.showToast({ title: "请框选日期或选用已存形态", icon: "none" });
      return;
    }
    this.setData({ busy: true, picks: [], study: "" });
    this._busy.start("在缓存股票的近期窗口里匹配价+量+换手相似形态…");
    try {
      const body = {
        universe: UNIV[univIndex].key,
        top_n: 12,
        lookback_days: LOOKS[lookIndex].v,
        pattern_ids: patternIds,
        include_current: includeCurrent && !!(simStart && simEnd),
        analyze: true,
      };
      if (body.include_current) {
        body.symbol = symbol;
        body.start = simStart;
        body.end = simEnd;
      }
      const r = await api.post("/api/similar", body);
      const raw = r.matches || r.picks || r.hits || [];
      const picks = raw.map((m) => ({
        ...m,
        corrText: num(m.corr ?? m.score ?? m.similarity, 3),
      }));
      let study = "";
      if (r.study) {
        study =
          typeof r.study === "string"
            ? r.study
            : `样本 ${r.study.n || picks.length}；后续中位收益 ${num(r.study.median_return_pct)}%`;
      }
      this.setData({ picks, study: study || `匹配 ${picks.length} 条` });
      this._busy.stop("形态匹配完成");
    } catch (e) {
      toastErr(e);
      this._busy.stop();
    } finally {
      this.setData({ busy: false });
    }
  },

  openQuote(e) {
    setSymbol(e.currentTarget.dataset.symbol);
    wx.switchTab({ url: "/pages/quote/quote" });
  },
});
