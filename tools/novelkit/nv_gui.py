# -*- coding: utf-8 -*-
"""NovelKit 图形界面（tkinter，无第三方依赖）。

界面分四块：输入输出 / 参数 / 操作按钮 / 日志。
所有耗时操作都丢到后台线程，主线程只负责把队列里的日志贴到文本框。
"""
from __future__ import annotations

import os
import queue
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import nv_core as core

FONT = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 9, "bold")
MONO = ("Consolas", 9)
MAX_LOG_LINES = 6000


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{core.APP_NAME} {core.VERSION} —— 网文拆书工具箱")
        self.geometry("1020x720")
        self.minsize(860, 600)

        self._q: queue.Queue = queue.Queue()
        self._busy = False
        self._buttons: list[ttk.Button] = []
        self._result_status = ""

        self._init_style()
        self._init_vars()
        self._build()
        self._menu()
        self.after(80, self._drain)
        self._log(f"{core.APP_NAME} {core.VERSION}  已就绪")
        ws = core.find_workspace()
        if ws:
            self._log(f"工作区：{ws}")
        self._log("用法：选输入 → 确认参数 → 点「一键拆书」。输入可以是原始 TXT、TXT 目录，或已拆好的 output\\<书名> 目录。")

    # ------------------------------------------------------------ 初始化
    def _init_style(self) -> None:
        style = ttk.Style(self)
        for theme in ("vista", "winnative", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure(".", font=FONT)
        style.configure("TButton", padding=(10, 4))
        style.configure("Run.TButton", font=FONT_BOLD, padding=(14, 6))
        style.configure("TLabelframe.Label", font=FONT_BOLD)
        style.configure("Status.TLabel", foreground="#555555")

    def _init_vars(self) -> None:
        self.var_in = tk.StringVar()
        self.var_out = tk.StringVar(value=str(core.default_output_root()))
        self.var_book = tk.StringVar()
        self.var_parts = tk.StringVar(value="0")
        self.var_maxchars = tk.StringVar(value="0")
        self.var_terms = tk.StringVar()
        self.var_mincount = tk.StringVar(value="15")
        self.var_topn = tk.StringVar(value="100")
        self.var_skip_encode = tk.BooleanVar(value=False)
        self.var_dry = tk.BooleanVar(value=False)
        self.var_status = tk.StringVar(value="就绪")

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        pad = {"padx": 8, "pady": 4}

        # ---------------- 输入输出
        io = ttk.LabelFrame(self, text="输入 / 输出")
        io.grid(row=0, column=0, sticky="ew", **pad)
        io.columnconfigure(1, weight=1)

        ttk.Label(io, text="输入：").grid(row=0, column=0, sticky="w", padx=(8, 2), pady=4)
        ttk.Entry(io, textvariable=self.var_in).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(io, text="选 TXT", command=self._pick_file).grid(row=0, column=2, padx=4)
        ttk.Button(io, text="选目录", command=self._pick_dir).grid(row=0, column=3, padx=(0, 8))

        ttk.Label(io, text="输出根：").grid(row=1, column=0, sticky="w", padx=(8, 2), pady=4)
        ttk.Entry(io, textvariable=self.var_out).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(io, text="更改", command=self._pick_out).grid(row=1, column=2, padx=4)
        ttk.Button(io, text="打开", command=self._open_output).grid(row=1, column=3, padx=(0, 8))

        # ---------------- 参数
        opt = ttk.LabelFrame(self, text="参数（0 = 自动）")
        opt.grid(row=1, column=0, sticky="ew", **pad)
        for c in (1, 3, 5, 7):
            opt.columnconfigure(c, weight=0, minsize=72)

        def field(row: int, col: int, label: str, var: tk.StringVar, width: int,
                  tip: str = "", pad_left: int = 12) -> ttk.Entry:
            ttk.Label(opt, text=label).grid(row=row, column=col, sticky="e",
                                            padx=(pad_left, 4), pady=6)
            e = ttk.Entry(opt, textvariable=var, width=width)
            e.grid(row=row, column=col + 1, sticky="w", pady=6)
            if tip:
                _Tip(e, tip)
            return e

        field(0, 0, "份数", self.var_parts, 8, "切几份；0 = 每份约 10 万字自动决定")
        field(0, 2, "每份字数", self.var_maxchars, 10,
              "每份净字数上限；与「份数」二选一，0 = 不限", pad_left=20)
        field(0, 4, "最小频次", self.var_mincount, 8,
              "术语候选的最低总频次，默认 15；噪音大就调高", pad_left=20)
        field(0, 6, "词表条数", self.var_topn, 8, "「词表」按钮输出的候选专名条数", pad_left=20)

        field(1, 0, "书名", self.var_book, 30, "留空则从文件名自动推导")
        ttk.Label(opt, text="专名").grid(row=1, column=2, sticky="e", padx=(20, 4), pady=(0, 8))
        terms = ttk.Entry(opt, textvariable=self.var_terms, width=46)
        terms.grid(row=1, column=3, columnspan=5, sticky="w", pady=(0, 8))
        _Tip(terms, "人工确认的专名，逗号分隔，强制进词表，如：亚伦,苏伦,莎尔")

        ttk.Checkbutton(opt, text="跳过编码统一", variable=self.var_skip_encode).grid(
            row=0, column=8, padx=(24, 12), sticky="w")
        ttk.Checkbutton(opt, text="预演（不写盘）", variable=self.var_dry).grid(
            row=1, column=8, padx=(24, 12), sticky="w")

        # ---------------- 按钮
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 4))
        specs = [
            ("一键拆书", self._on_chai, "Run.TButton"),
            ("只重算统计", self._on_stats, "TButton"),
            ("对账 verify", self._on_verify, "TButton"),
            ("词表 terms", self._on_terms, "TButton"),
            ("探测 probe", self._on_probe, "TButton"),
            ("重生成任务书", self._on_tasks, "TButton"),
            ("清空日志", self._clear_log, "TButton"),
        ]
        for text, cmd, style in specs:
            b = ttk.Button(bar, text=text, command=cmd, style=style)
            b.pack(side="left", padx=(0, 6))
            if text not in ("清空日志",):
                self._buttons.append(b)

        # ---------------- 日志
        logf = ttk.LabelFrame(self, text="运行日志")
        logf.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.txt = tk.Text(logf, wrap="none", font=MONO, bg="#1e1e1e", fg="#d4d4d4",
                           insertbackground="#d4d4d4", undo=False)
        self.txt.grid(row=0, column=0, sticky="nsew")
        ys = ttk.Scrollbar(logf, orient="vertical", command=self.txt.yview)
        ys.grid(row=0, column=1, sticky="ns")
        xs = ttk.Scrollbar(logf, orient="horizontal", command=self.txt.xview)
        xs.grid(row=1, column=0, sticky="ew")
        self.txt.configure(yscrollcommand=ys.set, xscrollcommand=xs.set, state="disabled")

        # ---------------- 状态栏
        bottom = ttk.Frame(self)
        bottom.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 6))
        bottom.columnconfigure(1, weight=1)
        self.bar = ttk.Progressbar(bottom, mode="indeterminate", length=180)
        self.bar.grid(row=0, column=0, sticky="w")
        ttk.Label(bottom, textvariable=self.var_status, style="Status.TLabel").grid(
            row=0, column=1, sticky="w", padx=10)

    def _menu(self) -> None:
        m = tk.Menu(self)
        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label="打开工作区…", command=self._open_workspace)
        fm.add_command(label="打开输出目录…", command=self._open_output)
        fm.add_separator()
        fm.add_command(label="退出", command=self.destroy)
        m.add_cascade(label="文件", menu=fm)
        hm = tk.Menu(m, tearoff=0)
        hm.add_command(label="关于 NovelKit", command=self._about)
        m.add_cascade(label="帮助", menu=hm)
        self.config(menu=m)

    # ------------------------------------------------------------ 交互
    def _pick_file(self) -> None:
        p = filedialog.askopenfilename(
            title="选择小说 TXT",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialdir=str(core.find_workspace() or Path.home()),
        )
        if p:
            self.var_in.set(p)

    def _pick_dir(self) -> None:
        p = filedialog.askdirectory(title="选择目录（TXT 所在目录，或 output\\<书名>）")
        if p:
            self.var_in.set(p)

    def _pick_out(self) -> None:
        p = filedialog.askdirectory(title="选择输出根目录")
        if p:
            self.var_out.set(p)

    def _open_output(self) -> None:
        out = Path(self.var_out.get().strip() or core.default_output_root())
        if not out.exists():
            messagebox.showinfo("还没有产物", f"输出目录还不存在：\n{out}")
            return
        os.startfile(str(out))  # noqa: S606

    def _open_workspace(self) -> None:
        ws = core.find_workspace()
        if not ws:
            messagebox.showinfo("未找到工作区", "没有找到包含 tools/novel_split 或 novels 的目录。")
            return
        os.startfile(str(ws))  # noqa: S606

    def _about(self) -> None:
        messagebox.showinfo(
            "关于",
            f"{core.APP_NAME} {core.VERSION}\n\n"
            "网文拆书工具箱：拆书（probe→encode→analyze→split）\n"
            "＋ 机读统计、对账、词表、精读任务书。\n\n"
            "内核：tools/novel_split + tools/chai/chai_stats\n"
            "命令行：NovelKit.exe --help",
        )

    # ------------------------------------------------------------ 日志
    def _log(self, msg: str) -> None:
        self.txt.configure(state="normal")
        self.txt.insert("end", str(msg) + "\n")
        # 控制行数，防止长任务把内存吃满
        if int(self.txt.index("end-1c").split(".")[0]) > MAX_LOG_LINES:
            self.txt.delete("1.0", f"{MAX_LOG_LINES // 3}.0")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _clear_log(self) -> None:
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")

    def _log_cb(self, msg: str) -> None:
        """后台线程用的回调：只往队列里放，不碰 UI。"""
        self._q.put(("log", msg))

    # ------------------------------------------------------------ 异步执行
    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for b in self._buttons:
            b.configure(state=state)
        self.configure(cursor="watch" if busy else "")
        if busy:
            self.bar.start(12)
            self.var_status.set("运行中…")
        else:
            self.bar.stop()
            self.var_status.set("就绪")

    def _run_async(self, label: str, fn) -> None:
        if self._busy:
            return
        self._busy = True
        self._set_busy(True)
        self._log("")
        self._log(f"▶ {label}")

        def worker() -> None:
            try:
                result = fn()
                self._q.put(("log", "✔ 完成"))
                self._q.put(("result", result))
            except Exception as exc:  # noqa: BLE001
                self._q.put(("log", f"✘ 出错：{exc}"))
                self._q.put(("log", traceback.format_exc().rstrip()))
                self._q.put(("error", str(exc)))
            finally:
                self._q.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

    def _drain(self) -> None:
        try:
            while True:
                kind, val = self._q.get_nowait()
                if kind == "log":
                    self._log(val)
                elif kind == "result":
                    if isinstance(val, list) and val:
                        ok = sum(1 for s in val if getattr(s, "ok", False))
                        self._result_status = f"完成：{ok}/{len(val)} 本" if ok else "完成（有失败）"
                elif kind == "error":
                    self._result_status = "失败，看日志"
                elif kind == "done":
                    self._busy = False
                    self._set_busy(False)
                    if self._result_status:
                        self.var_status.set(self._result_status)
                        self._result_status = ""
        except queue.Empty:
            pass
        self.after(80, self._drain)

    # ------------------------------------------------------------ 动作
    def _input(self) -> str:
        p = self.var_in.get().strip().strip('"')
        if not p:
            messagebox.showwarning("缺少输入", "请先选择要处理的 TXT 或目录。")
        return p

    def _ints(self) -> tuple[int, int, int, int] | None:
        try:
            return (int(self.var_parts.get() or 0), int(self.var_maxchars.get() or 0),
                    int(self.var_mincount.get() or 15), int(self.var_topn.get() or 100))
        except ValueError:
            messagebox.showerror("参数错误", "份数 / 每份字数 / 最小频次 / 词表条数 必须是整数。")
            return None

    def _on_chai(self) -> None:
        inp = self._input()
        if not inp:
            return
        iv = self._ints()
        if iv is None:
            return
        parts, maxc, minc, _topn = iv
        out = self.var_out.get().strip().strip('"') or None
        book = self.var_book.get().strip() or None
        terms = self.var_terms.get().strip() or None
        skip = self.var_skip_encode.get()
        dry = self.var_dry.get()
        self._run_async("一键拆书", lambda: core.run_chai(
            inp, out, book, parts, maxc, terms, minc, skip, dry, False, self._log_cb))

    def _on_stats(self) -> None:
        inp = self._input()
        if not inp:
            return
        iv = self._ints()
        if iv is None:
            return
        _p, _m, minc, _t = iv
        terms = self.var_terms.get().strip() or None
        self._run_async("只重算统计", lambda: core.run_stats(inp, terms=terms, min_count=minc,
                                                        log=self._log_cb))

    def _on_verify(self) -> None:
        inp = self._input()
        if not inp:
            return
        book = self.var_book.get().strip() or None
        self._run_async("对账 verify", lambda: core.run_verify(inp, book, log=self._log_cb))

    def _on_terms(self) -> None:
        inp = self._input()
        if not inp:
            return
        iv = self._ints()
        if iv is None:
            return
        _p, _m, minc, topn = iv
        terms = self.var_terms.get().strip() or None
        self._run_async("词表 terms", lambda: core.run_terms(inp, topn, minc, terms, log=self._log_cb))

    def _on_probe(self) -> None:
        inp = self._input()
        if not inp:
            return
        self._run_async("探测 probe", lambda: core.run_probe(inp, log=self._log_cb))

    def _on_tasks(self) -> None:
        inp = self._input()
        if not inp:
            return
        self._run_async("重生成任务书", lambda: core.run_tasks_only(inp, log=self._log_cb))


class _Tip:
    """极简 tooltip（tkinter 不自带）。"""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _e=None) -> None:
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", background="#ffffe0",
                 relief="solid", borderwidth=1, font=FONT).pack()

    def _hide(self, _e=None) -> None:
        if self.tip:
            self.tip.destroy()
            self.tip = None


def run() -> int:
    app = App()
    app.mainloop()
    return 0
