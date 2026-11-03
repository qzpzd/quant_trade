const api = require("../../utils/api");
const desk = require("../../utils/desk");
const { setSymbol, pct, chgClass, toastErr } = require("../../utils/format");

Page({
  data: { cards: [] },

  onShow() {
    this.load();
  },

  async load() {
    try {
      const [wl, dash] = await Promise.all([
        api.get("/api/watchlist"),
        api.get("/api/dashboard").catch(() => ({ stocks: [] })),
      ]);
      const items = wl.items || [];
      const byCode = {};
      (dash.stocks || []).forEach((s) => {
        byCode[s.symbol] = s;
      });
      const cards = items.map((m) => {
        const s = byCode[m.symbol] || { symbol: m.symbol, name: m.name };
        return {
          ...desk.enrichCard(s, pct, chgClass),
          name: s.name || m.name || m.symbol,
        };
      });
      this.setData({ cards });
    } catch (e) {
      toastErr(e);
    }
  },

  openQuote(e) {
    setSymbol(e.currentTarget.dataset.symbol);
    wx.switchTab({ url: "/pages/quote/quote" });
  },

  async onRemove(e) {
    const symbol = e.currentTarget.dataset.symbol;
    try {
      await api.del(`/api/watchlist/${symbol}`);
      this.load();
    } catch (err) {
      toastErr(err);
    }
  },

  onPullDownRefresh() {
    this.load().finally(() => wx.stopPullDownRefresh());
  },
});
