"""扫描 output/stocks 目录，生成实时图库目录数据。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PNG_RE = re.compile(r"^(rise|fall)_(\d+)_(.+)\.png$", re.I)


def scan_catalog(output_dir: Path) -> dict[str, Any]:
    """遍历 stocks/*/ 下的 png 与 json，组装大屏数据。"""
    output_dir = Path(output_dir)
    stocks_dir = output_dir / "stocks"
    cards: list[dict[str, Any]] = []
    n_images = 0

    if stocks_dir.is_dir():
        for stock_dir in sorted(stocks_dir.iterdir()):
            if not stock_dir.is_dir():
                continue
            symbol = stock_dir.name
            name = ""
            summary = ""
            horiz_path = stock_dir / "horizontal.json"
            if horiz_path.exists():
                try:
                    horiz = json.loads(horiz_path.read_text(encoding="utf-8"))
                    summary = horiz.get("summary") or ""
                    name = horiz.get("name") or ""
                except Exception:
                    pass

            images: list[dict[str, str]] = []
            for png in sorted(stock_dir.glob("*.png")):
                m = PNG_RE.match(png.name)
                kind = (m.group(1).lower() if m else "other")
                # caption: rise_001_2018-01-01_2018-02-01.png → 升 2018-01-01~2018-02-01
                if m:
                    rng = m.group(3).replace("_", " ~ ")
                    label = "升" if kind == "rise" else "降"
                    caption = f"{label} {rng}"
                else:
                    caption = png.stem
                rel = str(png.relative_to(output_dir)).replace("\\", "/")
                images.append({"kind": kind, "path": rel, "caption": caption})
            n_images += len(images)
            if not images and not horiz_path.exists():
                continue
            cards.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "summary": summary,
                    "images": images,
                    "n_images": len(images),
                }
            )

    narrative: list[str] = []
    vert_path = output_dir / "reports" / "vertical.json"
    if vert_path.exists():
        try:
            vert = json.loads(vert_path.read_text(encoding="utf-8"))
            narrative = vert.get("narrative") or []
        except Exception:
            pass

    return {
        "title": "涨跌阶段 · MA 综合分析大屏（实时）",
        "generated": True,
        "n_stocks": len(cards),
        "n_images": n_images,
        "narrative": narrative,
        "stocks": cards,
    }


def write_catalog(output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cat = scan_catalog(output_dir)
    path = output_dir / "catalog.json"
    path.write_text(json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8")
    # 兼容旧索引
    (output_dir / "dashboard_index.json").write_text(
        json.dumps(
            {
                "title": cat["title"],
                "n_stocks": cat["n_stocks"],
                "n_images": cat["n_images"],
                "stocks": [
                    {"symbol": c["symbol"], "name": c.get("name"), "n_images": c.get("n_images", 0)}
                    for c in cat["stocks"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
