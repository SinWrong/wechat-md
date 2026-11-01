#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wechat_md_gui.py —— 公众号排版编辑器（Tk 桌面版）

左边写文案，右边实时看排版，点按钮插组件，一键导出 Markdown / 可粘贴 HTML。

启动：
    python tools/wechat_md_gui.py
    python tools/wechat_md_gui.py examples/bear.md      # 直接打开某篇
    wechat_md_gui.bat

依赖：Python 3.8+ 自带 tkinter；Pillow 可选（用于预览里显示 JPG 图片，
      没装也不影响导出，预览会用占位块代替）。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import traceback
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gui_core as G          # noqa: E402
import wechat_md as W         # noqa: E402

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except Exception:             # pragma: no cover
    HAS_PIL = False

APP_TITLE = "公众号排版编辑器"
FONT = "Microsoft YaHei UI"
MONO = "Consolas"

C_BG = "#F5F6F8"
C_PANEL = "#FFFFFF"
C_LINE = "#E3E5E8"
C_TEXT = "#2B2F36"
C_MUTED = "#8A8F96"
C_ACCENT = "#2F6FD0"

WELCOME = """# 在这里写标题（≤30 字）

日期: {today}

导语：一到两句话说清这篇为什么值得看。空行分段。

## 01 第一个小节的标题

正文写在这里。单段控制在 3 行以内，超过就在分号处拆开。

[IMG:imgs/01-示例图.jpg|图片描述|图注：画面里发生了什么。图源：待补]

## 02 第二个小节的标题

- 列表会自动排成 ①②③
- 也可以直接写正文

## 写在最后

一句收束全文的话。

[CTA]
看完这篇，你最大的感受是什么？欢迎在评论区聊聊。

[END]
**关注「公众号名称」，每天一个新鲜事。**
""".format(today=__import__("datetime").date.today().isoformat())


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------

def ui_font(size: int, bold: bool = False) -> Tuple[str, int, str]:
    """界面字号（磅）。"""
    return (FONT, size, "bold" if bold else "normal")


def px_font(size: int, bold: bool = False) -> Tuple[str, int, str]:
    """正文字号（像素）。Tk 里负数字号表示像素，预览要和公众号的 px 对齐。"""
    return (FONT, -abs(int(size)), "bold" if bold else "normal")


def add_tooltip(widget: tk.Widget, text: str, delay: int = 450):
    tip: Dict[str, Optional[tk.Toplevel]] = {"win": None, "job": None}

    def show():
        if tip["win"] or not text:
            return
        x = widget.winfo_rootx() + 12
        y = widget.winfo_rooty() + widget.winfo_height() + 6
        win = tk.Toplevel(widget)
        win.wm_overrideredirect(True)
        win.wm_geometry(f"+{x}+{y}")
        tk.Label(win, text=text, font=ui_font(9), bg="#333333", fg="#FFFFFF",
                 padx=8, pady=4, justify="left").pack()
        tip["win"] = win

    def leave(_e=None):
        if tip["job"]:
            widget.after_cancel(tip["job"])
            tip["job"] = None
        if tip["win"]:
            tip["win"].destroy()
            tip["win"] = None

    def enter(_e=None):
        leave()
        tip["job"] = widget.after(delay, show)

    widget.bind("<Enter>", enter, add="+")
    widget.bind("<Leave>", leave, add="+")
    widget.bind("<ButtonPress>", leave, add="+")


# --------------------------------------------------------------------------
# 预览面板
# --------------------------------------------------------------------------

