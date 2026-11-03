const STORAGE_KEY = "xingji_api_base";
const DEFAULT_BASE = "http://127.0.0.1:8765";

function getBaseUrl() {
  try {
    const v = wx.getStorageSync(STORAGE_KEY);
    if (v && typeof v === "string" && v.trim()) return v.trim().replace(/\/$/, "");
  } catch (e) {}
  return DEFAULT_BASE;
}

function setBaseUrl(url) {
  const clean = String(url || "").trim().replace(/\/$/, "");
  wx.setStorageSync(STORAGE_KEY, clean || DEFAULT_BASE);
  return getBaseUrl();
}

/** 常见本机/局域网候选，方便真机连接 */
function suggestBases() {
  const list = [
    "http://127.0.0.1:8765",
    "http://192.168.3.202:8765",
    "http://10.158.152.183:8765",
  ];
  const cur = getBaseUrl();
  if (cur && !list.includes(cur)) list.unshift(cur);
  return list;
}

function isLocalHost(url) {
  return /:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/i.test(String(url || ""));
}

module.exports = {
  STORAGE_KEY,
  DEFAULT_BASE,
  getBaseUrl,
  setBaseUrl,
  suggestBases,
  isLocalHost,
};
