# -*- coding: utf-8 -*-
"""NovelKit 入口：不带参数进图形界面，带参数走命令行。

    NovelKit.exe                        # 图形界面
    NovelKit.exe chai <输入> [选项]      # 一键拆书（probe→encode→analyze→split→stats→任务书）
    NovelKit.exe stats <目录> [...]      # 只重算统计
    NovelKit.exe verify <目录>           # 对账
    NovelKit.exe terms <目录> [...]      # 词表
    NovelKit.exe probe <路径>            # 探测编码
    NovelKit.exe split|analyze|encode|all <...>   # 透传底层 novel_split
    NovelKit.exe where                   # 打印工作区与自身位置

打包：见 tools/novelkit/build.ps1（PyInstaller --onefile）。
"""
from __future__ import annotations

import argparse
import os
import sys

import nv_core as core


# ------------------------------------------------------------------ Windows 细节


def _hide_console() -> None:
    """GUI 模式下把随 EXE 一起拉起的控制台窗口藏掉（CLI 模式不调用）。"""
    if os.name != "nt":
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:  # noqa: BLE001
        pass


def _force_utf8_io() -> None:
    """把控制台与 stdout/stderr 钉死到 UTF-8。

    Windows 默认 cp936：中文会乱码，`✓` 这类字符还会直接抛
    UnicodeEncodeError（实测打包后的 EXE 就崩在这一步）。
    """
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:  # noqa: BLE001
            pass
    for name in ("stdout", "stderr", "stdin"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def _dpi_aware() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


def _launch_gui() -> int:
    _dpi_aware()
    _hide_console()
    try:
        import nv_gui
    except Exception as exc:  # noqa: BLE001
        print(f"图形界面启动失败：{exc}\n（可改用命令行：NovelKit.exe chai <文件>）")
        return 1
    return nv_gui.run()


# ------------------------------------------------------------------ 命令行


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="NovelKit",
        description="网文拆书工具箱：拆书 + 机读统计 + 对账 + 词表 + 精读任务书。不带参数运行时打开图形界面。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  NovelKit.exe                                   打开图形界面\n"
            "  NovelKit.exe chai novels\\某本书.txt             一键拆书\n"
            "  NovelKit.exe chai output\\某本书                 已拆好，只补统计\n"
            "  NovelKit.exe stats output\\某本书                只重算统计\n"
            "  NovelKit.exe verify output\\某本书               对账\n"
            "  NovelKit.exe terms output\\某本书 --top-n 200    看词表\n"
            "  NovelKit.exe probe novels                       看编码\n"
        ),
    )
    ap.add_argument("--version", action="version", version=f"{core.APP_NAME} {core.VERSION}")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("chai", help="一键拆书（等价于 chai.ps1）")
    p.add_argument("input", help="原始 TXT / TXT 目录 / 已拆好的 output\\<书名> 目录")
    p.add_argument("--out", help="产物根目录（默认 <工作区>\\output）")
    p.add_argument("--book", help="书名（默认从文件名推导）")
    p.add_argument("--parts", type=int, default=0, help="切几份；0 = 自动")
    p.add_argument("--max-chars", type=int, default=0, help="每份净字数上限；0 = 不限")
    p.add_argument("--terms", help="人工确认的专名，逗号分隔")
    p.add_argument("--min-count", type=int, default=15, help="术语最低总频次（默认 15）")
    p.add_argument("--skip-encode", action="store_true", help="跳过编码统一")
    p.add_argument("--dry-run", action="store_true", help="只预演，不写盘")
    p.add_argument("--tasks-only", action="store_true", help="只重新生成精读任务书")

    sub.add_parser("gui", help="打开图形界面")
    sub.add_parser("where", help="打印工作区与程序位置")
    return ap


def main(argv: list[str] | None = None) -> int:
    _force_utf8_io()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _launch_gui()

    cmd = argv[0]

    # 透传底层工具：args 原样交给它们的 argparse，保证参数完全兼容
    if cmd in ("probe", "encode", "analyze", "split", "all"):
        import novel_split

        return int(novel_split.main(argv) or 0)
    if cmd in ("stats", "verify", "terms"):
        import chai_stats

        return int(chai_stats.main(argv) or 0)

    if cmd == "gui":
        return _launch_gui()

    ap = _build_parser()
    args = ap.parse_args(argv)

    if args.cmd == "where":
        ws = core.find_workspace()
        print(f"程序目录：{core.app_dir()}")
        print(f"工作区  ：{ws if ws else '（未找到）'}")
        print(f"默认输出：{core.default_output_root()}")
        return 0

    if args.cmd == "chai":
        try:
            core.run_chai(
                args.input, args.out, args.book, args.parts, args.max_chars,
                args.terms, args.min_count, args.skip_encode, args.dry_run,
                args.tasks_only, log=print,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            print(f"\n错误：{exc}", file=sys.stderr)
            return 2
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
