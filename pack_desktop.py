"""
打包形迹 QuantTrade Web 桌面便携包（Windows / macOS）。

含：可执行文件 + Python 依赖（PyInstaller）+ web/ + data_cache/
不含：miniprogram（微信小程序）、phase_ma_study 大图库。

用法（在 quant_trade 目录）：

  # Windows（本机）
  .\\.venv\\Scripts\\python.exe -m pack_desktop
  .\\.venv\\Scripts\\python.exe -m pack_desktop --no-data          # 不含行情缓存（体积小）
  .\\.venv\\Scripts\\python.exe -m pack_desktop --zip

  # macOS（必须在 Mac 上执行同一脚本）
  python -m pack_desktop --zip

说明：PyInstaller 不能跨平台交叉编译。
在 Windows 上只能打出 Windows 包；Mac 包请在 macOS 上运行本脚本。
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE_NAME = "QuantTrade"


def _ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("安装 pyinstaller …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def platform_tag() -> str:
    sysname = platform.system().lower()
    if sysname == "darwin":
        return "mac"
    if sysname == "windows":
        return "win"
    return sysname or "unknown"


def dist_dir(tag: str | None = None) -> Path:
    return ROOT / "dist" / f"{PACKAGE_NAME}-{tag or platform_tag()}"


def build_exe(out_dir: Path) -> Path:
    _ensure_pyinstaller()
    work = ROOT / "_pack_desktop_work"
    work.mkdir(parents=True, exist_ok=True)
    name = PACKAGE_NAME
    # onedir：依赖与 exe 同夹，便于旁路放 web/data_cache
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed" if platform.system() == "Windows" else "--windowed",
        "--name",
        name,
        "--distpath",
        str(out_dir.parent / "_pyi_dist"),
        "--workpath",
        str(work / "build"),
        "--specpath",
        str(work),
        "--paths",
        str(ROOT),
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols",
        "--hidden-import",
        "uvicorn.protocols.http",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--hidden-import",
        "server",
        "--collect-submodules",
        "qt",
        "--collect-all",
        "uvicorn",
        "--collect-all",
        "fastapi",
        "--collect-all",
        "starlette",
        "--collect-all",
        "pydantic",
        "--collect-all",
        "akshare",
        str(ROOT / "desktop_launcher.py"),
    ]
    # macOS: 部分环境 --windowed 即 app 无控制台；保持一致
    print("PyInstaller 打包中（依赖较多，可能需数分钟）…")
    subprocess.check_call(cmd)

    built = out_dir.parent / "_pyi_dist" / name
    if platform.system() == "Darwin":
        # PyInstaller 可能生成 .app
        app = out_dir.parent / "_pyi_dist" / f"{name}.app"
        if app.exists() and not built.exists():
            built = app

    if not built.exists():
        raise RuntimeError(f"未找到 PyInstaller 输出: {built}")

    out_dir.mkdir(parents=True, exist_ok=True)
    # 清空目标后拷贝 onedir 内容到 QuantTrade-win/
    for child in list(out_dir.iterdir()):
        if child.name in ("web", "data_cache", "打开说明.txt", "README_PORTABLE.txt"):
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    if built.suffix == ".app" or built.name.endswith(".app"):
        dest_app = out_dir / built.name
        if dest_app.exists():
            shutil.rmtree(dest_app)
        shutil.copytree(built, dest_app)
        return dest_app

    # onedir 文件夹：把内部文件提升到 out_dir
    for item in built.iterdir():
        dest = out_dir / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    exe = out_dir / (f"{name}.exe" if platform.system() == "Windows" else name)
    if not exe.exists():
        # 有时在子目录
        candidates = list(out_dir.rglob(f"{name}.exe")) + list(out_dir.rglob(name))
        if candidates:
            return candidates[0]
        raise RuntimeError(f"未找到可执行文件于 {out_dir}")
    return exe


def copy_web(out_dir: Path) -> None:
    src = ROOT / "web"
    dst = out_dir / "web"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("*.map", ".DS_Store"),
    )
    print(f"已复制 web/ → {dst}")


def copy_data_cache(out_dir: Path) -> None:
    src = ROOT / "data_cache"
    dst = out_dir / "data_cache"
    if not src.exists():
        print("警告: 无 data_cache，将创建空目录")
        (dst / "bars").mkdir(parents=True, exist_ok=True)
        (dst / "auction").mkdir(parents=True, exist_ok=True)
        return
    if dst.exists():
        shutil.rmtree(dst)
    print(f"复制 data_cache/ → {dst} （可能较慢）…")
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("*.tmp", ".DS_Store", "__pycache__"),
    )


def write_readme(out_dir: Path, tag: str) -> None:
    exe_name = "QuantTrade.exe" if tag == "win" else "QuantTrade（或 QuantTrade.app）"
    text = f"""形迹 QuantTrade 便携包（{tag}）
