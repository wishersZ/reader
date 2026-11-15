# -*- coding: utf-8 -*-
"""把 PyInstaller 及其依赖取到 tools/novelkit/_pylib（仅供打包使用）。

为什么不直接 `pip install --target`：
    受限环境（文件沙箱 / 只读系统盘）下，pip 下载阶段要往临时目录写
    `*.whl.metadata`，会被拒绝并报 PermissionError。这里改为自己从 PyPI
    取 wheel（纯 HTTP）再解包，只写目标目录，成功率高得多。

用法：
    py -3 tools/novelkit/bootstrap_pyinstaller.py
    py -3 tools/novelkit/bootstrap_pyinstaller.py --target D:\\some\\dir
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

#: PyInstaller 的运行期依赖（Windows）
PKGS = [
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "altgraph",
    "packaging",
    "pefile",
    "pywin32-ctypes",
]

DEFAULT_TARGET = Path(__file__).resolve().parent / "_pylib"


def pick_wheel(urls: list[dict]) -> dict | None:
    """挑一个适合本机的 wheel：优先 cp3xx-win_amd64，其次 py3-none-any。"""

    def score(u: dict) -> int:
        f = u["filename"]
        if not f.endswith(".whl"):
            return -1
        s = 0
        if "win_amd64" in f:
            s += 5
        if "cp3" in f and "win_amd64" in f:
            s += 3
        if "py3-none-any" in f or "py2.py3-none-any" in f:
            s += 4
        if any(bad in f for bad in ("musllinux", "manylinux", "macosx", "aarch64")):
            s -= 10
        return s

    cands = [u for u in urls if score(u) >= 0]
    cands.sort(key=score, reverse=True)
    return cands[0] if cands else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="取 PyInstaller wheel 到 _pylib（打包专用）")
    ap.add_argument("--target", default=str(DEFAULT_TARGET), help="解包目标目录")
    ap.add_argument("--timeout", type=int, default=120, help="单个请求超时（秒）")
    args = ap.parse_args(argv)

    target = Path(args.target).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    failed = 0

    for name in PKGS:
        print(f"取 {name} ...", end="", flush=True)
        try:
            meta = json.load(urllib.request.urlopen(
                f"https://pypi.org/pypi/{name}/json", timeout=args.timeout))
            wheel = pick_wheel(meta.get("urls") or [])
            if not wheel:
                print(f"\r跳过 {name}：没有可用 wheel")
                failed += 1
                continue
            data = urllib.request.urlopen(wheel["url"], timeout=args.timeout).read()
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                z.extractall(target)
            print(f"\r{name:26s} {wheel['filename']}  {len(data) / 1e6:.1f} MB")
        except Exception as exc:  # noqa: BLE001
            print(f"\r失败 {name}：{exc}")
            failed += 1

    print(f"\n解包目标：{target}")
    if failed:
        print(f"{failed} 个包没装好；若网络受限，可手动把 wheel 解压到该目录。")
        return 1
    print("完成。接下来运行 build.ps1 打包。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