class PreviewPane(ttk.Frame):
    """手机预览。

    结构：Canvas（负责纵向滚动）→ 一个固定宽度的白色「纸页」Frame。
    所有块都是纸页里的整行控件，左右边距统一，所以文字、卡片、图片一定对齐。
    """

    PAGE_PAD = 16          # 纸页内边距
    OFF_BG = "#E9EBEF"     # 纸页外的底色

    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.blocks: List[G.Block] = []
        self.theme_name = "business"
        self.base_dir = os.getcwd()
        self._img_cache: Dict[str, object] = {}
        self._pref_width = 375
        self.preview_width = 375
        self._last_width = 0
        self._render_job = None
        self._hover = False
        self._build()

    # ---------- 界面 ----------
    def _build(self):
        bar = ttk.Frame(self, padding=(10, 6))
        bar.pack(fill="x")
        tk.Label(bar, text="手机预览", font=ui_font(10, True), fg=C_TEXT).pack(side="left")
        self.lbl_w = tk.Label(bar, text="375px", font=ui_font(9), fg=C_MUTED)
        self.lbl_w.pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="浏览器预览", width=11, command=self.open_in_browser).pack(side="right")
        ttk.Button(bar, text="复制 HTML", width=10, command=self.copy_html).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text="－", width=3, command=lambda: self.zoom(-30)).pack(side="right", padx=(4, 0))
        ttk.Button(bar, text="＋", width=3, command=lambda: self.zoom(30)).pack(side="right", padx=(0, 2))

        wrap = tk.Frame(self, bg=C_BG)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas = tk.Canvas(wrap, bg=self.OFF_BG, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg="#FFFFFF", bd=0, highlightthickness=0)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.bind_all("<MouseWheel>", self._global_wheel, add="+")
        self.canvas.bind("<Enter>", lambda e: setattr(self, "_hover", True))
        self.canvas.bind("<Leave>", lambda e: setattr(self, "_hover", False))

    # ---------- 布局 ----------
    def _on_inner(self, _e=None):
        try:
            self.inner.update_idletasks()
        except Exception:
            pass
        h = max(1, self.inner.winfo_reqheight())
        view = max(1, self.canvas.winfo_height())
        # 只约束宽度；高度交给 Frame 自己撑开，否则会把内容裁成 1px
        self.canvas.itemconfigure(self.win, width=self.preview_width)
        self.canvas.configure(scrollregion=(0, 0, self.preview_width, max(h, view)))

    def _on_configure(self, e):
        if abs(e.width - self._last_width) > 2:
            self._last_width = e.width
            self.schedule_render(80)

    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")
        return "break"

    def _global_wheel(self, e):
        if self._hover:
            self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def zoom(self, delta: int):
        avail = max(300, self._last_width - 16) if self._last_width else 560
        self._pref_width = max(300, min(avail, 560, self._pref_width + delta))
        self.lbl_w.config(text=f"{self._pref_width}px")
        self.schedule_render(30)

    def reset_scroll(self):
        try:
            self.canvas.yview_moveto(0)
        except Exception:
            pass

    # ---------- 数据 ----------
    def set_blocks(self, blocks: List[G.Block], theme_name: str = "business", base_dir: str = ""):
        self.blocks = blocks or []
        self.theme_name = theme_name if theme_name in G.GUI_THEMES else "business"
        if base_dir:
            self.base_dir = base_dir
        self.schedule_render(0)

    def _theme(self) -> Dict[str, str]:
        return G.GUI_THEMES.get(self.theme_name, G.GUI_THEMES["business"])

    def schedule_render(self, delay: int = 120):
        if self._render_job:
            try:
                self.after_cancel(self._render_job)
            except Exception:
                pass
        self._render_job = self.after(delay, self.render)

    # ---------- 渲染 ----------
    def render(self):
        self._render_job = None
        ypos = self.canvas.yview()[0]
        for w in self.inner.winfo_children():
            w.destroy()
        self._img_cache.clear()

        avail = max(280, (self._last_width or 420) - 16)
        self.preview_width = max(280, min(self._pref_width, avail))
        self.lbl_w.config(text=f"{self.preview_width}px")
        self.canvas.itemconfigure(self.win, width=self.preview_width)
        self.inner.configure(width=self.preview_width, bg="#FFFFFF")

        if not self.blocks:
            self._label("在左侧写点内容，这里实时预览", 11, C_MUTED, 60)
            self._on_inner()
            return

        for b in self.blocks:
            self._block(b)
        tk.Frame(self.inner, bg="#FFFFFF", height=20).pack(fill="x")
        self._on_inner()
        try:
            self.canvas.yview_moveto(ypos)
        except Exception:
            pass

    # ---------- 块渲染 ----------
    def _label(self, text, size, color, pady=0, bold=False, align="left", bg="#FFFFFF"):
        lab = tk.Label(self.inner, text=text, font=px_font(size, bold), fg=color, bg=bg,
                       justify=align, anchor={"left": "w", "center": "center", "right": "e"}[align],
                       wraplength=max(120, self.preview_width - self.PAGE_PAD * 2))
        lab.pack(fill="x", padx=self.PAGE_PAD, pady=(0, pady))
        return lab

    def _block(self, b: G.Block):
        kind = b.kind
        if kind == "title":
            self._label(b.text, 21, "#111111", 6, bold=True)
            return
        if kind == "meta":
            self._label(b.text, 12, "#999999", 18)
            return
        if kind in ("section", "closing"):
            row = tk.Frame(self.inner, bg="#FFFFFF")
            row.pack(fill="x", padx=self.PAGE_PAD, pady=(18, 8))
            if b.accent:
                tk.Frame(row, bg=b.accent, width=3).pack(side="left", fill="y")
                inner = tk.Frame(row, bg="#FFFFFF")
                inner.pack(side="left", fill="x", expand=True, padx=(8, 0))
                num, rest = self._split_number(b.text)
                txt = (num + "  " if num else "") + rest
                tk.Label(inner, text=txt, font=px_font(17, True), fg="#1A1A1A", bg="#FFFFFF",
                         anchor="w", justify="left",
                         wraplength=max(120, self.preview_width - self.PAGE_PAD * 2 - 12)).pack(fill="x")
            else:
                tk.Label(row, text=b.text, font=px_font(17, True), fg="#1A1A1A", bg="#FFFFFF",
                         anchor="w", justify="left",
                         wraplength=max(120, self.preview_width - self.PAGE_PAD * 2)).pack(fill="x")
            return
        if kind == "card":
            box = tk.Frame(self.inner, bg=b.bg or "#EAF1FC")
            box.pack(fill="x", padx=self.PAGE_PAD, pady=(4, 16))
            lines = [ln.strip() for ln in b.text.split("\n") if ln.strip()]
            for k, line in enumerate(lines):
                tk.Label(box, text=line, font=px_font(13 if k == 0 else 14, k == 0),
                         fg=self._theme()["accent"] if k == 0 else "#333333",
                         bg=b.bg or "#EAF1FC", anchor="w", justify="left",
                         wraplength=max(120, self.preview_width - self.PAGE_PAD * 2 - 28)).pack(
                    fill="x", padx=14, pady=(10 if k == 0 else 3, 0))
            tk.Frame(box, bg=b.bg or "#EAF1FC", height=10).pack(fill="x")
            return
        if kind == "quote":
            box = tk.Frame(self.inner, bg="#F7F8FA")
            box.pack(fill="x", padx=self.PAGE_PAD, pady=(2, 14))
            tk.Frame(box, bg=self._theme()["accent"], width=3).pack(side="left", fill="y")
            tk.Label(box, text=b.text, font=px_font(15), fg="#555555", bg="#F7F8FA",
                     anchor="w", justify="left",
                     wraplength=max(120, self.preview_width - self.PAGE_PAD * 2 - 24)).pack(
                side="left", fill="x", expand=True, padx=12, pady=10)
            return
        if kind == "list":
            for item in (x for x in b.text.split("\u0001") if x.strip()):
                row = tk.Frame(self.inner, bg="#FFFFFF")
                row.pack(fill="x", padx=self.PAGE_PAD, pady=(0, 4))
                tk.Label(row, text="·", font=px_font(16), fg="#8A8F96", bg="#FFFFFF").pack(side="left")
                tk.Label(row, text=item.strip(), font=px_font(16), fg="#333333", bg="#FFFFFF",
                         anchor="w", justify="left",
                         wraplength=max(120, self.preview_width - self.PAGE_PAD * 2 - 16)).pack(
                    side="left", fill="x", expand=True)
            return
        if kind == "code":
            box = tk.Frame(self.inner, bg="#1F2937")
            box.pack(fill="x", padx=self.PAGE_PAD, pady=(4, 14))
            tk.Label(box, text=b.text or " ", font=(MONO, -12), fg="#E5E7EB", bg="#1F2937",
                     anchor="w", justify="left",
                     wraplength=max(120, self.preview_width - self.PAGE_PAD * 2 - 24)).pack(
                fill="x", padx=12, pady=10)
            return
        if kind == "img":
            self._image(b)
            return
        if kind == "caption":
            self._label(b.text, 12, "#888888", 14, align="center")
            return
        # 普通段落
        self._label(b.text, 16, "#333333", 12)

    def _image(self, b: G.Block):
        src = b.src or ""
        path = src if os.path.isabs(src) else os.path.normpath(os.path.join(self.base_dir, src))
        max_w = max(160, self.preview_width - self.PAGE_PAD * 2)
        photo = None
        if src and os.path.exists(path):
            try:
                if HAS_PIL:
                    im = Image.open(path)
                    im.thumbnail((max_w, 300))
                    photo = ImageTk.PhotoImage(im)
                elif path.lower().endswith((".png", ".gif")):
                    photo = tk.PhotoImage(file=path)
            except Exception:
                photo = None
        if photo is not None:
            self._img_cache[path] = photo
            tk.Label(self.inner, image=photo, bg="#FFFFFF", bd=0).pack(pady=(6, 4))
        else:
            msg = "［配图位：1080×608］"
            if src and not os.path.exists(path):
                msg = "［图片未找到：" + os.path.basename(src) + "］"
            self._label(msg, 11, "#9AA3AD", 6, align="center")
        if b.text and b.text.strip():
            self._label(b.text.strip(), 12, "#888888", 14, align="center")

    @staticmethod
    def _split_number(text: str) -> Tuple[str, str]:
        m = re.match(r"^(\d{2})\s*(.+)$", text.strip())
        if m:
            return m.group(1), m.group(2)
        return "", text.strip()

    # ---------- 动作 ----------
    def open_in_browser(self):
        cb = getattr(self, "html_provider", None)
        if not cb:
            return
        html = cb()
        if not html:
            return
        import tempfile
        import webbrowser
        fd, path = tempfile.mkstemp(prefix="wechat_preview_", suffix=".html")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        webbrowser.open("file:///" + path.replace("\\", "/"))

    def copy_html(self):
        cb = getattr(self, "html_provider", None)
        if not cb:
            return
        html = cb()
        if not html:
            return
        self.clipboard_clear()
        self.clipboard_append(html)
        messagebox.showinfo("已复制", "HTML 已复制到剪贴板。\n\n粘贴进公众号后台前，建议先用「浏览器预览」看一眼。")


