# -*- coding: utf-8 -*-
"""
gui_core.py —— 公众号排版编辑器的「无界面」核心逻辑

与界面分离，方便单独测试：
- 把 render_html() 的输出解析成 blocks（供 Tk 预览渲染）
- 编辑器里的文本插入/包裹/行操作
- 发布前体检（规则 + 行号定位）
- 图片复制入库、主题映射

不依赖 tkinter，可被任何前端（Tk / Web / 命令行）复用。
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# 主题（与 wechat_md.THEMES 的键一一对应，这里存 GUI 需要的中性色）
# --------------------------------------------------------------------------

GUI_THEMES: Dict[str, Dict[str, str]] = {
    "business": {"label": "商务蓝", "accent": "#2F6FD0", "soft": "#EAF1FC"},
    "news": {"label": "新闻红", "accent": "#C0302F", "soft": "#FBEDED"},
    "warm": {"label": "暖橙", "accent": "#C96A1E", "soft": "#FDF0E4"},
}

FONT_STACK = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "SimHei")

BLOCK_LABELS = {
    "title": "标题",
    "meta": "信息行",
    "card": "结论卡",
    "section": "小标题",
    "closing": "收尾标题",
    "p": "正文",
    "quote": "引用块",
    "img": "配图",
    "caption": "图注",
    "cta": "互动提问",
    "end": "关注引导",
    "divider": "分隔线",
}

INK = "#333333"


# --------------------------------------------------------------------------
# 1) 预览数据：把 HTML 解析成可渲染的 blocks
# --------------------------------------------------------------------------

@dataclass
class TextChunk:
    text: str
    size: int = 16
    bold: bool = False
    color: str = INK


@dataclass
class Block:
    kind: str
    chunks: List[TextChunk] = field(default_factory=list)
    pad_top: int = 12
    pad_bottom: int = 12
    bg: str = ""
    accent: str = ""          # 左侧竖条颜色
    align: str = "left"
    src: str = ""             # 图片路径
    caption: str = ""         # 图片图注
    idx: int = -1             # 图片序号（与 md 中 [IMG] 出现顺序一致）

    @property
    def text(self) -> str:
        return "".join(c.text for c in self.chunks)


def _parse_style(style: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in (style or "").split(";"):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        out[k.strip().lower()] = v.strip()
    return out


def _px(value: str, default: int = 0) -> int:
    m = re.match(r"(-?\d+)", value or "")
    return int(m.group(1)) if m else default


def _font_size(style: Dict[str, str], default: int = 16) -> int:
    return _px(style.get("font-size", ""), default)


def _hex(color: str) -> str:
    """rgb(1,2,3) → #010203；transparent 归空；其余原样返回。"""
    color = (color or "").strip()
    if color.lower() in ("transparent", "none", "inherit", "initial"):
        return ""
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", color)
    if m:
        return "#%02X%02X%02X" % tuple(int(x) for x in m.groups())
    if color.startswith("rgba"):
        return ""
    return color


