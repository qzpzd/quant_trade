const { getBaseUrl, isLocalHost } = require("./utils/config");
const { todayStr } = require("./utils/format");

App({
  globalData: {
    symbol: "002195",
    start: "2020-01-01",
    end: "",
    baseUrl: "",
  },

  onLaunch() {
    this.globalData.baseUrl = getBaseUrl();
    this.globalData.end = todayStr();
    if (isLocalHost(this.globalData.baseUrl)) {
      // 真机上 127.0.0.1 不可用，启动时轻提示一次
      try {
        const sys = wx.getSystemInfoSync();
        const isDevtools = sys.platform === "devtools";
        if (!isDevtools) {
          wx.showModal({
            title: "需要配置 API 地址",
            content:
              "真机不能访问 127.0.0.1。请到「更多 → 连接设置」改成电脑局域网 IP，例如 http://192.168.3.202:8765，并确认后端用 --host 0.0.0.0 启动。",
            confirmText: "去设置",
            success: (r) => {
              if (r.confirm) wx.navigateTo({ url: "/pages/settings/settings" });
            },
          });
        }
      } catch (e) {}
    }
  },

  setApiBase(url) {
    const { setBaseUrl } = require("./utils/config");
    this.globalData.baseUrl = setBaseUrl(url);
  },
});