# --------------------------------------------------------------------------
# 图片插入对话框
# --------------------------------------------------------------------------

class ImageDialog(tk.Toplevel):
    def __init__(self, master, base_dir: str, default_section: str = ""):
        super().__init__(master)
        self.title("插入图片")
        self.configure(bg=C_PANEL)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.base_dir = base_dir
        self.result: Optional[str] = None
        self._photo = None
        self._src = ""

        frm = tk.Frame(self, bg=C_PANEL, padx=18, pady=14)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        def row(r, label):
            tk.Label(frm, text=label, font=ui_font(10), fg=C_TEXT, bg=C_PANEL,
                     anchor="e", width=7).grid(row=r, column=0, sticky="e", pady=5, padx=(0, 8))

        row(0, "图片文件")
        path_frm = tk.Frame(frm, bg=C_PANEL)
        path_frm.grid(row=0, column=1, sticky="we", pady=5)
        self.var_path = tk.StringVar()
        tk.Entry(path_frm, textvariable=self.var_path, font=ui_font(10), width=40).pack(side="left", fill="x", expand=True)
        ttk.Button(path_frm, text="选择…", width=7, command=self.browse).pack(side="left", padx=(6, 0))
        ttk.Button(path_frm, text="选择最近的图", width=12,
                   command=self.pick_recent).pack(side="left", padx=(6, 0))

        row(1, "预览")
        self.lbl_img = tk.Label(frm, text="（选择图片后显示）", font=px_font(9), fg=C_MUTED,
                                bg="#F5F6F8", width=44, height=7, anchor="center")
        self.lbl_img.grid(row=1, column=1, sticky="we", pady=5)

        row(2, "alt 文字")
        self.var_alt = tk.StringVar()
        tk.Entry(frm, textvariable=self.var_alt, font=ui_font(10)).grid(row=2, column=1, sticky="we", pady=5)

        row(3, "图注")
        self.var_cap = tk.StringVar()
        tk.Entry(frm, textvariable=self.var_cap, font=ui_font(10)).grid(row=3, column=1, sticky="we", pady=5)

        row(4, "图源")
        self.var_src = tk.StringVar(value="图源：待补")
        tk.Entry(frm, textvariable=self.var_src, font=ui_font(10)).grid(row=4, column=1, sticky="we", pady=5)

        row(5, "存档")
        self.var_copy = tk.BooleanVar(value=True)
        tk.Checkbutton(frm, text="复制到 imgs/ 文件夹（推荐，图片不会丢）", variable=self.var_copy,
                       font=ui_font(9), bg=C_PANEL, fg=C_TEXT, anchor="w").grid(row=5, column=1, sticky="we")

        tk.Label(frm, text="提示：图注写「谁 + 在做什么 + 证明了什么」，图源写清出处；纯装饰图可只写 alt。",
                 font=ui_font(9), fg=C_MUTED, bg=C_PANEL, wraplength=430, justify="left").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

        btns = tk.Frame(self, bg=C_PANEL, padx=18, pady=12)
        btns.pack(fill="x")
        ttk.Button(btns, text="取消", width=8, command=self._cancel).pack(side="right")
        ttk.Button(btns, text="插入", width=10, command=self._ok).pack(side="right", padx=(0, 8))
        ttk.Button(btns, text="删除这张", width=10, command=self._delete).pack(side="left")

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.after(60, self._center)

    def _center(self):
        self.update_idletasks()
        p = self.master.winfo_rootx(), self.master.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        mw, mh = self.master.winfo_width(), self.master.winfo_height()
        self.geometry(f"+{p[0] + (mw - w) // 2}+{p[1] + max(0, (mh - h) // 2)}")

    def pick_recent(self):
        folder = os.path.join(self.base_dir, "imgs")
        if os.path.isdir(folder):
            files = [f for f in os.listdir(folder) if f.lower().endswith(G.IMG_EXTS)]
            if files:
                files.sort()
                self.var_path.set(os.path.join(folder, files[-1]))
                self.browse(path=os.path.join(folder, files[-1]))
                return
        messagebox.showinfo("没有图片", "imgs/ 里还没有图片。\n点「选择…」从电脑里挑一张吧。")

    def browse(self, path: str = ""):
        if not path:
            path = filedialog.askopenfilename(
                title="选择图片", parent=self,
                filetypes=[("图片", " ".join("*" + e for e in G.IMG_EXTS)), ("所有文件", "*.*")])
        if not path:
            return
        self.var_path.set(path)
        self._src = path
        if not self.var_alt.get():
            self.var_alt.set(self._guess_alt(path))
        if not self.var_cap.get():
            self.var_cap.set(self._guess_caption(path))
        self._show_thumb(path)

    @staticmethod
    def _guess_alt(path: str) -> str:
        stem = os.path.splitext(os.path.basename(path))[0]
        s = re.sub(r"^[\d_\-\s]+", "", stem)
        s = re.sub(r"(?i)(img|image|photo|screenshot|截图|封面|配图|\d{2,4}[x×]\d{2,4})", " ", s)
        s = re.sub(r"[\-_]+", " ", s).strip()
        return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s) or "配图"

    @classmethod
    def _guess_caption(cls, path: str) -> str:
        alt = cls._guess_alt(path)
        if alt and alt != "配图":
            return f"{alt}。图源：待补"
        return "图源：待补"

    def _show_thumb(self, path: str):
        try:
            if HAS_PIL:
                im = Image.open(path)
                im.thumbnail((320, 180))
                self._photo = ImageTk.PhotoImage(im)
                self.lbl_img.configure(image=self._photo, text="", width=320, height=180)
            else:
                self.lbl_img.configure(text="（预览需要 Pillow；不影响插入）")
        except Exception as e:
            self.lbl_img.configure(image="", text=f"无法预览：{e}")

    def _delete(self):
        self.result = "__DELETE__"
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    def _ok(self):
        path = self.var_path.get().strip()
        if not path:
            messagebox.showwarning("还差一步", "先选一张图片，或者直接把图片路径粘到输入框里。", parent=self)
            return
        if not (path.startswith("http") or os.path.exists(path)):
            if not messagebox.askyesno("文件不存在", f"找不到这个文件：\n{path}\n\n仍然插入吗？", parent=self):
                return
        shown_path = path
        if self.var_copy.get() and os.path.exists(path):
            folder = os.path.join(self.base_dir, "imgs")
            try:
                name = G.import_image(path, folder, self._section_hint())
                shown_path = os.path.join("imgs", name).replace(os.sep, "/")
            except Exception as e:
                messagebox.showwarning("复制失败", f"保留原路径插入。\n{e}", parent=self)
        elif os.path.exists(path):
            try:
                shown_path = os.path.relpath(path, self.base_dir).replace(os.sep, "/")
            except Exception:
                shown_path = path
        self.result = G.build_img_marker(shown_path, self.var_alt.get().strip(),
                                         self.var_cap.get().strip(), self.var_src.get().strip())
        self.destroy()

    def _section_hint(self) -> str:
        return ""


