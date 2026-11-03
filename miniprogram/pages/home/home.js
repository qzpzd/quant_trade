const api = require("../../utils/api");
const desk = require("../../utils/desk");
const { setSymbol, pct, chgClass, toastErr } = require("../../utils/format");
const { getBaseUrl, isLocalHost } = require("../../utils/config");

const PAGE_SIZE = 20;

Page({
  data: {
    busy: false,
    needLan: false,
    tab: "desk",
    searchQ: "",
    suggests: [],
    cache: null,
    buyCount: 0,
    sellCount: 0,
    alertSide: "buy",
    alertList: [],
    buys: [],
    sells: [],
    mode: "industry",
    cat: "all",
    cats: [],
    stocks: [],
    summary: null,
    watchSet: [],
    useGroups: true,
    groupNames: [],
    groupLabels: [],
    groupIndex: 0,
    groupKey: "",
    cards: [],
    deskMore: false,
    remain: 0,
    shown: PAGE_SIZE,
    metaText: "",
    sectorsStatus: "",
  },

  _stocks: [],
  _watch: new Set(),
  _summary: {},
  _groups: [],
  _timer: null,

  onShow() {
    let phone = false;
    try {
      phone = wx.getSystemInfoSync().platform !== "devtools";
    } catch (e) {}
    this.setData({ needLan: phone && isLocalHost(getBaseUrl()) });
    this.loadAll();
  },

  goSettings() {
    wx.navigateTo({ url: "/pages/settings/settings" });
  },

  setTab(e) {
    this.setData({ tab: e.currentTarget.dataset.tab });
    if (e.currentTarget.dataset.tab === "alerts") this.refreshAlertList();
  },

  setAlertSide(e) {
    this.setData({ alertSide: e.currentTarget.dataset.side });
    this.refreshAlertList();
  },

  refreshAlertList() {
    const side = this.data.alertSide;
    const raw = side === "buy" ? this.data.buys : this.data.sells;
    const alertList = (raw || []).map((a) => ({
      ...a,
      reasonText: ((a.reasons || []).slice(0, 2).map((r) => r.reason || r.source).filter(Boolean) || []).join("；"),
    }));
    this.setData({ alertList });
  },

  onSearchInput(e) {
    const searchQ = e.detail.value || "";
    this.setData({ searchQ });
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this.lookup(searchQ), 220);
  },

  async lookup(q) {
    const query = String(q || "").trim();
    if (!query) {
      this.setData({ suggests: [] });
      return;
    }
    const low = query.toLowerCase();
    let hits = [];
    if (this._stocks.length) {
      const scored = [];
      for (const s of this._stocks) {
        const code = String(s.symbol || "");
        const name = String(s.name || "").toLowerCase();
        let rank = -1;
        if (code === query || code.startsWith(query)) rank = 0;
        else if (name.startsWith(low) || String(s.name) === query) rank = 1;
        else if (name.includes(low) || code.includes(query)) rank = 2;
        if (rank >= 0) scored.push({ rank, s });
      }
      scored.sort((a, b) => a.rank - b.rank || String(a.s.symbol).localeCompare(String(b.s.symbol)));
      hits = scored.slice(0, 12).map((x) => x.s);
    }
    if (!hits.length) {
      try {
        const r = await api.get(`/api/search?q=${encodeURIComponent(query)}`);
        hits = r.hits || [];
      } catch (e) {
        hits = [];
      }
    }
    this.setData({
      suggests: hits.map((h) => ({
        ...h,
        pctText: h.pct_chg != null ? pct(h.pct_chg) : "",
        pctClass: chgClass(h.pct_chg),
      })),
    });
  },

  pickSuggest(e) {
    const symbol = e.currentTarget.dataset.symbol;
    this.setData({ searchQ: symbol, suggests: [] });
    setSymbol(symbol);
    wx.switchTab({ url: "/pages/quote/quote" });
  },

  async onSearchConfirm() {
    const q = String(this.data.searchQ || "").trim();
    if (!q) return;
    if (/^\d{6}$/.test(q)) {
      setSymbol(q);
      this.setData({ suggests: [] });
      wx.switchTab({ url: "/pages/quote/quote" });
      return;
    }
    await this.lookup(q);
    const first = (this.data.suggests || [])[0];
    if (first) {
      setSymbol(first.symbol);
      this.setData({ searchQ: first.symbol, suggests: [] });
      wx.switchTab({ url: "/pages/quote/quote" });
    } else {
      wx.showToast({ title: "未找到匹配股票", icon: "none" });
    }
  },

  async loadAll() {
    this.setData({ busy: true });
    try {
      const [cache, alerts, dash, wl] = await Promise.all([
        api.get("/api/cache/status"),
        api.get("/api/alerts"),
        api.get("/api/dashboard"),
        api.get("/api/watchlist"),
      ]);
      const buys = alerts.buys || [];
      const sells = alerts.sells || [];
      this._stocks = dash.stocks || [];
      this._summary = dash.summary || {};
      this._watch = new Set((wl.items || []).map((m) => m.symbol));
      this._stocks.forEach((s) => {
        if (s.watched) this._watch.add(s.symbol);
      });

      this.setData({
        cache,
        buys,
        sells,
        buyCount: buys.length,
        sellCount: sells.length,
        summary: this._summary,
      });
      this.refreshAlertList();
      this.rebuildCats();
      this.applyDesk();
      this.refreshSectorsStatus();
    } catch (e) {
      toastErr(e, "加载失败");
    } finally {
      this.setData({ busy: false });
    }
  },

  rebuildCats() {
    const cats = desk.buildFilterCats(this.data.mode, this._summary);
    let cat = this.data.cat;
    if (!cats.some((c) => c.id === cat)) cat = "all";
    this.setData({ cats, cat });
  },

  setMode(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({ mode, cat: "all", shown: PAGE_SIZE, groupKey: "", groupIndex: 0 });
    this.rebuildCats();
    this.applyDesk();
  },

  setCat(e) {
    this.setData({ cat: e.currentTarget.dataset.cat, shown: PAGE_SIZE, groupKey: "", groupIndex: 0 });
    this.applyDesk();
  },

  applyDesk() {
    const { mode, cat, shown } = this.data;
    const rows = desk.filteredStocks(this._stocks, { cat, q: "" }, this._watch);
    const useGroups = mode === "industry" || mode === "concept";
    let cards = [];
    let deskMore = false;
    let remain = 0;
    let groupNames = [];
    let groupLabels = [];
    let groupIndex = 0;
    let groupKey = this.data.groupKey;

    if (useGroups) {
      this._groups = desk.buildGroups(rows, mode);
      groupNames = this._groups.map((g) => g.name);
      groupLabels = this._groups.map((g) => `${g.name}（${g.count}）`);
      if (!groupKey || !groupNames.includes(groupKey)) {
        groupKey = groupNames[0] || "";
      }
      groupIndex = Math.max(0, groupNames.indexOf(groupKey));
      const list = (this._groups[groupIndex] && this._groups[groupIndex].items) || [];
      const slice = list.slice(0, shown);
      remain = Math.max(0, list.length - slice.length);
      deskMore = remain > 0;
      cards = slice.map((s) => ({
        ...desk.enrichCard(s, pct, chgClass),
        watched: this._watch.has(s.symbol),
      }));
    } else {
      this._groups = [];
      const slice = rows.slice(0, shown);
      remain = Math.max(0, rows.length - slice.length);
      deskMore = remain > 0;
      cards = slice.map((s) => ({
        ...desk.enrichCard(s, pct, chgClass),
        watched: this._watch.has(s.symbol),
      }));
    }

    const sum = this._summary || {};
    const metaText = `筛选 ${rows.length} / 缓存 ${this._stocks.length} · 涨停 ${sum.limit_up || 0} · 行业 ${Object.keys(sum.industries || {}).length} · 概念 ${Object.keys(sum.concepts || {}).length} · 偏多 ${(sum.stances && sum.stances["偏多"]) || 0}`;

    this.setData({
      useGroups,
      groupNames,
      groupLabels,
      groupIndex,
      groupKey,
      cards,
      deskMore,
      remain,
      metaText,
    });
  },

  onGroupPick(e) {
    const groupIndex = Number(e.detail.value);
    const groupKey = this.data.groupNames[groupIndex] || "";
    this.setData({ groupIndex, groupKey, shown: PAGE_SIZE });
    this.applyDesk();
  },

  loadMore() {
    this.setData({ shown: this.data.shown + PAGE_SIZE });
    this.applyDesk();
  },

  openQuote(e) {
    const symbol = e.currentTarget.dataset.symbol;
    if (!symbol) return;
    setSymbol(symbol);
    wx.switchTab({ url: "/pages/quote/quote" });
  },

  async toggleWatch(e) {
    const symbol = e.currentTarget.dataset.symbol;
    try {
      if (this._watch.has(symbol)) {
        await api.del(`/api/watchlist/${symbol}`);
        this._watch.delete(symbol);
      } else {
        await api.post("/api/watchlist", { symbol });
        this._watch.add(symbol);
      }
      this.applyDesk();
    } catch (err) {
      toastErr(err);
    }
  },

  async refreshSectorsStatus() {
    try {
      const s = await api.get("/api/sectors");
      let sectorsStatus = "分类未生成";
      if (s.building) sectorsStatus = `正在拉取分类… 行业股 ${s.industry_count || 0}`;
      else if (s.built_at) {
        sectorsStatus = `分类 ${s.built_at} · 行业 ${s.industry_count} · 概念股 ${s.concept_stock_count}`;
      }
      this.setData({ sectorsStatus });
    } catch (e) {
      this.setData({ sectorsStatus: e.message || "" });
    }
  },

  async onRefreshSectors() {
    this.setData({ busy: true });
    try {
      await api.post("/api/sectors/refresh", {});
      wx.showToast({ title: "已触发刷新", icon: "success" });
      setTimeout(() => this.loadAll(), 1500);
    } catch (e) {
      toastErr(e);
      this.setData({ busy: false });
    }
  },

  onPullDownRefresh() {
    this.loadAll().finally(() => wx.stopPullDownRefresh());
  },

  onReload() {
    this.loadAll();
  },

  async onRefreshCache() {
    this.setData({ busy: true });
    try {
      await api.post("/api/cache/update", {});
      wx.showToast({ title: "已触发更新", icon: "success" });
      setTimeout(() => this.loadAll(), 1200);
    } catch (e) {
      toastErr(e);
      this.setData({ busy: false });
    }
  },

  async onRefreshAlerts() {
    this.setData({ busy: true });
    try {
      await api.post("/api/alerts/refresh", {});
      wx.showToast({ title: "已重扫", icon: "success" });
      await this.loadAll();
    } catch (e) {
      toastErr(e);
      this.setData({ busy: false });
    }
  },
});
