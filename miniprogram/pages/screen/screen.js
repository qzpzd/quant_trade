const api = require("../../utils/api");
const { setSymbol, pct, chgClass, toastErr } = require("../../utils/format");
const { createBusy, busyData } = require("../../utils/busy");

const UNIV = [
  { key: "low20", label: "主板低价股" },
  { key: "demo", label: "核心样本" },
  { key: "sz50", label: "上证50" },
  { key: "hs300", label: "沪深300" },
  { key: "zz500", label: "中证500" },
];

const PRESETS = [
  { id: "rsi", name: "RSI超卖", conditions: [{ field: "rsi14", op: "<", value: "30" }] },
  { id: "macd", name: "MACD金叉", conditions: [{ field: "macd_cross", op: "=", value: "golden" }] },
  { id: "ma", name: "多头排列", conditions: [{ field: "ma_align", op: "=", value: "bull" }] },
  { id: "vol", name: "放量", conditions: [{ field: "vol_ratio", op: ">", value: "1.5" }] },
  {
    id: "combo",
    name: "超卖+放量",
    conditions: [
      { field: "rsi14", op: "<", value: "35" },
      { field: "vol_ratio", op: ">", value: "1.2" },
    ],
  },
  { id: "limit_up", name: "底部首板", conditions: [{ field: "first_limit_up", op: "=", value: "yes" }] },
  { id: "pullback", name: "缩量回踩", conditions: [{ field: "bull_pullback", op: "=", value: "yes" }] },
  { id: "vol_break", name: "底部放量", conditions: [{ field: "vol_breakout", op: "=", value: "yes" }] },
  {
    id: "value",
    name: "低估值",
    conditions: [
      { field: "pe", op: ">", value: "0" },
      { field: "pe", op: "<", value: "20" },
      { field: "pb", op: "<", value: "2" },
    ],
  },
  {
    id: "quality",
    name: "绩优低估值",
    conditions: [
      { field: "pe", op: ">", value: "0" },
      { field: "pe", op: "<", value: "20" },
      { field: "pb", op: "<", value: "3" },
      { field: "roe", op: ">", value: "10" },
      { field: "net_profit_yoy", op: ">", value: "0" },
    ],
  },
];

const OPS = [">", ">=", "<", "<=", "="];
const MODES = [
  { key: "dynamic", label: "动态条件" },
  { key: "static", label: "静态名单" },
];

