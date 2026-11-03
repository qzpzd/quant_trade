const api = require("../../utils/api");

Page({
  data: {
    year: 0,
    month: 0,
    title: "",
    weeks: ["一", "二", "三", "四", "五", "六", "日"],
    days: [],
    monthThemes: [],
    selected: "",
    detailItems: [],
    detailHint: "点击某一天查看事件",
  },

  onShow() {
    const now = new Date();
    if (!this.data.year) {
      this.setData({ year: now.getFullYear(), month: now.getMonth() + 1 });
    }
    this.loadMonth();
  },

  prevMonth() {
    let { year, month } = this.data;
    month -= 1;
    if (month < 1) {
      month = 12;
      year -= 1;
    }
    this.setData({ year, month });
    this.loadMonth();
  },

  nextMonth() {
    let { year, month } = this.data;
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
    this.setData({ year, month });
    this.loadMonth();
  },

  thisMonth() {
    const now = new Date();
    this.setData({ year: now.getFullYear(), month: now.getMonth() + 1 });
    this.loadMonth();
  },

  async loadMonth() {
    const { year, month } = this.data;
    try {
      const data = await api.get(`/api/calendar?year=${year}&month=${month}&live=1`);
      const monthMeta = data.month_themes || {};
      const themeList = Array.isArray(monthMeta)
        ? monthMeta
        : monthMeta.themes || data.themes || [];
      const themes = themeList.map((t) =>
        typeof t === "string" ? t : t.name || t.title || String(t)
      );
      if (monthMeta.note) themes.push(monthMeta.note);
      const eventDates = new Set();
      for (const d of data.days || []) {
        if (!d || !d.date) continue;
        const flags = d.flags || {};
        const has =
          (d.events && d.events.length) ||
          flags.has_event ||
          flags.has_major ||
          flags.has_report;
        if (has) eventDates.add(String(d.date).slice(0, 10));
      }

      const first = new Date(year, month - 1, 1);
      // JS: 0=Sun ... convert to Mon-first
      let pad = first.getDay() - 1;
      if (pad < 0) pad = 6;
      const lastDate = new Date(year, month, 0).getDate();
      const days = [];
      for (let i = 0; i < pad; i++) {
        days.push({ key: `e${i}`, empty: true, label: "", date: "", hasEvent: false });
      }
      for (let d = 1; d <= lastDate; d++) {
        const date = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
        days.push({
          key: date,
          empty: false,
          label: String(d),
          date,
          hasEvent: eventDates.has(date),
        });
      }
      this.setData({
        title: `${year}年${month}月`,
        monthThemes: themes,
        days,
        detailHint: data.note || "点击某一天查看事件",
      });
    } catch (e) {
      wx.showToast({ title: e.message || "加载失败", icon: "none" });
    }
  },

  async selectDay(e) {
    const date = e.currentTarget.dataset.date;
    if (!date) return;
    this.setData({ selected: date, detailItems: [], detailHint: "加载中…" });
    try {
      const d = await api.get(`/api/calendar/day?date=${encodeURIComponent(date)}&live=1`);
      const themeObj = d.month_themes || {};
      const themeStrs = (themeObj.themes || []).map((t) =>
        typeof t === "string" ? { title: t, source: "本月题材" } : t
      );
      const items = []
        .concat(d.events || [])
        .concat(d.live_events || [])
        .concat(d.nearby_major || [])
        .concat(themeStrs);
      const detailItems = items.map((x) =>
        typeof x === "string"
          ? { title: x }
          : {
              title: x.title || x.name || x.text || x.headline,
              source: x.source || x.category || x.kind || x.level || "",
              time: x.time || x.published_at || x.date || "",
            }
      );
      this.setData({
        detailItems,
        detailHint: detailItems.length ? "" : d.note || "当日暂无内置事件",
      });
    } catch (err) {
      this.setData({ detailHint: err.message || "加载失败" });
    }
  },
});
