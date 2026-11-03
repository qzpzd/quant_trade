"""动态大屏：页面通过 catalog.json /api/catalog 跟随目录变化。"""

from __future__ import annotations

from pathlib import Path

from .catalog import write_catalog

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>涨跌阶段 · MA 综合分析大屏</title>
<style>
:root {
  --bg:#0e100c; --panel:#161910; --line:#2c3224; --text:#efe7d6;
  --muted:#8b8473; --accent:#e6ff4a; --rise:#e4454a; --fall:#2ea574;
}
* { box-sizing:border-box; }
body {
  margin:0; font-family:"Segoe UI","Microsoft YaHei",sans-serif;
  background:var(--bg); color:var(--text); line-height:1.45;
}
header.top {
  position:sticky; top:0; z-index:10;
  background:rgba(14,16,12,.94); border-bottom:1px solid var(--line);
  padding:14px 20px;
}
header.top h1 { margin:0 0 4px; font-size:20px; color:var(--accent); }
.meta { font-size:12px; color:var(--muted); margin-bottom:8px; }
.nav {
  display:flex; flex-wrap:wrap; gap:6px; max-height:72px; overflow:auto;
}
.nav a {
  color:var(--muted); text-decoration:none; font-size:12px;
  border:1px solid var(--line); padding:2px 8px; border-radius:4px;
}
.nav a:hover { color:#111; background:var(--accent); border-color:var(--accent); }
main { padding:16px 20px 40px; }
.insight {
  background:var(--panel); border:1px dashed var(--line);
  padding:12px 16px; margin-bottom:18px; border-radius:8px;
}
.insight h3 { margin:0 0 8px; font-size:14px; color:var(--accent); }
.insight ul { margin:0; padding-left:18px; color:var(--muted); font-size:13px; }
.card {
  background:var(--panel); border:1px solid var(--line);
  border-radius:10px; padding:14px; margin-bottom:18px;
}
.card h2 { margin:0 0 6px; font-size:16px; }
.card .sum { margin:0 0 12px; color:var(--muted); font-size:13px; }
.gallery {
  display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
  gap:12px;
}
.shot { margin:0; background:#10130e; border-radius:6px; overflow:hidden; }
.shot img { width:100%; display:block; background:#10130e; }
.shot figcaption {
  font-size:11px; color:var(--muted); padding:6px 8px;
  border-top:1px solid var(--line);
}
.shot.rise figcaption { border-left:3px solid var(--rise); }
.shot.fall figcaption { border-left:3px solid var(--fall); }
.filter {
  display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin:8px 0 0;
  font-size:13px; color:var(--muted);
}
.filter button, .filter input {
  background:var(--panel); color:var(--text); border:1px solid var(--line);
  border-radius:4px; padding:4px 10px;
}
.filter button { cursor:pointer; }
.filter button.on { background:var(--accent); color:#111; border-color:var(--accent); }
.filter input { min-width:140px; }
.empty { color:var(--muted); padding:40px 0; text-align:center; }
</style>
</head>
<body>
<header class="top">
  <h1 id="title">涨跌阶段 · MA 综合分析大屏</h1>
  <div class="meta" id="meta">正在加载目录…</div>
  <div class="filter">
    <span>筛选：</span>
    <button type="button" class="on" data-f="all">全部</button>
    <button type="button" data-f="rise">仅上升</button>
    <button type="button" data-f="fall">仅下降</button>
    <input id="q" type="search" placeholder="代码/名称过滤" />
    <button type="button" id="reload">立即刷新</button>
    <label style="display:inline-flex;align-items:center;gap:4px">
      <input type="checkbox" id="auto" checked /> 自动刷新
    </label>
  </div>
  <div class="nav" id="nav"></div>
</header>
<main>
  <div class="insight">
    <h3>纵向综合（跨股同阶段）</h3>
    <ul id="narrative"><li>加载中…</li></ul>
  </div>
  <div id="cards" class="empty">等待扫描 stocks/ 目录…</div>
</main>
<script>
(() => {
  let filter = "all";
  let catalog = null;
  let timer = null;

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));

  async function loadCatalog() {
    // 优先实时 API（viewer 服务），否则读 catalog.json
    const urls = ["/api/catalog", "./catalog.json"];
    let data = null;
    let src = "";
    for (const u of urls) {
      try {
        const r = await fetch(u + (u.includes("?") ? "&" : "?") + "t=" + Date.now(), { cache: "no-store" });
        if (!r.ok) continue;
        data = await r.json();
        src = u;
        break;
      } catch (e) {}
    }
    if (!data) {
      $("meta").textContent = "无法读取目录。请用 python -m phase_ma_study.viewer 打开，或等待 catalog.json 生成。";
      return;
    }
    catalog = data;
    $("title").textContent = data.title || "涨跌阶段大屏";
    $("meta").textContent = `股票 ${data.n_stocks || 0} · 图片 ${data.n_images || 0} · 来源 ${src} · ${new Date().toLocaleTimeString()}`;
    const narr = (data.narrative || []);
    $("narrative").innerHTML = narr.length
      ? narr.map((x) => `<li>${esc(x)}</li>`).join("")
      : "<li>纵向报告尚未生成（任务跑完后写入 reports/vertical.json）</li>";
    render();
  }

  function render() {
    if (!catalog) return;
    const q = ($("q").value || "").trim().toLowerCase();
    const stocks = (catalog.stocks || []).filter((c) => {
      if (!q) return true;
      return (c.symbol || "").toLowerCase().includes(q) || (c.name || "").toLowerCase().includes(q);
    });
    $("nav").innerHTML = stocks.map((c) =>
      `<a href="#s-${esc(c.symbol)}">${esc(c.symbol)}</a>`
    ).join("");

    if (!stocks.length) {
      $("cards").innerHTML = '<p class="empty">暂无匹配结果</p>';
      $("cards").className = "";
      return;
    }

    $("cards").className = "";
    $("cards").innerHTML = stocks.map((c) => {
      const imgs = (c.images || []).filter((im) => filter === "all" || im.kind === filter);
      const gallery = imgs.map((im) =>
        `<figure class="shot ${esc(im.kind)}">` +
        `<a href="${esc(im.path)}" target="_blank">` +
        `<img src="${esc(im.path)}?t=${Date.now()}" loading="lazy" alt="${esc(im.caption)}"/>` +
        `</a><figcaption>${esc(im.caption)}</figcaption></figure>`
      ).join("");
      return `<section class="card" id="s-${esc(c.symbol)}">` +
        `<header><h2>${esc(c.symbol)} ${esc(c.name || "")}</h2>` +
        `<p class="sum">${esc(c.summary || `共 ${c.n_images || imgs.length} 张阶段图`)}</p></header>` +
        `<div class="gallery">${gallery || '<p class="empty">该筛选下无图</p>'}</div></section>`;
    }).join("");
  }

  document.querySelectorAll(".filter button[data-f]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter button[data-f]").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      filter = btn.dataset.f;
      render();
    });
  });
  $("q").addEventListener("input", render);
  $("reload").addEventListener("click", loadCatalog);
  $("auto").addEventListener("change", () => {
    if ($("auto").checked) startAuto();
    else stopAuto();
  });

  function startAuto() {
    stopAuto();
    timer = setInterval(loadCatalog, 8000);
  }
  function stopAuto() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  loadCatalog();
  startAuto();
})();
</script>
</body>
</html>
"""


def write_live_dashboard(output_dir: Path, refresh_catalog: bool = True) -> Path:
    """写入动态 dashboard.html，并刷新 catalog.json。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if refresh_catalog:
        write_catalog(output_dir)
    out = output_dir / "dashboard.html"
    out.write_text(DASHBOARD_HTML, encoding="utf-8")
    return out


# 兼容旧调用签名
def build_dashboard(
    output_dir: Path,
    stock_cards: list | None = None,
    vertical: dict | None = None,
    title: str = "涨跌阶段 · MA 综合分析大屏",
) -> Path:
    """忽略静态 cards，改为扫描目录生成动态大屏。"""
    return write_live_dashboard(Path(output_dir), refresh_catalog=True)