# --------------------------------------------------------------------------
# 体检对话框
# --------------------------------------------------------------------------

LEVEL_COLORS = {"error": "#C0302F", "warn": "#B7791F", "info": "#2F6FD0"}


class CheckDialog(tk.Toplevel):
    def __init__(self, master, issues: List[G.Issue], on_jump):
        super().__init__(master)
        self.title("发布前体检")
        self.configure(bg=C_PANEL)
        self.geometry("620x430")
        self.transient(master)
        self.grab_set()
        self.issues = issues
        self.on_jump = on_jump

        head = tk.Frame(self, bg=C_PANEL, padx=16, pady=12)
        head.pack(fill="x")
        errs = sum(1 for i in issues if i.level == "error")
        warns = sum(1 for i in issues if i.level == "warn")
        infos = sum(1 for i in issues if i.level == "info")
        if not issues:
            text, color = "✓ 没发现问题，可以发了", "#1E7B34"
        else:
            text = f"✖ {errs}　▲ {warns}　ℹ {infos}"
            color = "#C0302F" if errs else ("#B7791F" if warns else "#2F6FD0")
        tk.Label(head, text=text, font=ui_font(13, True), fg=color, bg=C_PANEL).pack(side="left")
        tk.Label(head, text="点条目可跳到对应行", font=ui_font(9), fg=C_MUTED, bg=C_PANEL).pack(side="left", padx=10)

        body = tk.Frame(self, bg=C_PANEL, padx=12)
        body.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(body, font=ui_font(10), activestyle="none",
                                  selectbackground="#E8F0FB", selectforeground=C_TEXT,
                                  bg="#FBFBFC", highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)
        for i, it in enumerate(issues):
            self.listbox.insert("end", self._fmt(it))
            self.listbox.itemconfig(i, foreground=LEVEL_COLORS.get(it.level, C_TEXT))
        if not issues:
            self.listbox.insert("end", "  ✓ 标题、结论卡、小节编号、图注、段长、结尾组件都过了")
        self.listbox.bind("<Double-Button-1>", self._jump)
        self.listbox.bind("<Return>", self._jump)

        btns = tk.Frame(self, bg=C_PANEL, padx=16, pady=12)
        btns.pack(fill="x")
        ttk.Button(btns, text="关闭", width=8, command=self.destroy).pack(side="right")
        ttk.Button(btns, text="跳到该行", width=10, command=self._jump).pack(side="right", padx=(0, 8))

    @staticmethod
    def _fmt(it: G.Issue) -> str:
        line = f"（第 {it.line} 行）" if it.line > 0 else ""
        detail = f" — {it.detail}" if it.detail else ""
        return f" {it.icon} {it.title}{line}{detail}"

    def _jump(self, _e=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self.issues):
            self.on_jump(self.issues[idx])
            self.destroy()


# --------------------------------------------------------------------------
# 主应用
# --------------------------------------------------------------------------

