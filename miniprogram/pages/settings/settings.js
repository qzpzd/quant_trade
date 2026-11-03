const { getBaseUrl, setBaseUrl, DEFAULT_BASE, suggestBases } = require("../../utils/config");
const api = require("../../utils/api");

Page({
  data: {
    baseUrl: "",
    suggests: [],
    busy: false,
    msg: "",
  },

  onShow() {
    this.setData({
      baseUrl: getBaseUrl(),
      suggests: suggestBases(),
    });
  },

  onInput(e) {
    this.setData({ baseUrl: e.detail.value });
  },

  pick(e) {
    const url = e.currentTarget.dataset.url;
    this.setData({ baseUrl: url });
    this.onSave();
  },

  onSave() {
    const url = setBaseUrl(this.data.baseUrl);
    getApp().globalData.baseUrl = url;
    this.setData({ baseUrl: url, msg: "已保存", suggests: suggestBases() });
    wx.showToast({ title: "已保存", icon: "success" });
  },

  onReset() {
    const url = setBaseUrl(DEFAULT_BASE);
    getApp().globalData.baseUrl = url;
    this.setData({ baseUrl: url, msg: "已恢复默认", suggests: suggestBases() });
  },

  async onTest() {
    this.onSave();
    this.setData({ busy: true, msg: "测试中…" });
    try {
      const r = await api.get("/api/health");
      const quote = await api.get("/api/quote/002195?start=2024-01-01");
      this.setData({
        msg: `连接成功：${(r && r.name) || "形迹"}；行情 ${quote.name} ${quote.close}`,
      });
    } catch (e) {
      this.setData({ msg: e.message || "连接失败" });
    } finally {
      this.setData({ busy: false });
    }
  },
});
