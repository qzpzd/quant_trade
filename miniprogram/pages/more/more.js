const api = require("../../utils/api");
const { getBaseUrl, isLocalHost } = require("../../utils/config");

Page({
  data: {
    baseUrl: "",
    busy: false,
    health: "",
    needLan: false,
  },

  onShow() {
    const baseUrl = getBaseUrl();
    let phone = false;
    try {
      phone = wx.getSystemInfoSync().platform !== "devtools";
    } catch (e) {}
    this.setData({
      baseUrl,
      needLan: phone && isLocalHost(baseUrl),
    });
  },

  go(e) {
    wx.navigateTo({ url: e.currentTarget.dataset.url });
  },

  switchTab() {},

  async ping() {
    this.setData({ busy: true, health: "" });
    try {
      const r = await api.get("/api/health");
      this.setData({
        health: r && r.ok ? `连接成功：${r.name || "形迹"}` : JSON.stringify(r),
      });
    } catch (e) {
      this.setData({ health: e.message || "失败" });
    } finally {
      this.setData({ busy: false });
    }
  },
});
