"""
打包便携启动器。

默认（推荐）：把 PhaseMAGallery.exe 直接打进已有 output 目录，
与 dashboard.html、stocks/ 同级 —— 不复制 9GB 图片。
整夹拷到别的电脑即可。

  python -m phase_ma_study.pack_portable

完整复制到新目录（占双倍磁盘）:
  python -m phase_ma_study.pack_portable --copy-to D:\\PhaseMAGallery
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from phase_ma_study.build_static import build_static_dashboard  # noqa: E402
from phase_ma_study.config import DEFAULT_OUTPUT, PACKAGE_DIR  # noqa: E402


def _ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("安装 pyinstaller …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_exe(distpath: Path, script: Path, name: str) -> Path:
    _ensure_pyinstaller()
    work = PACKAGE_DIR / "_pack_work"
    work.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        name,
        "--distpath",
        str(distpath),
        "--workpath",
        str(work / "build" / name),
        "--specpath",
        str(work),
        str(script),
    ]
    subprocess.check_call(cmd)
    exe = distpath / f"{name}.exe"
    if not exe.exists():
        raise RuntimeError(f"未生成 {exe}")
    return exe


def build_gallery_exe(distpath: Path) -> Path:
    return build_exe(distpath, PACKAGE_DIR / "launcher.py", "PhaseMAGallery")


def build_web_exe(distpath: Path) -> Path:
    return build_exe(distpath, PACKAGE_DIR / "web_launcher.py", "PhaseMAWeb")


def write_readme(folder: Path) -> None:
    (folder / "打开说明.txt").write_text(
        "PhaseMAGallery 便携包\n"
        "==================\n\n"
        "打开方式（任选其一）:\n"
        "  1. 双击 PhaseMAWeb.exe     （推荐：本地网页服务，浏览器打开）\n"
        "  2. 双击 PhaseMAGallery.exe （直接打开 dashboard.html）\n"
        "  3. 双击 dashboard.html / correlation.html\n\n"
        "换电脑: 复制整个文件夹（必须包含 exe、dashboard.html、correlation.html、stocks/）。\n"
        "图片约数 GB，请整夹拷贝。\n",
        encoding="utf-8",
    )


def pack_inplace(output_dir: Path, skip_static: bool = False) -> Path:
    output_dir = Path(output_dir)
    if not skip_static:
        print("生成静态 dashboard.html …")
        build_static_dashboard(output_dir)
    print("打包 PhaseMAGallery.exe …")
    gallery = build_gallery_exe(output_dir)
    print("打包 PhaseMAWeb.exe（Web 端）…")
    web = build_web_exe(output_dir)
    write_readme(output_dir)
    print(f"完成: {gallery}")
    print(f"完成: {web}")
    print("推荐双击 PhaseMAWeb.exe（浏览器打开本地网页）")
    return web


def pack_copy(output_src: Path, dest: Path) -> Path:
    output_src = Path(output_src)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    print("生成静态 dashboard.html …")
    build_static_dashboard(output_src)
    print(f"复制数据 → {dest} （约数 GB，较慢）…")
    for name in ("stocks", "reports", "dashboard.html", "catalog.json", "correlation.html"):
        src = output_src / name
        dst = dest / name
        if not src.exists():
            continue
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    print("打包 exe …")
    build_gallery_exe(dest)
    web = build_web_exe(dest)
    write_readme(dest)
    print(f"完成: {dest}")
    return web


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument(
        "--copy-to",
        default=None,
        help="复制整包到新目录（占双倍空间）；默认直接在 output 里生成 exe",
    )
    ap.add_argument(
        "--skip-static",
        action="store_true",
        help="不重建 dashboard.html，只打 exe",
    )
    args = ap.parse_args(argv)
    if args.copy_to:
        pack_copy(Path(args.output), Path(args.copy_to))
    else:
        pack_inplace(Path(args.output), skip_static=args.skip_static)


if __name__ == "__main__":
    main()
