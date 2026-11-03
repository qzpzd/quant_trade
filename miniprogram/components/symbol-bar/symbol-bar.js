const api = require("../../utils/api");
const { rangeFromApp, setRange, pct, chgClass } = require("../../utils/format");

Component({
  data: {
    query: "",
    start: "",
    end: "",
    suggests: [],
  },
  lifetimes: {
    attached() {
      this.syncFromApp();
    },
  },
  pageLifetimes: {
    show() {
      this.syncFromApp();
    },
  },
  methods: {
    syncFromApp() {
      const r = rangeFromApp();
      this.setData({ query: r.symbol, start: r.start, end: r.end });
    },
    onQuery(e) {
      const query = e.detail.value || "";
      this.setData({ query });
      clearTimeout(this._t);
      this._t = setTimeout(() => this.search(query), 240);
    },
    async search(q) {
      const query = String(q || "").trim();
      if (!query) {
        this.setData({ suggests: [] });
        return;
      }
      try {
        const r = await api.get(`/api/search?q=${encodeURIComponent(query)}`);
        const suggests = (r.hits || []).map((h) => ({
          ...h,
          pctClass: chgClass(h.pct_chg),
          close: h.close != null ? Number(h.close).toFixed(2) : "",
        }));
        this.setData({ suggests });
      } catch (e) {
        this.setData({ suggests: [] });
      }
    },
    onStart(e) {
      this.setData({ start: e.detail.value });
      setRange({ start: e.detail.value });
    },
    onEnd(e) {
      this.setData({ end: e.detail.value });
      setRange({ end: e.detail.value });
    },
    pick(e) {
      this.apply(e.currentTarget.dataset.symbol);
    },
    async onConfirm() {
      let symbol = String(this.data.query || "").trim();
      if (!symbol) return;
      if (!/^\d{6}$/.test(symbol)) {
        await this.search(symbol);
        const first = (this.data.suggests || [])[0];
        if (!first) {
          wx.showToast({ title: "未找到匹配股票", icon: "none" });
          return;
        }
        symbol = first.symbol;
      }
      this.apply(symbol);
    },
    apply(symbol) {
      setRange({ symbol, start: this.data.start, end: this.data.end });
      this.setData({ query: symbol, suggests: [] });
      this.triggerEvent("change", {
        symbol,
        start: this.data.start,
        end: this.data.end,
      });
    },
  },
});
