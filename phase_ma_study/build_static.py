"""
生成可双击打开的静态大屏（catalog 内嵌进 HTML，不依赖 localhost / fetch）。

  python -m phase_ma_study.build_static
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from phase_ma_study.catalog import scan_catalog, write_catalog  # noqa: E402
from phase_ma_study.config import DEFAULT_OUTPUT  # noqa: E402

STATIC_HTML_TMPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__TITLE__</title>
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
.filter {
  display:flex; flex-wrap:wrap; gap:10px; align-items:center;
  font-size:13px; color:var(--muted);
}
.filter button, .filter input {
  background:var(--panel); color:var(--text); border:1px solid var(--line);
  border-radius:4px; padding:4px 10px;
}
.filter button { cursor:pointer; }
.filter button.on { background:var(--accent); color:#111; border-color:var(--accent); }
.filter input { min-width:160px; }
main { padding:16px 20px 40px; }
.insight {
  background:var(--panel); border:1px dashed var(--line);
  padding:12px 16px; margin-bottom:18px; border-radius:8px;
}
.insight h3 { margin:0 0 8px; font-size:14px; color:var(--accent); }
.insight ul { margin:0; padding-left:18px; color:var(--muted); font-size:13px; }
.card {
  background:var(--panel); border:1px solid var(--line);
  border-radius:10px; margin-bottom:12px; overflow:hidden;
}
.card > header {
  display:flex; justify-content:space-between; gap:12px; align-items:center;
  padding:12px 14px; cursor:pointer; user-select:none;
}
.card > header:hover { background:#1c2016; }
.card h2 { margin:0; font-size:15px; }
.card .sum { margin:4px 0 0; color:var(--muted); font-size:12px; }
.badge {
  flex-shrink:0; font-size:12px; color:#111; background:var(--accent);
  border-radius:999px; padding:2px 10px;
}
.gallery {
  display:none; grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
  gap:10px; padding:0 14px 14px;
}
.card.open .gallery { display:grid; }
.shot { margin:0; background:#10130e; border-radius:6px; overflow:hidden; }
.shot img { width:100%; display:block; background:#10130e; }
.shot figcaption {
  font-size:11px; color:var(--muted); padding:6px 8px;
  border-top:1px solid var(--line);
}
.shot.rise figcaption { border-left:3px solid var(--rise); }
.shot.fall figcaption { border-left:3px solid var(--fall); }
.empty { color:var(--muted); padding:40px 0; text-align:center; }
.pager { display:flex; gap:8px; align-items:center; margin-top:10px; flex-wrap:wrap; }
</style>
</head>
<body>
<header class="top">
  <h1 id="title">涨跌阶段 · MA 综合分析大屏</h1>
  <div class="meta" id="meta"></div>
  <div class="filter">
    <span>阶段：</span>
    <button type="button" class="on" data-f="all">全部</button>
    <button type="button" data-f="rise">仅上升</button>
    <button type="button" data-f="fall">仅下降</button>
    <input id="q" type="search" placeholder="代码/名称过滤" />
    <span class="pager">
      <button type="button" id="prev">上一页</button>
      <span id="pageinfo">1/1</span>
      <button type="button" id="next">下一页</button>
    </span>
  </div>
</header>
<main>
  <div class="insight">
    <h3>纵向综合（跨股同阶段）</h3>
    <ul id="narrative"></ul>
  </div>
  <div id="cards" class="empty">加载中…</div>
</main>
<script id="catalog-data" type="application/json">
__CATALOG_JSON__
</script>
<script>
(() => {
  const raw = document.getElementById("catalog-data").textContent;
  const catalog = JSON.parse(raw);
  let filter = "all";
  let page = 1;
  const PAGE_SIZE = 40;

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));

  $("title").textContent = catalog.title || "涨跌阶段大屏";
  $("meta").textContent = `股票 ${catalog.n_stocks || 0} · 图片 ${catalog.n_images || 0} · 静态内嵌目录（可直接双击打开）`;
  const narr = catalog.narrative || [];
  $("narrative").innerHTML = narr.length
    ? narr.map((x) => `<li>${esc(x)}</li>`).join("")
    : "<li>无纵向摘要</li>";

  function filteredStocks() {
    const q = ($("q").value || "").trim().toLowerCase();
    return (catalog.stocks || []).filter((c) => {
      if (!q) return true;
      return (c.symbol || "").toLowerCase().includes(q) || (c.name || "").toLowerCase().includes(q);
    });
  }

  function render() {
    const all = filteredStocks();
    const pages = Math.max(1, Math.ceil(all.length / PAGE_SIZE));
    if (page > pages) page = pages;
    if (page < 1) page = 1;
    $("pageinfo").textContent = `${page}/${pages}（本页 ${Math.min(PAGE_SIZE, all.length - (page-1)*PAGE_SIZE)} / 共 ${all.length} 只）`;
    const slice = all.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
    if (!slice.length) {
      $("cards").innerHTML = '<p class="empty">无匹配股票</p>';
      return;
    }
    $("cards").className = "";
    $("cards").innerHTML = slice.map((c) => {
      const imgs = (c.images || []).filter((im) => filter === "all" || im.kind === filter);
      const gallery = imgs.map((im) =>
        `<figure class="shot ${esc(im.kind)}">` +
        `<a href="${esc(im.path)}" target="_blank">` +
        `<img data-src="${esc(im.path)}" alt="${esc(im.caption)}"/>` +
        `</a><figcaption>${esc(im.caption)}</figcaption></figure>`
      ).join("");
      return `<section class="card" data-sym="${esc(c.symbol)}">` +
        `<header>` +
        `<div><h2>${esc(c.symbol)} ${esc(c.name || "")}</h2>` +
        `<p class="sum">${esc(c.summary || "")}</p></div>` +
        `<span class="badge">${imgs.length} 图 ▾</span>` +
        `</header>` +
        `<div class="gallery">${gallery || '<p class="empty">该筛选下无图</p>'}</div>` +
        `</section>`;
    }).join("");

    document.querySelectorAll(".card > header").forEach((hdr) => {
      hdr.addEventListener("click", () => {
        const card = hdr.parentElement;
        const open = card.classList.toggle("open");
        if (open) {
          card.querySelectorAll("img[data-src]").forEach((img) => {
            if (!img.src) img.src = img.getAttribute("data-src");
          });
        }
      });
    });
  }

  document.querySelectorAll(".filter button[data-f]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter button[data-f]").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      filter = btn.dataset.f;
      render();
    });
  });
  $("q").addEventListener("input", () => { page = 1; render(); });
  $("prev").addEventListener("click", () => { page -= 1; render(); window.scrollTo(0,0); });
  $("next").addEventListener("click", () => { page += 1; render(); window.scrollTo(0,0); });

  render();
})();
</script>
</body>
</html>
"""