class _HTMLBlocks(HTMLParser):
    """只认识 render_html() 产出的那几种块，容错优先。"""

    CONTAINER_SKIP = {"style", "script", "head", "title"}
    BLOCK_TAGS = {"p", "section", "figure", "figcaption", "pre", "ul", "ol", "li"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: List[Block] = []
        self._stack: List[Dict] = []
        self._skip = 0

    # ---------- 栈 ----------
    def _open_block(self, attrs: Dict[str, str], style: Dict[str, str]):
        color = _hex(style.get("color", ""))
        bg = _hex(style.get("background", style.get("background-color", "")))
        border = style.get("border-left", "")
        accent = _hex(border.split()[-1]) if border else ""
        kind = attrs.get("data-b", "")
        # 没有 data-b、但父级是一个卡片/引用块时，子段落也要单独成块（便于合并内容）
        parent_kind = self._stack[-1]["kind"] if self._stack else ""
        if kind:
            if self._stack:
                self._stack[-1]["has_child"] = True
        elif parent_kind in ("card", "quote"):
            kind = "p"
        self._stack.append({
            "kind": kind,
            "style": style,
            "attrs": attrs,
            "chunks": [],
            "spans": [],
            "color": color,
            "bg": bg,
            "accent": accent,
            "margin": style.get("margin", ""),
            "padding": style.get("padding", ""),
            "has_child": False,
            "start": len(self.blocks),
        })

    def _close_block(self):
        if not self._stack:
            return
        st = self._stack.pop()
        kind = st["kind"]
        if not kind:
            if self._stack:                      # 外层容器，内容并入父级
                self._stack[-1]["chunks"].extend(st["chunks"])
            return
        if st["has_child"]:
            # 子块已经各自入列
            direct = [c for c in st["chunks"] if c.text.strip()]
            if direct and self._stack:
                self._stack[-1]["chunks"].extend(direct)
            children = self.blocks[st["start"]:]
            if kind == "card" and children:
                # 结论卡：合并成一块（标题行 + 每条一行）
                items: List[str] = []
                for ch in children:
                    if ch.kind == "card-title":
                        continue
                    for line in ch.text.split("\n"):
                        line = line.strip().lstrip("·・-*").strip()
                        if line:
                            items.append(line)
                title_text = next((ch.text for ch in children if ch.kind == "card-title"), "先说结论")
                title_color = next((ch.chunks[0].color for ch in children
                                    if ch.kind == "card-title" and ch.chunks), INK)
                merged: List[TextChunk] = [TextChunk(title_text, size=13, bold=True, color=title_color)]
                if items:
                    merged.append(TextChunk("\n\n"))
                for k, it in enumerate(items):
                    merged.append(TextChunk("· " + it, size=14, color=INK))
                    if k != len(items) - 1:
                        merged.append(TextChunk("\n"))
                card = Block(kind="card", chunks=merged, bg=st["bg"], accent=st["accent"],
                             pad_top=14, pad_bottom=14)
                del self.blocks[st["start"]:]
                self.blocks.append(card)
            elif kind in ("section", "closing"):
                # 「小标题」外壳：把竖条颜色补回到标题块上
                title = next((b for b in reversed(self.blocks) if b.kind == "section-title"), None)
                if title is not None:
                    title.kind = kind
                    title.accent = st["accent"]
                    title.pad_top = max(16, _px((st["margin"] or "24px").split()[0], 24))
            elif kind == "img":
                # figure 外壳：src 留在 img 块上，figcaption 的文字并进去当图注
                cap = next((b for b in reversed(self.blocks) if b.kind == "caption"), None)
                if cap is not None and cap.text.strip():
                    self.blocks.append(Block(
                        kind="img",
                        chunks=[TextChunk(cap.text.strip(), size=12, color=cap.chunks[0].color if cap.chunks else INK)],
                        pad_top=max(12, _px((st["margin"] or "20px").split()[0], 20)),
                        pad_bottom=8,
                        src=st["attrs"].get("src", ""),
                        idx=_px(st["attrs"].get("data-idx", "-1"), -1),
                    ))
                    self.blocks.remove(cap)
            return
        margin_px = _px(st["margin"], 0)
        parts = (st["margin"] or "").split()
        top = _px(parts[0], 0) if parts else margin_px
        bottom = _px(parts[0], 0) if len(parts) == 1 else (_px(parts[2], margin_px) if len(parts) >= 3 else margin_px)
        chunks = [c for c in st["chunks"] if c.text.strip()]
        if kind == "img" and not chunks:
            chunks = [TextChunk("")]
        if kind == "figcaption":
            kind = "caption"
        if kind == "li":
            kind = "list"
        if not chunks:
            return
        self.blocks.append(Block(
            kind=kind,
            chunks=chunks,
            pad_top=max(2, top),
            pad_bottom=max(2, bottom),
            bg=st["bg"],
            accent=st["accent"],
            align=(st["style"].get("text-align") or "left").strip(),
            src=st["attrs"].get("src", ""),
            idx=_px(st["attrs"].get("data-idx", "-1"), -1),
        ))

    # ---------- 回调 ----------
    def handle_starttag(self, tag, attrs_list):
        attrs = {k: (v or "") for k, v in attrs_list}
        if tag in self.CONTAINER_SKIP:
            self._skip += 1
            return
        if tag == "br":
            if self._stack:
                self._stack[-1]["chunks"].append(TextChunk("\n"))
            return
        if tag == "img":
            if self._stack:
                self._stack[-1]["attrs"]["src"] = attrs.get("src", "")
            return
        if tag in self.BLOCK_TAGS:
            self._open_block(attrs, _parse_style(attrs.get("style", "")))
            return
        if tag == "span":
            style = _parse_style(attrs.get("style", ""))
            if self._stack:
                self._stack[-1]["spans"].append({
                    "color": _hex(style.get("color", "")),
                    "bold": style.get("font-weight", "") == "bold",
                    "size": _font_size(style) if "font-size" in style else 16,
                })

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.CONTAINER_SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if tag == "span":
            if self._stack and self._stack[-1]["spans"]:
                self._stack[-1]["spans"].pop()
            return
        if tag in self.BLOCK_TAGS:
            self._close_block()

    def handle_data(self, data):
        if self._skip or not self._stack:
            return
        text = data.replace("\u3000", " ")
        if not text.strip():
            return
        st = self._stack[-1]
        span = st["spans"][-1] if st["spans"] else {}
        st["chunks"].append(TextChunk(
            text,
            size=int(span.get("size") or _font_size(st["style"])) or 16,
            bold=bool(span.get("bold")) or st["style"].get("font-weight", "") == "bold",
            color=span.get("color") or st["color"] or INK,
        ))


def parse_preview_blocks(html: str) -> List[Block]:
    p = _HTMLBlocks()
    p.feed(html or "")
    p.close()
    out: List[Block] = []
    for b in p.blocks:
        if b.kind == "card-title":          # 已合并进卡片
            continue
        if not b.text.strip() and b.kind not in ("img", "code"):
            continue
        if b.kind == "list" and out and out[-1].kind == "list":
            out[-1].chunks.append(TextChunk("\u0001" + b.text))   # 用占位符分行，渲染时再拆
            continue
        if b.kind in ("p", "code") and out and out[-1].kind == b.kind and not b.bg:
            out[-1].chunks.extend(b.chunks)   # 相邻正文合并，少一堆小 Label
            continue
        out.append(b)
    return out


# --------------------------------------------------------------------------
# 2) 编辑器文本操作（纯函数式，接收 text + 选区，返回新 text + 新选区）
# --------------------------------------------------------------------------

@dataclass
class Edit:
    text: str
    sel_start: int = 0
    sel_end: int = 0


def wrap_selection(text: str, sel: Tuple[int, int], left: str, right: str,
                   fallback: str = "") -> Edit:
    a, b = sel
    if a == b:
        inner = fallback
        ins = left + inner + right
        return Edit(text[:a] + ins + text[b:], a + len(left), a + len(left) + len(inner))
    return Edit(text[:a] + left + text[a:b] + right + text[b:],
                a + len(left), b + len(left))


def current_line(text: str, pos: int) -> Tuple[int, int]:
    """返回 pos 所在行的 [start, end) 区间（end 不含换行符）。"""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return start, end


def number_heading(text: str, pos: int) -> Edit:
    """把当前行变成「## NN 标题」，编号按文中已有小节自动 +1。"""
    start, end = current_line(text, pos)
    line = text[start:end]
    m = re.match(r"^#{1,4}\s+(\d{1,2})\s*(.*)$", line)
    if m:
        num = int(m.group(1)) + 1
        body = m.group(2).strip()
    else:
        nums = [int(x) for x in re.findall(r"^##\s+(\d{1,2})\s", text, flags=re.M)]
        num = (max(nums) + 1) if nums else 1
        body = line.strip()
    tail = body.strip()
    new_line = f"## {num:02d} {tail}" if tail else f"## {num:02d} "
    new = text[:start] + new_line + text[end:]
    caret = start + 3 + (0 if not tail else 3 + len(f"{num:02d} "))
    return Edit(new, caret, caret)


def listify(text: str, pos: int, bullet: str = "· ") -> Edit:
    """把当前行加上列表符（已带符号则不重复）。"""
    start, end = current_line(text, pos)
    block = text[start:end]
    lines = block.split("\n")
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if re.match(r"^([-*+]|\d{1,2}[.)]|[①②③④⑤⑥⑦⑧⑨⑩])\s*", s):
            out.append(s)
        else:
            out.append(bullet + s)
    new = "\n".join(out)
    return Edit(text[:start] + new + text[end:], start, start + len(new))


INSERT_TEMPLATES = {
    "card": "## 先说结论\n\n> · 结论一，一句话说清发生了什么\n> · 结论二，说清最反常识的细节\n> · 结论三，给读者一个可执行的动作",
    "cta": "[CTA]\n看完这篇，你最大的感受是什么？欢迎在评论区聊聊。",
    "end": "[END]\n**关注「公众号名称」，每天一个新鲜事。**",
    "closing": "## 写在最后\n\n一句收束全文的话，单独成段。",
    "quote": "> 这里放专家原话或金句。",
    "img": "[IMG:图片路径|图片描述|图注：画面里发生了什么。图源：待补]",
}


def insert_block(text: str, pos: int, kind: str) -> Edit:
    """在光标所在行之后插入一个模板块（自动补空行）。"""
    tpl = INSERT_TEMPLATES.get(kind, "")
    if not tpl:
        return Edit(text, pos, pos)
    start, end = current_line(text, pos)
    before = "\n" if start > 0 else ""
    after = "\n"
    ins = before + tpl + after
    new = text[:end] + ins + text[end:]
    caret = end + len(ins) - 1          # 停在模板内容末尾，用户接着写
    return Edit(new, caret, caret)


# --------------------------------------------------------------------------
# 3) 发布前体检
# --------------------------------------------------------------------------

@dataclass
class Issue:
    level: str        # error / warn / info
    title: str
    detail: str = ""
    line: int = -1    # 1 起；-1 表示无定位

    @property
    def icon(self) -> str:
        return {"error": "✖", "warn": "▲", "info": "ℹ"}.get(self.level, "·")


def _line_of(text: str, needle: str) -> int:
    pos = text.find(needle)
    return text.count("\n", 0, pos) + 1 if pos >= 0 else -1


def check_article(text: str, base_dir: str = "") -> List[Issue]:
    issues: List[Issue] = []
    body = text or ""

    # 标题
    title = ""
    title_line = 1
    for i, ln in enumerate(body.split("\n"), 1):
        s = ln.strip()
        if s.startswith("# "):
            title, title_line = s[2:].strip(), i
            break
        if s and not s.startswith(("#", ">", "[", "日期", "作者", "标题")):
            title, title_line = s, i
            break
    if not title:
        issues.append(Issue("error", "缺少标题", "第一行写「# 标题」，或直接把标题写在第一行"))
    else:
        if len(title) > 30:
            issues.append(Issue("warn", "标题偏长", f"当前 {len(title)} 字，建议 ≤30 字：{title}", title_line))
        if title.startswith("# "):
            issues.append(Issue("info", "标题行带了 # 号", "粘贴到公众号前去掉「# 」，后台标题栏单独填", title_line))

    # 结论卡
    if "先说结论" not in body and not re.search(r"^>\s*[·・]", body, flags=re.M):
        issues.append(Issue("warn", "没有「先说结论」卡片",
                            "首屏加 3 行结论：一个小节 + 3 行 > · 列表"))

    # 小节
    secs = re.findall(r"^(#{2,4})\s+(\d{0,2})\s*(.+)$", body, flags=re.M)
    if len(secs) < 2:
        issues.append(Issue("warn", "小节数量偏少", f"当前 {len(secs)} 个；长文建议 3–5 个小节"))
    nums = [s[1] for s in secs if s[1]]
    for d in sorted({n for n in nums if nums.count(n) > 1}):
        issues.append(Issue("warn", f"小节编号重复：{d}", "编号重复会让读者以为漏读",
                            _line_of(body, f"## {d}")))

    # 图片
    for m in re.finditer(r"\[IMG:([^\]]*)\]", body):
        parts = [p.strip() for p in m.group(1).split("|")]
        path = parts[0]
        line = body.count("\n", 0, m.start()) + 1
        if path and base_dir and not os.path.isabs(path):
            if not os.path.exists(os.path.normpath(os.path.join(base_dir, path))):
                issues.append(Issue("error", "图片文件找不到", f"{path}（相对 {base_dir}）", line))
        if len(parts) < 3 or not parts[2]:
            issues.append(Issue("warn", "图片缺图注", "信息图下面补一行「▲ 说明。图源：XXX」", line))
        elif len(parts[2]) < 10 and "图源" not in parts[2]:
            issues.append(Issue("info", "图注偏短", f"「{parts[2]}」建议写清画面和来源", line))

    if "画面说明：谁、在做什么、证明了什么" in body:
        issues.append(Issue("warn", "有未填写的图注占位", "把「▲ 画面说明…」替换成真实图注",
                            _line_of(body, "画面说明：谁、在做什么、证明了什么")))

    # 段落长度
    in_comment = False
    for i, ln in enumerate(body.split("\n"), 1):
        s = ln.strip()
        if s.startswith("<!--"):
            in_comment = not s.endswith("-->")
            continue
        if in_comment:
            if s.endswith("-->"):
                in_comment = False
            continue
        if not s or s[0] in "#>-[!]" or s.startswith(("日期", "作者", "标题")):
            continue
        if len(s) > 90:
            issues.append(Issue("info", f"第 {i} 行段落偏长", f"{len(s)} 字，建议在 3 行（≈55 字）内断开", i))

    # 分隔线
    dashes = len(re.findall(r"^—{2,}\s*$", body, flags=re.M)) + len(re.findall(r"^---\s*$", body, flags=re.M))
    if dashes > 2:
        issues.append(Issue("warn", f"分隔线 {dashes} 条偏多", "正文里最多留 2 条，章节靠间距分组"))

    # 结尾
    if "[CTA]" not in body and "评论区" not in body:
        issues.append(Issue("warn", "没有互动提问", "文末加一句提问（[CTA] 或直接写一句）"))
    if "[END]" not in body and "关注" not in body[-200:]:
        issues.append(Issue("info", "没有关注引导", "文末加 [END] 或一句关注引导"))
    if body.count("关注") > 3:
        issues.append(Issue("info", "「关注」出现次数偏多", "同一屏说三遍关注，读者会跳过"))

    if len(re.sub(r"\s", "", body)) < 20:
        issues.append(Issue("error", "正文几乎是空的", "先写正文再来体检"))

    return issues


# --------------------------------------------------------------------------
# 4) 图片入库
# --------------------------------------------------------------------------

IMG_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")


def next_image_name(folder: str, ext: str, section: str = "") -> str:
    os.makedirs(folder, exist_ok=True)
    nums = []
    for f in os.listdir(folder):
        m = re.match(r"^(\d{2})-", f)
        if m:
            nums.append(int(m.group(1)))
    nxt = (max(nums) + 1) if nums else 1
    base = f"{nxt:02d}" + (f"-{section}" if section else "")
    candidate = f"{base}{ext.lower()}"
    k = 2
    while os.path.exists(os.path.join(folder, candidate)):
        candidate = f"{base}-{k}{ext.lower()}"
        k += 1
    return candidate


def import_image(src: str, folder: str, section: str = "") -> str:
    """把图片复制到 imgs 目录，返回文件名。"""
    ext = os.path.splitext(src)[1].lower() or ".jpg"
    name = next_image_name(folder, ext, section)
    shutil.copyfile(src, os.path.join(folder, name))
    return name


def build_img_marker(path: str, alt: str = "", caption: str = "", source: str = "") -> str:
    parts = [path, alt, caption, source]
    while len(parts) > 1 and not parts[-1]:
        parts.pop()
    return "[IMG:" + "|".join(parts) + "]"


def split_marker(marker_body: str) -> Tuple[str, str, str, str]:
    parts = [p.strip() for p in (marker_body or "").split("|")]
    path = parts[0] if parts else ""
    alt = parts[1] if len(parts) > 1 else ""
    caption = parts[2] if len(parts) > 2 else ""
    source = parts[3] if len(parts) > 3 else ""
    if caption and not source and re.search(r"(图源|来源|摄影|出处|©)", caption):
        source, caption = caption, ""
    return path, alt, caption, source


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}GB"