class App:
    def __init__(self, root: tk.Tk, initial: str = ""):
        self.root = root
        self.path: str = ""
        self.base_dir: str = os.getcwd()   # 图片相对路径的基准目录
        self.dirty = False
        self.theme_name = "business"
        self.last_html = ""
        self._preview_job = None
        self._highlight_job = None

        self._style()
        self._build_menu()
        self._build_body()
        self._bind_keys()

        if initial and os.path.exists(initial):
            self.open_file(initial)
        else:
            self.set_text(WELCOME)
            self.dirty = False
        self.refresh_all()

    # ---------- 样式 ----------
    def _style(self):
        self.root.title(APP_TITLE)
        self.root.geometry("1360x880")
        self.root.minsize(1080, 700)
        self.root.configure(bg=C_BG)
        st = ttk.Style(self.root)
        try:
            st.theme_use("vista")
        except Exception:
            pass
        st.configure("TButton", font=ui_font(9), padding=(8, 4))
        st.configure("TFrame", background=C_BG)
        st.configure("TLabelframe", background=C_BG)
        st.configure("TLabelframe.Label", background=C_BG, font=ui_font(9, True))
        self.root.option_add("*Font", ui_font(10))

    # ---------- 菜单 ----------
    def _build_menu(self):
        m = tk.Menu(self.root)
        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label="新建", accelerator="Ctrl+N", command=self.new_file)
        fm.add_command(label="打开…", accelerator="Ctrl+O", command=lambda: self.open_file())
        fm.add_command(label="从网页 / Word 导入…", command=self.import_other)
        fm.add_command(label="批量转换…", command=self.batch_convert)
        fm.add_command(label="保存", accelerator="Ctrl+S", command=self.save)
        fm.add_command(label="另存为…", accelerator="Ctrl+Shift+S", command=lambda: self.save(as_new=True))
        fm.add_separator()
        fm.add_command(label="导出 Markdown…", command=self.export_md)
        fm.add_command(label="导出可粘贴 HTML…", command=self.export_html)
        fm.add_separator()
        fm.add_command(label="打开 imgs 文件夹", command=self.open_imgs_dir)
        fm.add_separator()
        fm.add_command(label="退出", command=self.on_close)
        m.add_cascade(label="文件", menu=fm)

        em = tk.Menu(m, tearoff=0)
        em.add_command(label="加粗", accelerator="Ctrl+B", command=self.act_bold)
        em.add_command(label="小标题", accelerator="Ctrl+1", command=self.act_section)
        em.add_command(label="结论卡", accelerator="Ctrl+2", command=lambda: self.act_insert("card"))
        em.add_command(label="图片…", accelerator="Ctrl+I", command=self.act_image)
        em.add_command(label="引用", accelerator="Ctrl+3", command=lambda: self.act_insert("quote"))
        em.add_command(label="列表", accelerator="Ctrl+4", command=lambda: self.act_insert("list"))
        em.add_command(label="互动提问", command=lambda: self.act_insert("cta"))
        em.add_command(label="关注引导", command=lambda: self.act_insert("end"))
        m.add_cascade(label="插入", menu=em)

        tm = tk.Menu(m, tearoff=0)
        self.theme_var = tk.StringVar(value="business")
        for key, meta in G.GUI_THEMES.items():
            tm.add_radiobutton(label=f"{meta['label']}（{key}）", value=key, variable=self.theme_var,
                               command=self.switch_theme)
        tm.add_separator()
        tm.add_command(label="发布前体检", accelerator="Ctrl+K", command=self.run_check)
        em.add_command(label="写在最后", command=lambda: self.act_insert("closing"))
        m.add_cascade(label="主题 / 检查", menu=tm)

        hm = tk.Menu(m, tearoff=0)
        hm.add_command(label="使用说明", command=self.show_help)
        hm.add_command(label="关于", command=self.show_about)
        m.add_cascade(label="帮助", menu=hm)
        self.root.config(menu=m)

    # ---------- 主界面 ----------
    def _build_body(self):
        head = tk.Frame(self.root, bg=C_PANEL)
        head.pack(fill="x", side="top")
        tk.Label(head, text="公众号排版编辑器", font=ui_font(13, True), fg=C_TEXT, bg=C_PANEL).pack(side="left", padx=(16, 10), pady=10)
        self.lbl_file = tk.Label(head, text="未命名", font=ui_font(9), fg=C_MUTED, bg=C_PANEL)
        self.lbl_file.pack(side="left")

        right = tk.Frame(head, bg=C_PANEL)
        right.pack(side="right", padx=(6, 10), pady=9)
        ttk.Button(right, text="体检", width=6, command=self.run_check).pack(side="right", padx=(4, 0))
        ttk.Button(right, text="HTML", width=6, command=self.export_html).pack(side="right", padx=(4, 0))
        ttk.Button(right, text="MD", width=6, command=self.export_md).pack(side="right", padx=(4, 0))
        ttk.Button(right, text="保存", width=6, command=self.save).pack(side="right", padx=(4, 0))

        tk.Frame(self.root, bg=C_LINE, height=1).pack(fill="x")

        self.paned = ttk.PanedWindow(self.root, orient="horizontal")
        self.paned.pack(fill="both", expand=True, padx=10, pady=10)

        # 左：编辑
        left = tk.Frame(self.paned, bg=C_PANEL)
        self.paned.add(left, weight=1)
        self._build_editor(left)

        # 右：预览
        self.preview = PreviewPane(self.paned)
        self.preview.html_provider = self.build_html
        self.paned.add(self.preview, weight=1)

        # 初始分栏：左 62%，右 38%
        self.root.after(80, self._init_sash)

        # 状态栏
        bar = tk.Frame(self.root, bg=C_PANEL, height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.lbl_stat = tk.Label(bar, text="", font=ui_font(9), fg=C_MUTED, bg=C_PANEL)
        self.lbl_stat.pack(side="left", padx=16)
        self.lbl_msg = tk.Label(bar, text="", font=ui_font(9), fg=C_ACCENT, bg=C_PANEL)
        self.lbl_msg.pack(side="right", padx=16)

    def _init_sash(self):
        try:
            w = self.paned.winfo_width()
            if w > 200:
                self.paned.sashpos(0, max(760, int(w * 0.62)))
        except Exception:
            pass

    def _build_editor(self, parent: tk.Frame):
        # 标题
        top = tk.Frame(parent, bg=C_PANEL, padx=12, pady=8)
        top.pack(fill="x")
        tk.Label(top, text="标题", font=ui_font(9), fg=C_MUTED, bg=C_PANEL).pack(side="left")
        self.var_title = tk.StringVar()
        self.ent_title = tk.Entry(top, textvariable=self.var_title, font=ui_font(11, True),
                                  bd=0, highlightthickness=1, highlightbackground=C_LINE,
                                  highlightcolor=C_ACCENT, bg="#FBFCFF")
        self.ent_title.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=4)
        self.var_title.trace_add("write", lambda *a: self._on_title_changed())

        # 工具条
        tb = tk.Frame(parent, bg=C_PANEL, padx=8, pady=6)
        tb.pack(fill="x")
        tools = [
            ("B", "加粗（Ctrl+B）", self.act_bold, 2),
            ("标题", "把当前行变成「## 01 标题」", self.act_section, 4),
            ("结论", "插入「先说结论」3 行卡片", lambda: self.act_insert("card"), 4),
            ("配图", "插入图片 / 补图注（Ctrl+I）", self.act_image, 4),
            ("引用", "插入引用块", lambda: self.act_insert("quote"), 4),
            ("列表", "把当前行变成列表项", lambda: self.act_insert("list"), 4),
            ("互动", "插入互动提问", lambda: self.act_insert("cta"), 4),
            ("关注", "插入关注引导", lambda: self.act_insert("end"), 4),
        ]
        for text, tip, cmd, w in tools:
            b = ttk.Button(tb, text=text, width=w, command=cmd)
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)
        ttk.Button(tb, text="插入图片…", width=9, command=self.act_image).pack(side="right", padx=(6, 2))
        ttk.Button(tb, text="发布前体检", width=9, command=self.run_check).pack(side="right", padx=2)

        hint = tk.Label(parent, text="提示：图片用 [IMG:路径|说明|图注|图源]；[CTA] 互动、[END] 关注；「写在最后」自动收尾。",
                        font=ui_font(9), fg=C_MUTED, bg="#FBFBFC", anchor="w", padx=12, pady=4)
        hint.pack(fill="x")

        # 文本区
        wrap = tk.Frame(parent, bg=C_PANEL)
        wrap.pack(fill="both", expand=True)
        self.txt = tk.Text(wrap, wrap="word", undo=True, autoseparators=True, maxundo=-1,
                           font=(MONO, 11), bg="#FCFCFD", fg=C_TEXT, insertbackground=C_ACCENT,
                           padx=14, pady=10, bd=0, highlightthickness=1,
                           highlightbackground=C_LINE, highlightcolor=C_ACCENT,
                           spacing1=2, spacing3=2, tabs="24")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        self.txt.bind("<KeyRelease>", self._on_edit)
        self.txt.bind("<ButtonRelease-1>", lambda e: self._schedule_highlight())
        self.txt.bind("<<Modified>>", self._on_modified)
        self._setup_tags()

    def _setup_tags(self):
        t = self.txt
        t.tag_configure("h1", font=(FONT, 14, "bold"), foreground="#111111", spacing1=6, spacing3=4)
        t.tag_configure("h2", font=(FONT, 12, "bold"), foreground=C_ACCENT, spacing1=8, spacing3=2)
        t.tag_configure("mark", foreground="#9A6A00", font=(MONO, 10))
        t.tag_configure("quote", foreground="#6B7280", font=(MONO, 10, "italic"))
        t.tag_configure("bold", font=(MONO, 11, "bold"))
        t.tag_configure("meta", foreground="#8A8F96")
        t.tag_configure("list", foreground="#2F6FD0")

    def _bind_keys(self):
        r = self.root
        r.bind("<Control-n>", lambda e: self.new_file())
        r.bind("<Control-o>", lambda e: self.open_file())
        r.bind("<Control-s>", lambda e: self.save())
        r.bind("<Control-S>", lambda e: self.save(as_new=True))
        r.bind("<Control-b>", lambda e: self.act_bold())
        r.bind("<Control-i>", lambda e: self.act_image())
        r.bind("<Control-k>", lambda e: self.run_check())
        r.bind("<Control-Key-1>", lambda e: self.act_section())
        r.bind("<Control-Key-2>", lambda e: self.act_insert("card"))
        r.bind("<Control-Key-3>", lambda e: self.act_insert("quote"))
        r.bind("<Control-Key-4>", lambda e: self.act_insert("list"))
        r.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- 文本读写 ----------
    def base(self) -> str:
        """图片相对路径的基准目录：优先用打开/导入时的源目录。"""
        if self.base_dir and os.path.isdir(self.base_dir):
            return self.base_dir
        return os.path.dirname(os.path.abspath(self.path)) if self.path else os.getcwd()

    def get_text(self) -> str:
        return self.txt.get("1.0", "end-1c")

    def set_text(self, text: str):
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", text)
        self.txt.edit_reset()
        self._schedule_highlight()
        self.syncing_title = True
        self.var_title.set(self._first_title())
        self.syncing_title = False

    def _first_title(self) -> str:
        for ln in self.get_text().split("\n"):
            s = ln.strip()
            if s.startswith("# "):
                return s[2:].strip()
            if s:
                return s
        return ""

    def _on_title_changed(self):
        if getattr(self, "syncing_title", False):
            return
        title = self.var_title.get().strip()
        text = self.get_text()
        lines = text.split("\n")
        idx = -1
        for i, ln in enumerate(lines):
            if ln.strip():
                idx = i
                break
        if idx < 0:
            self.set_text(f"# {title}\n")
            self.dirty = True
            return
        if lines[idx].strip().startswith("# "):
            lines[idx] = f"# {title}" if title else "# "
        else:
            lines.insert(idx, f"# {title}")
        new = "\n".join(lines)
        pos = self.txt.index("insert")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", new)
        self.txt.mark_set("insert", pos)
        self._on_edit()

    def _on_modified(self, _e=None):
        try:
            self.txt.edit_modified(False)
        except Exception:
            pass

    def _on_edit(self, _e=None):
        self.dirty = True
        self._update_stat()
        self.syncing_title = True
        self.var_title.set(self._first_title())
        self.syncing_title = False
        self.schedule_preview()
        self._schedule_highlight()

    def _schedule_highlight(self):
        if self._highlight_job:
            try:
                self.root.after_cancel(self._highlight_job)
            except Exception:
                pass
        self._highlight_job = self.root.after(180, self.highlight)

    def highlight(self):
        self._highlight_job = None
        t = self.txt
        for tag in ("h1", "h2", "mark", "quote", "bold", "meta", "list"):
            t.tag_remove(tag, "1.0", "end")
        text = self.get_text()
        for i, line in enumerate(text.split("\n"), 1):
            if line.startswith("# "):
                t.tag_add("h1", f"{i}.0", f"{i}.end")
            elif re.match(r"^#{2,4}\s", line):
                t.tag_add("h2", f"{i}.0", f"{i}.end")
            elif line.strip().startswith(">"):
                t.tag_add("quote", f"{i}.0", f"{i}.end")
            elif line.strip().startswith("["):
                t.tag_add("mark", f"{i}.0", f"{i}.end")
            elif re.match(r"^\s*([-*+]|\d{1,2}[.)])\s", line):
                t.tag_add("list", f"{i}.0", f"{i}.end")
            elif re.match(r"^(日期|作者|标题)\s*[:：]", line.strip()):
                t.tag_add("meta", f"{i}.0", f"{i}.end")
            for m in re.finditer(r"\*\*(.+?)\*\*", line):
                t.tag_add("bold", f"{i}.{m.start()}", f"{i}.{m.end()}")
            for m in re.finditer(r"\[IMG:[^\]]*\]", line):
                t.tag_add("mark", f"{i}.{m.start()}", f"{i}.{m.end()}")

    # ---------- 预览 ----------
    def schedule_preview(self):
        if self._preview_job:
            try:
                self.root.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.root.after(320, self.refresh_preview)

    def build_html(self) -> str:
        try:
            text = W.prepare_markdown(self.get_text())
            base = self.base()
            art = W.parse_content(text, base)
            W.normalize(art, want_summary=True, want_cta=False, want_end=False)
            # 预览里结论卡单行限长，避免在手机宽度下折成两行
            for b in art.lead:
                if b.kind == "summary":
                    b.items = [W._elide(t, 24) for t in b.items]
            title = self.var_title.get().strip() if hasattr(self, "var_title") else ""
            html = W.render_html(art, W.THEMES[self.theme_name], title)
            self.last_html = html
            return html
        except Exception:
            return ""

    def refresh_preview(self):
        self._preview_job = None
        html = self.build_html()
        blocks = G.parse_preview_blocks(html) if html else []
        base = self.base()
        self.preview.set_blocks(blocks, self.theme_name, base)

    def refresh_all(self):
        self._update_stat()
        self.highlight()
        self.refresh_preview()

    def _update_stat(self):
        text = self.get_text()
        art = W.parse_content(text, os.getcwd())
        n_img = len(re.findall(r"\[IMG:", text))
        n_sec = len(re.findall(r"^#{2,4}\s", text, flags=re.M))
        self.lbl_stat.config(
            text=f"{art.char_count()} 字　·　约 {art.read_minutes()} 分钟　·　{n_sec} 个小节　·　{n_img} 张图")

    def switch_theme(self):
        self.theme_name = self.theme_var.get()
        self.refresh_preview()
        self.flash(f"已切换到「{G.GUI_THEMES[self.theme_name]['label']}」主题")

    def flash(self, msg: str, ms: int = 2600):
        self.lbl_msg.config(text=msg)
        self.root.after(ms, lambda: self.lbl_msg.config(text=""))

    # ---------- 编辑动作 ----------
    def _selection(self) -> Tuple[int, int]:
        try:
            a = self.txt.index("sel.first")
            b = self.txt.index("sel.last")
            return (self.txt.count("1.0", a, "chars")[0], self.txt.count("1.0", b, "chars")[0])
        except tk.TclError:
            pos = self.txt.count("1.0", "insert", "chars")[0]
            return (pos, pos)

    def _apply(self, edit: G.Edit, msg: str = ""):
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", edit.text)
        if edit.sel_start == edit.sel_end:
            self.txt.mark_set("insert", f"1.0+{edit.sel_start}c")
        else:
            self.txt.tag_add("sel", f"1.0+{edit.sel_start}c", f"1.0+{edit.sel_end}c")
            self.txt.mark_set("insert", f"1.0+{edit.sel_end}c")
        self.txt.see("insert")
        self._on_edit()
        if msg:
            self.flash(msg)

    def act_bold(self):
        s, e = self._selection()
        edit = G.wrap_selection(self.get_text(), (s, e), "**", "**", "加粗文字")
        self._apply(edit, "已加粗（再点一次是取消，需要手动删掉两侧 **）")

    def act_section(self):
        pos = self._selection()[0]
        self._apply(G.number_heading(self.get_text(), pos), "已变成小标题，编号自动 +1")

    def act_insert(self, kind: str):
        pos = self._selection()[0]
        if kind == "list":
            self._apply(G.listify(self.get_text(), pos), "已变成列表项")
            return
        self._apply(G.insert_block(self.get_text(), pos, kind), f"已插入：{kind}")

    def act_image(self):
        base = self.base()
        pos = self._selection()[0]
        text = self.get_text()
        start, end = G.current_line(text, pos)
        line = text[start:end].strip()
        m = re.match(r"^\[IMG:([^\]]*)\]$", line, flags=re.I)
        if m:                                   # 光标已在图片行 → 编辑这张图
            self._edit_existing_image(m.group(1), start, end)
            return
        dlg = ImageDialog(self.root, base)
        self.root.wait_window(dlg)
        if not dlg.result or dlg.result == "__DELETE__":
            return
        new = text[:end] + "\n" + dlg.result + "\n" + text[end:]
        caret = end + 1 + len(dlg.result)
        self._apply(G.Edit(new, caret, caret), "已插入图片")
        self.refresh_all()

    def _edit_existing_image(self, body: str, start: int, end: int):
        dlg = ImageDialog(self.root, self.base())
        path, alt, cap, src = G.split_marker(body)
        dlg.var_path.set(path)
        dlg.var_alt.set(alt)
        dlg.var_cap.set(cap)
        dlg.var_src.set(src or "图源：待补")
        dlg.var_copy.set(False)
        if path:
            try:
                dlg.browse(path=path if os.path.isabs(path) else os.path.join(
                    self.base(), path))
            except Exception:
                pass
        self.root.wait_window(dlg)
        if dlg.result == "__DELETE__":
            text = self.get_text()
            self.txt.delete(f"1.0+{start}c", f"1.0+{end}c")
            self._on_edit()
            self.flash("已删除这张图")
            return
        if dlg.result:
            text = self.get_text()
            new = text[:start] + dlg.result + text[end:]
            self._apply(G.Edit(new, start + len(dlg.result), start + len(dlg.result)), "已更新图片")
            self.refresh_all()

    # ---------- 体检 ----------
    def run_check(self):
        base = self.base()
        issues = G.check_article(self.get_text(), base)
        dlg = CheckDialog(self.root, issues, self.jump_to_line)
        self.root.wait_window(dlg)

    def jump_to_line(self, issue: G.Issue):
        if issue.line > 0:
            self.txt.mark_set("insert", f"{issue.line}.0")
            self.txt.tag_remove("sel", "1.0", "end")
            self.txt.tag_add("sel", f"{issue.line}.0", f"{issue.line}.end")
            self.txt.see(f"{issue.line}.0")
            self.txt.focus_force()

    # ---------- 文件 ----------
    def maybe_save(self) -> bool:
        if not self.dirty:
            return True
        r = messagebox.askyesnocancel("还没保存", "当前内容有改动，要保存吗？")
        if r is None:
            return False
        if r:
            return self.save()
        return True

    def new_file(self):
        if not self.maybe_save():
            return
        self.path = ""
        self.set_text(WELCOME)
        self.dirty = False
        self.lbl_file.config(text="未命名")
        self.refresh_all()
        self.flash("新建了一个草稿")

    def open_file(self, path: str = ""):
        if not path and not self.maybe_save():
            return
        if not path:
            path = filedialog.askopenfilename(
                title="打开文案（支持 md / txt / html / docx）",
                filetypes=[
                    ("全部支持的格式", "*.md *.markdown *.txt *.text *.html *.htm *.xhtml *.docx"),
                    ("Markdown / 文本", "*.md *.markdown *.txt *.text"),
                    ("网页 HTML", "*.html *.htm *.xhtml"),
                    ("Word 文档", "*.docx"),
                    ("所有文件", "*.*"),
                ])
            if not path:
                return
        try:
            text, note, base = self._read_any(path)
        except Exception as e:
            messagebox.showerror("打开失败", f"{e}\n\n支持的格式：md / txt / html / docx")
            return
        self.path = path
        self.base_dir = base or os.path.dirname(os.path.abspath(path))
        self.source_path = path
        self.set_text(text)
        self.dirty = False
        self.lbl_file.config(text=path)
        self.refresh_all()
        self.preview.reset_scroll()
        self.flash(note or f"已打开：{os.path.basename(path)}", 4200)

    @staticmethod
    def _read_any(path: str) -> Tuple[str, str, str]:
        """读任意支持格式，返回 (可编辑的 Markdown 文本, 提示语, 图片基准目录)。"""
        import convert as C
        ext = os.path.splitext(path)[1].lower()
        base = os.path.dirname(os.path.abspath(path))
        if ext in (".md", ".markdown", ".mdown", ".txt", ".text"):
            # 用 convert.read_text：自动识别 UTF-8 / GBK / BOM
            return C.read_text(path), "", base
        loaded = C.load(path)
        info = loaded.info
        note = f"已把 {info.format} 转成可编辑文案"
        if info.wechat:
            note = "已从公众号文章页提取正文"
        elif info.format == "docx":
            note = "已从 Word 提取正文"
        bits = []
        if info.images:
            bits.append(f"{info.images} 张图")
        if info.sections:
            bits.append(f"{info.sections} 个小节")
        if info.dropped:
            bits.append(f"过滤 {info.dropped} 个非正文块")
        if bits:
            note += "（" + "，".join(bits) + "）"
        return loaded.markdown, note, loaded.base_dir or base

    def import_other(self):
        """选网页 / Word 导入，转换成可编辑文案。"""
        path = filedialog.askopenfilename(
            title="从网页 / Word 导入",
            filetypes=[("网页 / Word", "*.html *.htm *.xhtml *.docx"),
                       ("网页 HTML", "*.html *.htm *.xhtml"),
                       ("Word 文档", "*.docx"),
                       ("所有文件", "*.*")])
        if path:
            self.open_file(path)

    def batch_convert(self):
        """把选中的多个文件批量转成 Markdown 模板。"""
        files = filedialog.askopenfilenames(
            title="批量转换（可多选）",
            filetypes=[("全部支持的格式", "*.md *.markdown *.txt *.text *.html *.htm *.xhtml *.docx"),
                       ("所有文件", "*.*")])
        if not files:
            return
        out_dir = filedialog.askdirectory(title="输出到哪个文件夹")
        if not out_dir:
            return
        ok, fail = 0, []
        for src in files:
            try:
                stem = os.path.splitext(os.path.basename(src))[0]
                dst = os.path.join(out_dir, f"{stem}_模板.md")
                W.build(src, theme_name=self.theme_name, out_md=dst)
                ok += 1
            except Exception as e:
                fail.append(f"{os.path.basename(src)}: {e}")
        msg = f"成功 {ok} 个，输出到：\n{out_dir}"
        if fail:
            msg += "\n\n失败：\n" + "\n".join(fail[:8])
        messagebox.showinfo("批量转换完成", msg)

    def save(self, as_new: bool = False) -> bool:
        path = self.path
        # 从 html/docx 打开的，保存时默认另存为 .md，避免覆盖原文件
        if path and os.path.splitext(path)[1].lower() not in (".md", ".markdown", ".mdown", ".txt", ".text"):
            as_new = True
            note = "原文件是网页/Word，不能直接覆盖；保存为 .md 文案"
        else:
            note = ""
        if as_new or not path:
            default = os.path.splitext(os.path.basename(path))[0] + ".md" if path else "我的文章.md"
            path = filedialog.asksaveasfilename(
                title="保存文案", defaultextension=".md",
                filetypes=[("Markdown", "*.md"), ("文本", "*.txt")],
                initialfile=default)
            if not path:
                return False
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.get_text())
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return False
        self.path = path
        self.dirty = False
        self.lbl_file.config(text=path)
        self.flash(note or f"已保存：{os.path.basename(path)}", 3600)
        return True

    def _default_stem(self) -> str:
        title = self.var_title.get().strip() or "未命名文章"
        stem = re.sub(r'[\\/:*?"<>|\s]+', "_", title)[:40]
        base = os.path.dirname(self.path) if self.path else os.getcwd()
        return os.path.join(base, stem)

    def export_md(self):
        try:
            md = W.render_markdown(self._build_article(), self.theme_name, W.THEMES[self.theme_name],
                                   self.var_title.get().strip())
        except Exception as e:
            messagebox.showerror("生成失败", traceback.format_exc(limit=2))
            return
        path = filedialog.asksaveasfilename(title="导出 Markdown", defaultextension=".md",
                                            initialfile=os.path.basename(self._default_stem()) + "_模板.md",
                                            filetypes=[("Markdown", "*.md")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        self.flash(f"已导出：{os.path.basename(path)}")
        if messagebox.askyesno("导出成功", f"Markdown 已保存到：\n{path}\n\n要打开所在文件夹吗？"):
            self._reveal(path)

    def export_html(self):
        html = self.build_html()
        if not html:
            messagebox.showwarning("生成失败", "内容为空，先在左边写点东西。")
            return
        path = filedialog.asksaveasfilename(title="导出可粘贴 HTML", defaultextension=".html",
                                            initialfile=os.path.basename(self._default_stem()) + "_可粘贴.html",
                                            filetypes=[("HTML", "*.html")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        self.flash(f"已导出：{os.path.basename(path)}")
        if messagebox.askyesno("导出成功",
                               f"HTML 已保存到：\n{path}\n\n打开后全选（Ctrl+A）复制，再粘进公众号后台。\n现在打开吗？"):
            self._reveal(path)

    def _build_article(self):
        base = self.base()
        art = W.parse_content(W.prepare_markdown(self.get_text()), base)
        W.normalize(art, want_summary=True, want_cta=True, want_end=True)
        return art

    def _reveal(self, path: str):
        import subprocess
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                import webbrowser
                webbrowser.open(os.path.dirname(path))
        except Exception:
            pass

    def open_imgs_dir(self):
        base = self.base()
        folder = os.path.join(base, "imgs")
        os.makedirs(folder, exist_ok=True)
        self._reveal(os.path.join(folder, "."))

    # ---------- 帮助 ----------
    def show_help(self):
        messagebox.showinfo("使用说明", (
            "1. 左边写文案：标题、空行分段、## 01 小节；\n"
            "2. 工具条按钮插入组件：小标题 / 结论卡 / 配图 / 引用 / 列表 / 互动 / 关注；\n"
            "3. 配图用 [IMG:路径|说明|图注|图源]，也可以在图片对话框里点「选择…」，\n"
            "   勾选「复制到 imgs/」后图片会被复制到文案旁边，换电脑也不丢；\n"
            "4. 右边实时预览手机效果，可调宽度、换主题；\n"
            "5. 发之前点「发布前体检」，按提示逐条修；\n"
            "6. 「导出 HTML」后浏览器全选复制 → 公众号后台粘贴，图片在后台重新上传。\n\n"
            "快捷键：Ctrl+S 保存，Ctrl+B 加粗，Ctrl+1 小标题，Ctrl+2 结论卡，\n"
            "Ctrl+3 引用，Ctrl+4 列表，Ctrl+I 图片，Ctrl+K 体检。"))

    def show_about(self):
        messagebox.showinfo("关于", "公众号排版编辑器 1.0\n\n"
                                    "文案 + 图片 → 公众号排版模板\n"
                                    "配套命令行：tools/wechat_md.py\n"
                                    "主题：商务蓝 / 新闻红 / 暖橙")

    # ---------- 退出 ----------
    def on_close(self):
        if self.maybe_save():
            self.root.destroy()


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------

def self_test(root: tk.Tk, app: App) -> int:
    """无窗口自检：渲染样例、跑几个编辑动作、跑体检，确认整条链路没断。"""
    try:
        app.set_text(WELCOME)
        app.refresh_all()
        html = app.build_html()
        blocks = G.parse_preview_blocks(html)
        kinds = {b.kind for b in blocks}
        issues = G.check_article(app.get_text(), os.getcwd())

        # 编辑动作：加粗 / 小标题 / 结论卡 / 列表
        app.txt.mark_set("insert", "4.0")
        app.act_bold()
        app.act_section()
        app.act_insert("card")
        app.act_insert("list")
        text2 = app.get_text()
        blocks2 = G.parse_preview_blocks(app.build_html())

        ok = (len(html) > 500 and len(blocks) >= 5 and isinstance(issues, list)
              and "**" in text2 and "## " in text2 and len(blocks2) >= len(blocks) - 1
              and "section" in kinds)
        print(f"[selftest] blocks={len(blocks)} kinds={sorted(kinds)} issues={len(issues)} "
              f"html={len(html)} -> {'OK' if ok else 'FAIL'}")
        if not ok:
            print("  text2 snippet:", text2[:160].replace("\n", "\\n"))
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="公众号排版编辑器（Tk GUI）")
    ap.add_argument("file", nargs="?", default="", help="打开一个 .md/.txt 文案")
    ap.add_argument("--selftest", action="store_true", help="无窗口自检后退出（用于 CI）")
    args = ap.parse_args(argv)

    root = tk.Tk()
    app = App(root, initial=args.file)

    if args.selftest:
        code = self_test(root, app)
        root.destroy()
        return code

    try:
        root.state("zoomed")
    except Exception:
        pass
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