def build_static_dashboard(output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    write_catalog(output_dir)
    cat = scan_catalog(output_dir)
    # 精简：去掉无用字段，减小体积
    slim = {
        "title": "涨跌阶段 · MA 综合分析大屏",
        "n_stocks": cat["n_stocks"],
        "n_images": cat["n_images"],
        "narrative": cat.get("narrative") or [],
        "stocks": [
            {
                "symbol": s["symbol"],
                "name": s.get("name") or "",
                "summary": s.get("summary") or "",
                "images": s.get("images") or [],
            }
            for s in cat.get("stocks") or []
        ],
    }
    payload = json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
    # 防止 </script> 打断
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = STATIC_HTML_TMPL.replace("__TITLE__", "涨跌阶段 · MA 综合分析大屏").replace(
        "__CATALOG_JSON__", payload
    )
    out = output_dir / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    # 同时写一份启动说明
    (output_dir / "打开大屏.txt").write_text(
        "直接双击 dashboard.html 即可查看（已内嵌目录，无需服务器）。\n"
        "或运行同目录上级打包的 PhaseMAGallery.exe。\n",
        encoding="utf-8",
    )
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = ap.parse_args(argv)
    out = build_static_dashboard(Path(args.output))
    print(f"已生成可双击大屏: {out}")
    print(f"大小约 {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
