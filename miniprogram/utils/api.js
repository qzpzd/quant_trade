const { getBaseUrl, isLocalHost } = require("./config");

function errText(detail) {
  if (detail == null) return "请求失败";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((x) => (x && x.msg) || JSON.stringify(x)).join("; ");
  }
  if (typeof detail === "object" && detail.msg) return detail.msg;
  try {
    return JSON.stringify(detail);
  } catch (e) {
    return String(detail);
  }
}

function phoneHint(base) {
  if (!isLocalHost(base)) return "";
  return " 当前是 127.0.0.1，真机请到「设置」改成电脑局域网 IP（如 http://192.168.3.202:8765），后端需 --host 0.0.0.0。";
}

function request(path, opts = {}) {
  const base = getBaseUrl();
  const url = path.startsWith("http") ? path : `${base}${path}`;
  const method = (opts.method || "GET").toUpperCase();
  const header = {
    "Content-Type": "application/json",
    ...(opts.header || {}),
  };
  let data = opts.data;
  if (data != null && typeof data === "object" && method !== "GET") {
    data = JSON.stringify(data);
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url,
      method,
      header,
      data,
      timeout: opts.timeout || 180000,
      success(res) {
        const body = res.data;
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body);
          return;
        }
        const detail = body && (body.detail != null ? body.detail : body);
        reject(new Error(errText(detail) || `HTTP ${res.statusCode}`));
      },
      fail(err) {
        const msg = (err && err.errMsg) || "网络错误";
        reject(
          new Error(
            `${msg}。请确认后端已启动（uvicorn --host 0.0.0.0 --port 8765）。${phoneHint(base)}`
          )
        );
      },
    });
  });
}

function get(path, data) {
  return request(path, { method: "GET", data });
}

function post(path, data) {
  return request(path, { method: "POST", data: data || {} });
}

function del(path) {
  return request(path, { method: "DELETE" });
}

module.exports = {
  request,
  get,
  post,
  del,
  errText,
};