==============================

本包为 Web 研究终端桌面版，已包含运行环境与本地行情缓存。
不含微信小程序（miniprogram）。

打开方式
--------
1. 双击 {exe_name}
2. 浏览器自动打开 http://127.0.0.1:8765/
3. 关闭启动窗口即停止服务

目录说明
--------
  {exe_name}     主程序（内置 Python 依赖）
  web/           前端页面
  data_cache/    日线/自选/提醒等本地数据（可随用随更新）

换电脑
------
复制整个「{PACKAGE_NAME}-{tag}」文件夹即可。
Windows 包不能在 Mac 上运行，反之亦然。

注意
----
- 首次盘中拉现价需联网
- 日线缓存可在软件内「立即更新缓存」刷新
- 杀毒软件若拦截，请添加信任
"""
    (out_dir / "打开说明.txt").write_text(text, encoding="utf-8")
    (out_dir / "README_PORTABLE.txt").write_text(text, encoding="utf-8")


def make_zip(out_dir: Path) -> Path:
    zpath = out_dir.with_suffix(".zip")
    if zpath.exists():
        zpath.unlink()
    print(f"压缩 → {zpath} …")
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as zf:
        for f in out_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out_dir.parent))
    print(f"完成 zip: {zpath} ({zpath.stat().st_size / 1e6:.1f} MB)")
    return zpath


def pack(include_data: bool = True, do_zip: bool = False) -> Path:
    tag = platform_tag()
    out = dist_dir(tag)
    out.mkdir(parents=True, exist_ok=True)
    print(f"目标平台: {tag} ({platform.platform()})")
    print(f"输出目录: {out}")

    build_exe(out)
    copy_web(out)
    if include_data:
        copy_data_cache(out)
    else:
        (out / "data_cache" / "bars").mkdir(parents=True, exist_ok=True)
        (out / "data_cache" / "auction").mkdir(parents=True, exist_ok=True)
        print("已跳过 data_cache 复制（--no-data）")

    # 明确不打包 miniprogram
    if (out / "miniprogram").exists():
        shutil.rmtree(out / "miniprogram")

    write_readme(out, tag)
    print(f"便携包已就绪: {out}")
    if do_zip:
        make_zip(out)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="打包 QuantTrade Web 桌面便携包")
    ap.add_argument("--no-data", action="store_true", help="不复制 data_cache（体积更小）")
    ap.add_argument("--zip", action="store_true", help="额外打 zip")
    ap.add_argument(
        "--print-mac-hint",
        action="store_true",
        help="仅打印在 Mac 上打包的命令后退出",
    )
    args = ap.parse_args(argv)

    if args.print_mac_hint:
        print(
            "在 macOS 上进入 quant_trade 目录后执行:\n"
            "  python3 -m venv .venv && source .venv/bin/activate\n"
            "  pip install -r requirements.txt pyinstaller\n"
            "  python -m pack_desktop --zip\n"
            "产物: dist/QuantTrade-mac/"
        )
        return

    pack(include_data=not args.no_data, do_zip=args.zip)


if __name__ == "__main__":
    main()