Page({
  data: {
    univLabels: UNIV.map((u) => u.label),
    univIndex: 1,
    presets: PRESETS,
    preset: "rsi",
    fields: [],
    fieldLabels: [],
    ops: OPS,
    conds: [],
    busy: false,
    ...busyData(),
    hits: [],
    hint: "选择预设或自定义条件后选股；可保存后下次下拉选用",
    saved: [],
    savedLabels: ["（不选，用下方条件）"],
    savedIndex: 0,
    saveName: "",
    modeLabels: MODES.map((m) => m.label),
    modeIndex: 0,
  },

  _busy: null,
  _savedRaw: [],

  onLoad() {
    this._busy = createBusy(this);
  },

  onShow() {
    this.boot();
  },

  async boot() {
    try {
      const [fieldsPack, screens] = await Promise.all([
        api.get("/api/screen/fields"),
        api.get("/api/screens").catch(() => ({ items: [] })),
      ]);
      const fields = fieldsPack.fields || fieldsPack || [];
      const fieldList = Array.isArray(fields) ? fields : [];
      const items = screens.items || screens || [];
      this._savedRaw = items;
      this.setData({
        fields: fieldList,
        fieldLabels: fieldList.map((f) => f.label || f.id),
        saved: items,
        savedLabels: ["（不选，用下方条件）"].concat(
          items.map((s) => `${s.name}（${s.mode === "static" ? "静态" : "动态"}）`)
        ),
        savedIndex: 0,
      });
      if (!this.data.conds.length) this.pickPreset({ currentTarget: { dataset: { id: "rsi" } } });
    } catch (e) {
      toastErr(e);
      const fieldList = [
        { id: "rsi14", label: "RSI(14)" },
        { id: "vol_ratio", label: "量比" },
        { id: "macd_cross", label: "MACD交叉" },
        { id: "ma_align", label: "均线排列" },
      ];
      this.setData({
        fields: fieldList,
        fieldLabels: fieldList.map((f) => f.label),
      });
      this.pickPreset({ currentTarget: { dataset: { id: "rsi" } } });
    }
  },

  onUniv(e) {
    this.setData({ univIndex: Number(e.detail.value) });
  },
  onMode(e) {
    this.setData({ modeIndex: Number(e.detail.value) });
  },
  onSaveName(e) {
    this.setData({ saveName: e.detail.value });
  },

  async onPickSaved(e) {
    const idx = Number(e.detail.value);
    this.setData({ savedIndex: idx });
    if (idx <= 0) return;
    const item = this._savedRaw[idx - 1];
    if (!item) return;
    await this.applySaved(item.id);
  },

  pickPreset(e) {
    const id = e.currentTarget.dataset.id;
    const p = PRESETS.find((x) => x.id === id) || PRESETS[0];
    const fields = this.data.fields;
    const conds = p.conditions.map((c) => {
      let fieldIndex = fields.findIndex((f) => f.id === c.field);
      if (fieldIndex < 0) fieldIndex = 0;
      const opIndex = Math.max(0, OPS.indexOf(c.op));
      return { fieldIndex, opIndex, value: String(c.value) };
    });
    this.setData({ preset: id, conds, savedIndex: 0 });
  },

  addCond() {
    const conds = this.data.conds.concat([{ fieldIndex: 0, opIndex: 0, value: "" }]);
    this.setData({ conds });
  },

  rmCond(e) {
    const i = Number(e.currentTarget.dataset.i);
    const conds = this.data.conds.filter((_, idx) => idx !== i);
    this.setData({ conds });
  },

  onField(e) {
    const i = Number(e.currentTarget.dataset.i);
    const conds = this.data.conds.slice();
    conds[i].fieldIndex = Number(e.detail.value);
    this.setData({ conds });
  },

  onOp(e) {
    const i = Number(e.currentTarget.dataset.i);
    const conds = this.data.conds.slice();
    conds[i].opIndex = Number(e.detail.value);
    this.setData({ conds });
  },

  onVal(e) {
    const i = Number(e.currentTarget.dataset.i);
    const conds = this.data.conds.slice();
    conds[i].value = e.detail.value;
    this.setData({ conds });
  },

  buildConditions() {
    const { fields, conds } = this.data;
    return conds
      .map((c) => {
        const f = fields[c.fieldIndex];
        if (!f) return null;
        let value = c.value;
        if (f.type === "number" || (!f.type && /^-?\d+(\.\d+)?$/.test(String(value)))) {
          value = Number(value);
        }
        return { field: f.id, op: OPS[c.opIndex], value };
      })
      .filter(Boolean);
  },

  async onSave() {
    const name = (this.data.saveName || "").trim();
    if (!name) {
      wx.showToast({ title: "请填写条件名称", icon: "none" });
      return;
    }
    const conditions = this.buildConditions();
    if (!conditions.length) {
      wx.showToast({ title: "请添加条件", icon: "none" });
      return;
    }
    const mode = MODES[this.data.modeIndex].key;
    this.setData({ busy: true });
    this._busy.start("正在保存条件…");
    try {
      await api.post("/api/screens", {
        name,
        mode,
        universe: UNIV[this.data.univIndex].key,
        conditions,
        hits: mode === "static" ? this.data.hits || [] : [],
        limit: 50,
      });
      this.setData({ saveName: "" });
      this._busy.stop("已保存");
      wx.showToast({ title: "已保存", icon: "success" });
      await this.boot();
    } catch (e) {
      toastErr(e);
      this._busy.stop();
    } finally {
      this.setData({ busy: false });
    }
  },

  async onRun() {
    const conditions = this.buildConditions();
    if (!conditions.length) {
      wx.showToast({ title: "请添加条件", icon: "none" });
      return;
    }
    this.setData({ busy: true, hint: "选股中…" });
    this._busy.start("按条件过滤样本池（未缓存的股票会现场拉取）…");
    try {
      const r = await api.post("/api/screen", {
        universe: UNIV[this.data.univIndex].key,
        conditions,
        limit: 50,
      });
      const hits = ((r && r.hits) || []).map((h) => ({
        ...h,
        pctText: pct(h.pct_chg),
        pctClass: chgClass(h.pct_chg),
      }));
      this.setData({
        hits,
        hint: hits.length ? "" : `扫描 ${r.scanned || 0} 只，无命中`,
      });
      this._busy.stop(hits.length ? `选股完成 · ${hits.length} 只` : "选股完成");
    } catch (e) {
      toastErr(e);
      this.setData({ hint: e.message || "失败" });
      this._busy.stop();
    } finally {
      this.setData({ busy: false });
    }
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

  async applySaved(id) {
    this.setData({ busy: true });
    this._busy.start("加载已保存条件…");
    try {
      const item = await api.get(`/api/screens/${id}`);
      if (item.conditions && item.conditions.length) {
        const fields = this.data.fields;
        const conds = item.conditions.map((c) => {
          let fieldIndex = fields.findIndex((f) => f.id === c.field);
          if (fieldIndex < 0) fieldIndex = 0;
          const opIndex = Math.max(0, OPS.indexOf(c.op || ">"));
          return { fieldIndex, opIndex, value: String(c.value) };
        });
        const univIndex = Math.max(
          0,
          UNIV.findIndex((u) => u.key === item.universe)
        );
        this.setData({
          conds,
          univIndex: univIndex < 0 ? 1 : univIndex,
          saveName: item.name || "",
          modeIndex: item.mode === "static" ? 1 : 0,
        });
      }
      if (item.hits && item.hits.length) {
        const hits = item.hits.map((h) => ({
          ...h,
          pctText: pct(h.pct_chg),
          pctClass: chgClass(h.pct_chg),
        }));
        this.setData({ hits, hint: `已保存名单 ${hits.length} 只` });
        this._busy.stop("已加载名单");
        return;
      }
      this._busy.stop();
      await this.onRun();
    } catch (err) {
      toastErr(err);
      this._busy.stop();
    } finally {
      this.setData({ busy: false });
    }
  },

  async loadSaved(e) {
    const id = e.currentTarget.dataset.id;
    const idx = this._savedRaw.findIndex((s) => s.id === id);
    this.setData({ savedIndex: idx >= 0 ? idx + 1 : 0 });
    await this.applySaved(id);
  },

  async delSaved(e) {
    const id = e.currentTarget.dataset.id;
    try {
      await api.del(`/api/screens/${id}`);
      wx.showToast({ title: "已删除", icon: "success" });
      await this.boot();
    } catch (err) {
      toastErr(err);
    }
  },

  openQuote(e) {
    setSymbol(e.currentTarget.dataset.symbol);
    wx.switchTab({ url: "/pages/quote/quote" });
  },
});
