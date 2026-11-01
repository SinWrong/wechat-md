#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wechat_md.py —— 公众号排版模板生成器（Markdown 版）

把「文案 + 图片」变成一份符合公众号阅读规范的 Markdown 模板，
并可选生成可直接粘贴进公众号后台的 HTML（内联样式）。

用法
----
1) 最简：文案里用 [IMG:...] 标图，程序自动排版
   python wechat_md.py 文案.md -o 输出.md --html 输出.html

2) 图文分离：图片单独放一个文件夹，按文件名序号自动分配章节
   python wechat_md.py 文案.txt --images ./图 -o 输出.md

3) 指定主题 / 摘要卡 / 预览页
   python wechat_md.py 文案.md --theme news --summary --preview 预览.html

输入格式（三种混用都行）
------------------------
# 标题                 ← 一级标题=文章标题（没有就用第一行）
> 摘要：一句话           ← 结论卡 / 导语
## 01 小节标题          ← 章节；也认 "01 "、"一、"、"## "、"### "
正文段落……              ← 空行分段；单换行自动合并
- 列表项               ← 会输出成 ①②③ 项目符号
> 这是引用             ← 引用块（专家原话 / 金句）
[IMG:图1.jpg|画面说明|图源：xxx]      ← 图片（alt|说明|来源都可省）
[IMG: ./图/01.jpg]
[CTA]                  ← 互动提问位（可选，不写会自动生成）
[END]                  ← 关注引导位（可选）

主题
----
business（默认，商务蓝） news（新闻红） warm（暖橙）

输出
----
- 一份 .md：带 YAML 头信息、排版规范、逐节可替换的模板正文、发布前清单
- 可选 .html：内联样式，浏览器打开全选复制 → 公众号后台直接粘贴
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# 主题：所有尺寸/颜色集中在这里，换主题只改一处
# --------------------------------------------------------------------------

THEMES: Dict[str, Dict[str, str]] = {
    "business": {
        "label": "商务蓝",
        "primary": "#2F6FD0",
        "primary_soft": "#EAF1FC",
        "text": "#333333",
        "strong": "#1A1A1A",
        "muted": "#888888",
        "meta": "#999999",
        "line": "#E5E5E5",
        "quote_bg": "#F7F8FA",
        "quote_line": "#D9DEE6",
        "quote_text": "#555555",
        "letter_spacing": "0.3",
        "heading_style": "bar",
        "code_bg": "#1F2937",
        "code_text": "#E5E7EB",
        "tip": "适合：资讯、解读、行业观察",
    },
    "news": {
        "label": "新闻红",
        "primary": "#C0302F",
        "primary_soft": "#FBEDED",
        "text": "#333333",
        "strong": "#1A1A1A",
        "muted": "#888888",
        "meta": "#999999",
        "line": "#E5E5E5",
        "quote_bg": "#FAF7F5",
        "quote_line": "#E0D5CE",
        "quote_text": "#555555",
        "letter_spacing": "0.2",
        "heading_style": "underline",
        "code_bg": "#1F2937",
        "code_text": "#E5E7EB",
        "tip": "适合：热点、社会新闻、事件复盘",
    },
    "warm": {
        "label": "暖橙",
        "primary": "#C96A1E",
        "primary_soft": "#FDF0E4",
        "text": "#3A3330",
        "strong": "#241F1C",
        "muted": "#887F7A",
        "meta": "#9C928C",
        "line": "#EEE6E0",
        "quote_bg": "#FAF6F2",
        "quote_line": "#E4D8CD",
        "quote_text": "#5A514C",
        "letter_spacing": "0.5",
        "heading_style": "bar",
        "code_bg": "#3A3330",
        "code_text": "#F5EFE8",
        "tip": "适合：生活、故事、情感、科普",
    },
}

TYPE_LABELS = {
    "summary": "先说结论",
    "quote": "引用",
    "steps": "步骤",
    "tip": "提醒",
    "points": "要点",
    "body": "正文",
}

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

# 文案里出现这些词，自动把该节标成摘要/步骤/提醒，决定用哪种视觉组件
TYPE_HINTS: List[Tuple[str, Tuple[str, ...]]] = [
    ("summary", ("先说结论", "结论", "摘要", "导语", "一句话说清", "划重点", "看点", "亮点")),
    ("steps", ("步骤", "怎么做", "三步", "操作", "流程", "方法", "攻略", "清单")),
    ("tip", ("提醒", "注意", "切记", "千万", "建议", "避坑", "误区")),
]

SECTION_RE = re.compile(
    r"^(?:#{1,4}\s+)?"                    # markdown 标题符
    r"(?:"
    r"(?P<num>\d{1,2})\s*[.、|｜:：]\s*"    # 01  xxx / 01|xxx
    r"|(?P<cn>[一二三四五六七八九十]{1,2})\s*[、.．]\s*"  # 一、xxx
    r"|第\s*(?P<di>\d{1,2})\s*[节章部分]\s*"
    r")?"
    r"(?P<title>.+)$"
)

IMG_RE = re.compile(r"^\[IMG(?::(?P<body>[^\]]*))?\]$", re.IGNORECASE)
CMD_RE = re.compile(r"^\[(?:CTA|END|关注|互动)\]$", re.IGNORECASE)

META_RE = re.compile(r"^[#>\s*]*" + "|".join([
    r"标题", r"副标题", r"摘要", r"导语", r"作者", r"日期", r"字数", r"分类", r"标签", r"主题",
]) + r"\s*[:：]\s*")


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------

@dataclass
class Image:
    path: str = ""
    alt: str = ""
    caption: str = ""
    source: str = ""

    def caption_text(self) -> str:
        parts = [p for p in (self.caption, self.source) if p]
        return "　".join(parts)


@dataclass
class Block:
    kind: str                       # p / img / quote / list / summary / steps / tip / cta / end
    text: str = ""
    items: List[str] = field(default_factory=list)
    image: Optional[Image] = None


@dataclass
class Section:
    number: str = ""
    title: str = ""
    kind: str = "body"              # body / summary / steps / tip
    blocks: List[Block] = field(default_factory=list)


@dataclass
class Article:
    title: str = ""
    lead: List[Block] = field(default_factory=list)   # 标题与第一个小节之间
    sections: List[Section] = field(default_factory=list)
    closing: List[Block] = field(default_factory=list)  # 「写在最后」等收尾段
    cta: Optional[str] = None
    cta_blocks: List[Block] = field(default_factory=list)   # [CTA] 后用户写的提问
    end: bool = False
    end_blocks: List[Block] = field(default_factory=list)   # [END] 后用户写的关注引导
    meta: Dict[str, str] = field(default_factory=dict)
    images: List[Image] = field(default_factory=list)

    def cta_text(self) -> str:
        return "".join(b.text for b in self.cta_blocks if b.kind == "p" and b.text).strip()

    def end_text(self) -> str:
        return "".join(b.text for b in self.end_blocks if b.kind == "p" and b.text).strip()

    # ---- 统计 ----
    def all_blocks(self) -> List[Block]:
        out = list(self.lead)
        for s in self.sections:
            out.extend(s.blocks)
        out.extend(self.closing)
        out.extend(self.cta_blocks)
        out.extend(self.end_blocks)
        return out

    def plain_text(self) -> str:
        chunks: List[str] = []
        for b in self.all_blocks():
            if b.text:
                chunks.append(b.text)
            chunks.extend(b.items)
            if b.kind == "cta":
                chunks.append(b.text)
        return "".join(chunks)

    def char_count(self) -> int:
        return len(re.findall(r"[\u4e00-\u9fff0-9A-Za-z]", self.plain_text()))

    def read_minutes(self) -> int:
        return max(1, round(self.char_count() / 350 + 0.2))


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------

def _clean(line: str) -> str:
    return line.replace("\u3000", " ").strip()


def _is_meta_line(line: str) -> bool:
    return bool(META_RE.match(line)) and len(line) <= 40


CLOSING_RE = re.compile(r"^(写在最后|最后|结语|结尾|尾声|总结|小结|撸一句|END)$", re.IGNORECASE)
SUMMARY_RE = re.compile(r"^(先说结论|结论|摘要|划重点|看点|亮点|导读)$")


def is_summary_section(title: str) -> bool:
    return bool(SUMMARY_RE.match((title or "").strip()))


def _eval_heading(s: str) -> Optional[Tuple[str, str]]:
    """规则 3 的判定：无编号短句是否当标题。"""
    if CLOSING_RE.match(s):
        return "", s
    if len(s) <= 16 and s[-1] not in "。！？；，,.、：" and "：" not in s and "|" not in s:
        return "", s
    return None


def _guess_section(line: str) -> Optional[Tuple[str, str]]:
    """判断一行是不是小节标题，返回 (编号, 标题)。编号可能为空字符串。"""
    s = _clean(line)
    if not s or len(s) > 40:
        return None
    s = s.lstrip(">").strip()
    if CLOSING_RE.match(s):
        return "", s

    # 优先级 1：markdown 标题符（## 及以上，短句也算标题）
    m = re.match(r"^(#{1,4})\s+(.*)$", s)
    if m:
        inner = m.group(2).strip()
        if len(m.group(1)) <= 2:
            m2 = re.match(r"^(\d{1,2})\s*[.、|｜:：]?\s+(.+)$", inner)
            if m2:
                return m2.group(1).zfill(2), m2.group(2).strip()
            m3 = re.match(r"^([一二三四五六七八九十]{1,2})\s*[、.．]\s*(.+)$", inner)
            if m3:
                return str(_cn_num(m3.group(1))).zfill(2), m3.group(2).strip()
            if len(inner) <= 40 and inner[-1] not in "。！？；，,":
                return "", inner
            return _eval_heading(inner)

    # 优先级 2：数字 / 中文数字 / 第 N 节（必须带分隔符）
    m = re.match(r"^(\d{1,2})\s*[.、|｜:：]\s*(.+)$", s)
    if m:
        return m.group(1).zfill(2), m.group(2).strip()

    m = re.match(r"^([一二三四五六七八九十]{1,2})\s*[、.．]\s*(.+)$", s)
    if m:
        return str(_cn_num(m.group(1))).zfill(2), m.group(2).strip()

    m = re.match(r"^第\s*(\d{1,2})\s*[节章部分]\s*[:：]?\s*(.*)$", s)
    if m:
        return m.group(1).zfill(2), m.group(2).strip()

    # 优先级 3：无编号短句
    return _eval_heading(s)


def _cn_num(s: str) -> int:
    """一~九十九 的中文数字转 int；转不了返回 0。"""
    digits = "零一二三四五六七八九"
    if not s:
        return 0
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + digits.index(s[1]) if len(s) > 1 and s[1] in digits else 10
    if s.endswith("十"):
        return digits.index(s[0]) * 10 if s[0] in digits else 0
    if "十" in s:
        a, _, b = s.partition("十")
        return digits.index(a) * 10 + (digits.index(b) if b in digits else 0)
    return digits.index(s[0]) if len(s) == 1 and s[0] in digits else 0


def _infer_kind(title: str) -> str:
    for kind, words in TYPE_HINTS:
        if any(w in title for w in words):
            return kind
    return "body"


def _parse_image(body: str, base_dir: str) -> Image:
    body = (body or "").strip()
    if not body:
        return Image()
    parts = [p.strip() for p in body.split("|")]
    path = parts[0]
    caption = parts[2] if len(parts) > 2 else ""
    source = parts[3] if len(parts) > 3 else ""
    # 只写了三段时，第三段若同时含「说明 + 图源」，从「图源：」处拆开，
    # 前半句留给图注，后半句作来源，避免整条说明被吞掉
    if caption and not source and re.search(r"(图源|来源|摄影|出处|©)", caption):
        m = re.search(r"(图源|来源|摄影|出处)\s*[:：]\s*", caption)
        if m:
            head = caption[:m.start()].strip("　 ：:，,")
            source, caption = caption[m.start():].strip(), head
        else:
            source, caption = caption, ""
    img = Image(
        path=path,
        alt=parts[1] if len(parts) > 1 else "",
        caption=caption,
        source=source,
    )
    if path and not os.path.isabs(path):
        candidate = os.path.normpath(os.path.join(base_dir, path))
        if os.path.exists(candidate):
            img.path = candidate
    return img


def parse_content(raw: str, base_dir: str = ".") -> Article:
    """解析文案。内部先做一次模板清洗（注释/附录/Markdown 图片），
    这样「源文案」和「本程序生成后的模板」都能直接喂进来。"""
    raw = prepare_markdown(raw)
    art = Article()
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    cur_section: Optional[Section] = None
    closing = False
    redirect = ""                    # "" / "closing" / "cta" / "end"
    pending: List[str] = []          # 待合并成一段的连续行
    list_buf: List[str] = []
    quote_buf: List[str] = []

    def target() -> List[Block]:
        if redirect == "closing":
            return art.closing
        if redirect == "cta":
            return art.cta_blocks
        if redirect == "end":
            return art.end_blocks
        return cur_section.blocks if cur_section is not None else art.lead

    def flush_para():
        nonlocal pending
        text = "".join(p.strip() for p in pending if p.strip())
        pending = []
        if text:
            target().append(Block("p", text=text))

    def flush_list():
        nonlocal list_buf
        if list_buf:
            target().append(Block("list", items=list_buf[:]))
            list_buf = []

    def flush_quote():
        nonlocal quote_buf
        if quote_buf:
            # 以「· 」「1. 」「①」开头的引用行，拆成列表项；
            # 注意只吃掉一个前缀字符，别把 **加粗** 的星号也删了
            BULLET_ONE = re.compile(r"^(?:[·・]|\d{1,2}[.)]|[①②③④⑤⑥⑦⑧⑨⑩]|\*(?!\*))\s*")
            lines = [ln.strip() for ln in quote_buf if ln.strip()]
            # 列表项要求「整行以列表符开头」，避免 **先说结论** 这种加粗行被算进去
            bulleted = [ln for ln in lines if BULLET_ONE.match(ln) and not ln.startswith("**")]
            if bulleted and len(bulleted) == len(lines):
                items = [BULLET_ONE.sub("", ln, count=1).strip() for ln in lines]
                target().append(Block("list", items=items))
            elif len(bulleted) == len(lines) - 1 and re.match(r"^\*\*\s*(先说结论|结论|摘要)\s*\*\*$", lines[0]):
                # 「**先说结论** + · 列表」→ 结论卡（模板/旧版常见写法）
                items = [BULLET_ONE.sub("", ln, count=1).strip() for ln in lines[1:]]
                # 结论卡永远放文首：插到 lead 最前面（若当前不在 lead 就插到目标段最前）
                blk = Block("summary", items=items)
                if target() is art.lead:
                    art.lead.insert(0, blk)
                else:
                    target().append(blk)
            else:
                target().append(Block("quote", text="".join(quote_buf)))
            quote_buf = []

    def flush_all():
        flush_para()
        flush_list()
        flush_quote()

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = _clean(raw_line)
        i += 1

        if not line:
            flush_all()
            continue

        # ---- 围栏代码块 ----
        if line.startswith("```"):
            flush_all()
            lang = line[3:].strip()
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i].rstrip("\n"))
                i += 1
            if i < len(lines):
                i += 1                      # 吃掉结束围栏
            target().append(Block("code", text="\n".join(code_lines), items=[lang]))
            continue

        # ---- 图片 ----
        m = IMG_RE.match(line)
        if m:
            flush_all()
            img = _parse_image(m.group("body") or "", base_dir)
            art.images.append(img)
            target().append(Block("img", image=img))
            continue

        # ---- CTA / END 标记 ----
        if CMD_RE.match(line):
            flush_all()
            if "CTA" in line.upper() or "互动" in line:
                art.cta = ""          # 占位，稍后生成
                redirect = "cta"
            else:
                art.end = True
                redirect = "end"
            continue

        # ---- 文章标题 ----
        if line.startswith("# ") and not art.title and cur_section is None and not closing:
            art.title = line[2:].strip()
            continue

        # ---- 元信息（作者/日期/分类 等）----
        if _is_meta_line(line) and cur_section is None and not closing:
            mm = re.match(r"^\**\s*(标题|副标题|摘要|导语|作者|日期|字数|分类|标签|主题)\s*[:：]\s*(.*)$", line)
            if mm:
                art.meta[mm.group(1)] = mm.group(2).strip()
                continue

        # ---- 引用（必须在"小节标题"判断前，避免 > 开头被误判）----
        if line.startswith(">"):
            flush_para()
            flush_list()
            quote_buf.append(_clean(line[1:]))
            continue
        flush_quote()

        # ---- 列表（必须在标题判断前，否则 "- 别堵..." 会被当成小节）----
        # 认 - * + / 1. / ①–⑩ / ·  这几种前缀
        LIST_MARK = r"^(?:[-*+]|\d{1,2}[.)]|[①②③④⑤⑥⑦⑧⑨⑩]|·)\s+"
        if re.match(LIST_MARK, line):
            flush_para()
            list_buf.append(re.sub(LIST_MARK, "", line).strip())
            continue
        flush_list()

        # ---- 小节 / 收尾 ----
        sec = _guess_section(line)
        if sec:
            num, title = sec
            if CLOSING_RE.match(title):
                flush_all()
                cur_section = None
                closing = True
                redirect = "closing"
                continue
            if redirect in ("cta", "end"):
                # [CTA]/[END] 之后的小标题文本，作为互动/引导的正文
                pending.append(line)
                continue
            if redirect == "closing":
                # 「写在最后」之后不再开新小节
                pending.append(line)
                continue
            # 「先说结论 / 摘要」这类小节 → 结论卡，而不是新章节
            if is_summary_section(title):
                flush_all()
                cur_section = Section(number="", title=title, kind="summary")
                art.sections.append(cur_section)
                continue
            flush_all()
            if not art.title:
                art.title = title
                continue
            cur_section = Section(number=num, title=title, kind=_infer_kind(title))
            art.sections.append(cur_section)
            continue

        # ---- 普通段落 ----
        if pending and pending[-1].endswith(("。", "！", "？", "…", "”")):
            flush_para()
        pending.append(line)

    flush_all()
    return art


def guess_title(raw: str) -> str:
    for line in raw.split("\n"):
        s = _clean(line)
        if s and not s.startswith(("[", ">", "#")):
            return s[:40]
    return "未命名文章"


# --------------------------------------------------------------------------
# 图片分配：按文件名序号 → 章节序号；否则均分到各章节
# --------------------------------------------------------------------------

def collect_images(folder: str) -> List[Image]:
    if not folder or not os.path.isdir(folder):
        return []
    exts = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(exts))
    out: List[Image] = []
    for f in files:
        stem = os.path.splitext(f)[0]
        caption = re.sub(r"^[\d_\-\s]+", "", stem)
        caption = re.sub(r"(?i)(封面|配图|图片|截图|img|image|photo|\d{2,4}[x×]\d{2,4})", " ", caption)
        caption = re.sub(r"[\-_]+", " ", caption).strip()
        # 中文之间不要把空格留下（"监控 黑熊" → "监控黑熊"）
        caption = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", caption)
        out.append(Image(path=os.path.join(folder, f), caption=caption))
    return out


def assign_images(art: Article, pool: Sequence[Image]) -> None:
    """把图片池里的图按序号分给各章节；不足的章节留空占位。"""
    if not pool:
        return
    usage: List[Image] = []
    for sec in art.sections:
        # 已手动插图，跳过
        if any(b.kind == "img" for b in sec.blocks):
            continue
        matched = None
        for img in pool:
            stem = os.path.basename(img.path)
            num = re.match(r"^(\d{1,2})", stem)
            if num and sec.number and num.group(1).zfill(2) == sec.number:
                matched = img
                break
        if matched:
            sec.blocks.append(Block("img", image=matched))
            usage.append(matched)
    # 其余图片均分到还没图的章节
    rest = [p for p in pool if p not in usage]
    empty = [s for s in art.sections if not any(b.kind == "img" for b in s.blocks)]
    for idx, sec in enumerate(empty):
        if not rest:
            break
        sec.blocks.append(Block("img", image=rest[idx % len(rest)]))
    for s in art.sections:
        for b in s.blocks:
            if b.kind == "img" and b.image:
                art.images.append(b.image)
    # 去重（保留首次出现顺序）
    seen, uniq = set(), []
    for img in art.images:
        key = id(img)
        if key not in seen:
            seen.add(key)
            uniq.append(img)
    art.images = uniq


# --------------------------------------------------------------------------
# 结构补全：摘要卡 / CTA / END / 空章节
# --------------------------------------------------------------------------

def _elide(s: str, limit: int = 26) -> str:
    """结论卡单行不超过 limit 字；过长时在最近的分句处收口，不留半个词。"""
    if len(s) <= limit:
        return s
    cut = s[:limit]
    for sep in ("，", "；", "：", "、", "——", " "):
        pos = cut.rfind(sep)
        if pos >= 8:
            return cut[:pos] + "…"
    return cut + "…"


def normalize(art: Article, want_summary: bool = False,
              want_cta: bool = True, want_end: bool = True) -> None:
    # 摘要：把小节或导语转成结论卡
    if not art.sections and not art.lead:
        raise SystemExit("没有解析到任何内容，请检查输入文件。")

    if want_summary:
        user_summary = next((s for s in art.sections if s.kind == "summary"), None)
        has_lead_summary = any(b.kind == "summary" for b in art.lead)
        if user_summary and not user_summary.blocks:
            # 写了「先说结论」小标题但还没填 → 给 3 个占位
            art.lead.insert(0, Block("summary", items=[
                "结论一：一句话说清发生了什么",
                "结论二：说清最反常识的细节",
                "结论三：给读者一个可执行的动作",
            ]))
            art.sections.remove(user_summary)
        elif user_summary:
            items: List[str] = []
            for b in user_summary.blocks:
                if b.kind in ("p", "quote") and b.text:
                    for sent in re.split(r"(?<=[。！？；])", b.text):
                        s = sent.strip().lstrip("·・-* ").rstrip("。；，")
                        if s:
                            items.append(s)
                        if len(items) >= 3:
                            break
                elif b.kind == "list":
                    items.extend(b.items)
                if len(items) >= 3:
                    break
            art.lead.insert(0, Block("summary", items=[_elide(t) for t in items[:3]]))
            art.sections.remove(user_summary)
        elif not has_lead_summary:
            from_lead = bool(art.lead)
            src: List[Block] = list(art.lead) if from_lead else list(art.sections[0].blocks)
            paras = [b.text for b in src if b.kind == "p" and b.text]
            items = []
            if paras and all(len(p) <= 40 for p in paras) and len(paras) >= 2:
                items = [p for p in paras[:3]]
            else:
                for p in paras:
                    for sent in re.split(r"(?<=[。！？；])", p):
                        s = sent.strip().rstrip("。；，")
                        if not s:
                            continue
                        if len(s) > 34:
                            head = re.split(r"[，：,——]", s)[0].strip()
                            s = (head if 8 <= len(head) <= 34 else s)
                        items.append(s)
                        if len(items) >= 3:
                            break
                    if len(items) >= 3:
                        break
            drop = set(id(b) for b in src if b.kind == "p")
            if from_lead:
                art.lead = [b for b in art.lead if id(b) not in drop]
            else:
                art.sections[0].blocks = [b for b in art.sections[0].blocks if id(b) not in drop]
            if items:
                art.lead.insert(0, Block("summary", items=[_elide(t) for t in items[:3]]))

    # 编号：统一重新编号，避免抽走内容后出现 02 开头
    art.sections = [s for s in art.sections
                    if s.kind == "summary" or any(b.kind == "img" or (b.text or "").strip()
                                                  or b.items for b in s.blocks)]
    for idx, sec in enumerate(art.sections, 1):
        sec.number = f"{idx:02d}"

    # 空章节
    if not art.sections:
        art.sections.append(Section(number="01", title="第一部分", kind="body",
                                    blocks=[Block("p", text="")]))

    if want_cta and art.cta == "":
        art.cta = "看完这篇，你最大的感受是什么？欢迎在评论区聊聊。"
    if want_end:
        art.end = True


# --------------------------------------------------------------------------
# Markdown 渲染
# --------------------------------------------------------------------------

def _md_image_block(img: Image, fallback: str = "配图") -> str:
    if img and img.path:
        alt = img.alt or img.caption or fallback
        return f"![{alt}]({img.path.replace(os.sep, '/')})"
    return f"![{fallback}](图片路径：待补，建议 1080×608 / 16:9)"


def _md_caption(img: Optional[Image]) -> str:
    if img and img.caption_text():
        return f"> {img.caption_text()}"
    return "> ▲ 画面说明：谁、在做什么、证明了什么　图源：待补"


def render_markdown(art: Article, theme_name: str, theme: Dict[str, str],
                    title_override: str = "", summary_flag: bool = True) -> str:
    title = title_override or art.title or "未命名文章"
    date = art.meta.get("日期") or _dt.date.today().isoformat()
    words, minutes = art.char_count(), art.read_minutes()
    theme_label = f"{theme_name}（{theme['label']}）"

    out: List[str] = []
    add = out.append

    add(f"# {title}")
    add("")
    add("<!--")
    add(f"  模板说明（粘贴到公众号时请整段删除注释）：")
    add(f"  · 主题：{theme_label}　主色 {theme['primary']}　正文 {theme['text']}　行高 1.75")
    add(f"  · 全文约 {words} 字，预计阅读 {minutes} 分钟")
    add(f"  · 每一节都按「小标题 → 正文 → 配图 → 图注」排列；正文单段 ≤ 3 行（≈55 字）")
    add(f"  · 加粗只给「事实/结论」，全文 ≤5 处；行动建议用主色，不用斜体")
    add("-->")
    add("")
    add(f"> {date}　·　全文约 {words} 字　·　约 {minutes} 分钟")
    add("")

    # ---------- 导语 / 结论卡 ----------
    lead = [b for b in art.lead]
    summary_block = next((b for b in lead if b.kind == "summary"), None)
    if summary_flag and summary_block and summary_block.items:
        add(f"> **先说结论**")
        add(">")
        for it in summary_block.items:
            add(f"> · {it}")
        add("")
        lead = [b for b in lead if b is not summary_block]
    elif summary_flag:
        add("> **先说结论**")
        add(">")
        add("> · 结论一：一句话说清发生了什么")
        add("> · 结论二：说清最反常识的细节")
        add("> · 结论三：给读者一个可执行的动作")
        add("")

    for b in lead:
        if b.kind == "p":
            add(b.text)
            add("")
        elif b.kind == "img":
            add(_md_image_block(b.image))
            add("")
            add(_md_caption(b.image))
            add("")
        elif b.kind == "code":
            add("```" + (b.items[0] if b.items else ""))
            add(b.text)
            add("```")
            add("")

    # ---------- 各小节 ----------
    placeholder_used = False
    for sec in art.sections:
        if sec.kind == "summary":
            # 结论卡：内容已提到文首，这里不再出小标题
            continue
        heading = f"{sec.number} {sec.title}".strip() if sec.number else sec.title
        add(f"## {heading}")
        add("")
        if sec.kind in ("steps", "tip", "points"):
            add(f"<!-- 本节类型：{TYPE_LABELS.get(sec.kind, sec.kind)}，"
                f"输出时用{'①②③ 列表' if sec.kind == 'steps' else '浅底提示块'} -->")
            add("")

        img_done = False
        list_idx = 0
        for b in sec.blocks:
            if b.kind == "p":
                add(b.text if b.text else "（在这里写这一节的正文。建议单段不超过 3 行，超过就在分号或破折号处拆成两段。）")
                add("")
            elif b.kind == "list":
                for k, item in enumerate(b.items):
                    mark = CIRCLED[list_idx % len(CIRCLED)]
                    list_idx += 1
                    add(f"{mark} {item}")
                add("")
            elif b.kind == "quote":
                for qline in b.text.split("\n"):
                    add(f"> {qline}")
                add("")
            elif b.kind == "img":
                add(_md_image_block(b.image))
                add("")
                add(_md_caption(b.image))
                add("")
                img_done = True
            elif b.kind == "code":
                add("```" + (b.items[0] if b.items else ""))
                add(b.text)
                add("```")
                add("")
        if not img_done:
            if placeholder_used:
                add("<!-- 本节建议配 1 张图（16:9 或 4:3）；图片放这里，图下定跟一行图注 -->")
                add("")
            else:
                placeholder_used = True
                add("<!-- 本节建议配 1 张图：16:9（1080×608）或 4:3；图下必须跟一行图注 -->")
                add(_md_image_block(Image(), "本节配图"))
                add("")
                add("> ▲ 画面说明：谁、在做什么、证明了什么　图源：待补")
                add("")

    # ---------- 结尾 ----------
    add("---")
    add("")
    add("## 写在最后")
    add("")
    if art.closing:
        for b in art.closing:
            if b.kind == "p":
                add(b.text)
                add("")
            elif b.kind == "list":
                for k, item in enumerate(b.items):
                    add(f"{CIRCLED[k % len(CIRCLED)]} {item}")
                add("")
            elif b.kind == "quote":
                add(f"> {b.text}")
                add("")
            elif b.kind == "img":
                add(_md_image_block(b.image))
                add("")
                add(_md_caption(b.image))
                add("")
    else:
        add("（一句收束全文的金句，单独成段，可以用「主色加粗」。宁可短，不要凑。）")
        add("")
    if art.cta is not None:
        add("**互动提问**")
        add("")
        add(art.cta_text() or "你觉得呢？欢迎在评论区聊聊。")
        add("")
    if art.end:
        add("<!-- 关注引导：图片 + 两行文字，二选一，不要图文重复 -->")
        add("")
        add(art.end_text() or "**关注「公众号名称」，每天一个新鲜事。**")
        add("")
        if not art.end_text():
            add("不花钱、不扣钱，只占你 3 分钟。")
            add("")

    add("---")
    add("")
    add("<!-- 以下为排版规范与自检，发布前整段删除 -->")
    add("")
    add(f"## 附：排版规范（{theme['label']}）")
    add("")
    add("| 元素 | 参数 | 本模板取值 |")
    add("| --- | --- | --- |")
    add(f"| 主色 | 标题编号 / 行动建议 / 链接 | `{theme['primary']}` |")
    add(f"| 主色浅底 | 结论卡 / 收束卡 | `{theme['primary_soft']}` |")
    add(f"| 正文字号 | 移动端舒适区 15–17px | 16px |")
    add(f"| 行高 | 中文方块字建议 ≥1.7 | 1.75 |")
    add(f"| 段距 | 段间留白，不用空行硬撑 | 16px |")
    add("| 缩进 | 不缩进、左对齐（禁两端对齐） | 0 |")
    add("| 小标题 | 只比正文大 1–2 档 | 17–18px 加粗 |")
    add("| 图注 | 12px 灰色居中，紧贴图下 | `#888` |")
    add("| 编号 | 数字与单位间加半角空格 | `5 小时` |")
    add("")
    add("## 附：发布前自检")
    add("")
    for item in [
        "标题 ≤ 30 字，且不在标题/首段重复同一个数字",
        "首屏有「先说结论」或导语，3 行以内",
        "每个小标题 ≤ 20 字，左对齐，字号只比正文大 1–2 档",
        "正文 16px / 行高 1.75 / 段后 16px，没有 text-indent",
        "单段 ≤ 3 行（约 55 字），超长的已拆",
        "加粗 ≤ 5 处，且都是事实/结论",
        "分隔线 ≤ 2 条，章节靠间距分组",
        "每张信息图都有「▲ 说明 + 图源」",
        "文末只有「一句收束 + 一个互动 + 一次关注引导」",
        "手机预览：每屏至少一个视觉锚点（小标题/图/卡片/加粗句）",
    ]:
        add(f"- [ ] {item}")
    add("")
    return "\n".join(out)


# --------------------------------------------------------------------------
# HTML 渲染（可直接粘贴公众号）
# --------------------------------------------------------------------------

def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _rich(text: str) -> str:
    """行内格式：**加粗**、`行内代码`、[文字](链接)。其余按纯文本转义。"""
    import html as _html
    out: List[str] = []
    pattern = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))", re.S)
    pos = 0
    for m in pattern.finditer(text or ""):
        out.append(_html.escape(text[pos:m.start()], quote=False))
        token = m.group(0)
        if token.startswith("**"):
            out.append("<strong>" + _html.escape(token[2:-2], quote=False) + "</strong>")
        elif token.startswith("`"):
            out.append('<code style="background: #F2F4F7; border-radius: 3px; padding: 1px 4px; '
                       'font-size: 0.92em;">' + _html.escape(token[1:-1], quote=False) + "</code>")
        else:
            label, url = re.match(r"\[([^\]]+)\]\(([^)\s]+)\)", token).groups()
            out.append('<a href="' + _html.escape(url, quote=True) + '" style="color: inherit; '
                       'text-decoration: underline;">' + _html.escape(label, quote=False) + "</a>")
        pos = m.end()
    out.append(_html.escape(text[pos:], quote=False))
    return "".join(out)


def _h_p(text: str, t: Dict[str, str], strong: bool = False, color: str = "",
         kind: str = "p") -> str:
    weight = "bold" if strong else "normal"
    col = color or (t["strong"] if strong else t["text"])
    return (f'<p data-b="{kind}" style="margin: 0 0 16px; font-size: 16px; line-height: 1.75; '
            f'letter-spacing: {t.get("letter_spacing", "0.3")}px; word-break: break-word; '
            f'overflow-wrap: break-word; '
            f'color: {col}; font-weight: {weight}; text-align: left;">{_rich(text)}</p>')


def _h_section(num: str, title: str, t: Dict[str, str], nxt: bool = True,
               closing: bool = False) -> str:
    num_html = (f'<span style="color: {t["primary"]};">{num}</span>&nbsp;&nbsp;' if num else "")
    kind = "closing" if closing else "section"
    style = t.get("heading_style", "bar")
    box, align = "", "left"
    if style == "bar":
        box = f'padding-left: 10px; border-left: 3px solid {t["primary"]};'
    elif style == "underline":
        box = f'padding-bottom: 6px; border-bottom: 2px solid {t["primary_soft"]};'
    elif style == "center":
        align = "center"
    return (
        f'<section data-b="{kind}" style="margin: 28px 0 12px; {box}">\n'
        f'  <p data-b="section-title" style="margin: 0; font-size: 17px; font-weight: bold; line-height: 1.5; '
        f'letter-spacing: 0.2px; color: {t["strong"]}; text-align: {align};">'
        f'{num_html}{title}</p>\n'
        f'</section>'
    )


def _h_img(img: Optional[Image], t: Dict[str, str], index: int = 0) -> str:
    src = _esc(img.path.replace(os.sep, "/")) if img and img.path else ""
    alt = _esc((img.alt or img.caption or "") if img else "")
    inner = (f'<img src="{src}" alt="{alt}" style="width: 100%; display: block; '
             f'border-radius: {t.get("image_radius", "4")}px;">'
             if src else
             f'<span style="font-size: 12px; color: #9AA3AD;">配图位：1080×608（16:9）｜在此插入图片</span>')
    # 用 figure/figcaption：语义正确，编辑器与第三方工具都能识别成「图 + 图注」
    return (f'<figure data-b="img" data-idx="{index}" style="margin: 20px 0 4px; padding: {0 if src else 36}px 0; '
            f'background: {"transparent" if src else "#F2F4F7"}; text-align: center;">\n  {inner}\n'
            f'  <figcaption style="margin: 8px 0 0; font-size: 12px; color: {t["muted"]}; '
            f'line-height: 1.6; text-align: center;">{_esc(_caption_text(img))}</figcaption>\n</figure>')


def _h_caption(img: Optional[Image], t: Dict[str, str]) -> str:
    cap = img.caption_text() if img and img.caption_text() else "▲ 画面说明：谁、在做什么、证明了什么　图源：待补"
    return (f'<p data-b="caption" style="margin: 0 0 24px; font-size: 12px; color: {t["muted"]}; '
            f'line-height: 1.6; text-align: center;">{_esc(cap)}</p>')


def _caption_text(img: Optional[Image]) -> str:
    if img and img.caption_text():
        return img.caption_text()
    return "▲ 画面说明：谁、在做什么、证明了什么　图源：待补"


def _h_card(items: List[str], t: Dict[str, str]) -> str:
    lis = "\n".join(
        f'  <p style="margin: 0; font-size: 14px; color: {t["text"]}; line-height: 1.75;">· {_esc(i)}</p>'
        for i in items)
    return (
        f'<section data-b="card" style="margin: 0 0 24px; padding: 14px 16px; '
        f'background: {t["primary_soft"]}; border-radius: 8px;">\n'
        f'  <p data-b="card-title" style="margin: 0 0 8px; font-size: 13px; font-weight: bold; '
        f'color: {t["primary"]}; line-height: 1.6;">先说结论</p>\n'
        f'{lis}\n</section>'
    )


def _h_ul(items: List[str], t: Dict[str, str]) -> str:
    lis = "\n".join(
        f'  <li style="margin: 6px 0; font-size: 16px; line-height: 1.75; '
        f'letter-spacing: {t.get("letter_spacing", "0.3")}px; color: {t["text"]};">{_rich(i)}</li>'
        for i in items)
    return (f'<ul data-b="list" style="margin: 0 0 16px; padding-left: 1.4em; color: {t["text"]};">\n'
            f'{lis}\n</ul>')


def _h_quote(text: str, t: Dict[str, str]) -> str:
    return (
        f'<section data-b="quote" style="margin: 0 0 20px; padding: 12px 16px; '
        f'background: {t["quote_bg"]}; border-left: 3px solid {t["quote_line"]}; border-radius: 2px;">\n'
        f'  <p style="margin: 0; font-size: 15px; line-height: 1.75; color: {t["quote_text"]};">{_rich(text)}</p>\n'
        f'</section>'
    )


def _h_code(text: str, t: Dict[str, str], lang: str = "") -> str:
    body = _esc(text.rstrip("\n"))
    return (
        f'<pre data-b="code" style="margin: 20px 0; padding: 16px 18px; background: {t.get("code_bg", "#1F2937")}; '
        f'color: {t.get("code_text", "#E5E7EB")}; border-radius: 8px; overflow-x: auto; '
        f'white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.7;">'
        f'<code style="font-family: SFMono-Regular, Consolas, Menlo, monospace; color: inherit; '
        f'background: transparent; padding: 0;">{body}</code></pre>'
    )


def _h_cta(text: str, t: Dict[str, str]) -> str:
    return (f'<p data-b="cta" style="margin: 0 0 24px; font-size: 15px; line-height: 1.75; '
            f'color: {t["quote_text"]}; text-align: left;">{_rich(text)}</p>')


def render_html(art: Article, theme: Dict[str, str], title_override: str = "") -> str:
    title = title_override or art.title or "未命名文章"
    t = theme
    parts: List[str] = []
    parts.append('<!-- 公众号排版片段：用浏览器打开本文件，选中 body 内全部内容复制 → 后台粘贴 -->')
    parts.append(f'<section style="margin: 0; padding: 0; font-family: -apple-system, '
                 f'\'PingFang SC\', \'Microsoft YaHei\', sans-serif;">')
    parts.append(f'  <p data-b="title" style="margin: 0 0 10px; font-size: 21px; font-weight: bold; '
                 f'color: {t["strong"]}; line-height: 1.45;">{_esc(title)}</p>')
    parts.append(f'  <p data-b="meta" style="margin: 0 0 18px; font-size: 12px; color: {t["meta"]}; line-height: 1.6;">'
                 f'{_dt.date.today().isoformat()} &nbsp;·&nbsp; 全文约 {art.char_count()} 字 &nbsp;·&nbsp; '
                 f'约 {art.read_minutes()} 分钟</p>')

    # 摘要卡
    sb = next((b for b in art.lead if b.kind == "summary"), None)
    if sb and sb.items:
        parts.append(_h_card(sb.items, t))
    for b in art.lead:
        if b is sb:
            continue
        if b.kind == "p":
            parts.append(_h_p(b.text, t))
        elif b.kind == "code":
            parts.append(_h_code(b.text, t, b.items[0] if b.items else ""))

    img_idx = [0]

    def _img_block(img):
        idx = img_idx[0]
        img_idx[0] += 1
        return _h_img(img, t, idx)

    for sec in art.sections:
        if sec.kind == "summary":
            continue
        parts.append(_h_section(sec.number, _esc(sec.title), t))
        for b in sec.blocks:
            if b.kind == "p":
                parts.append(_h_p(b.text, t))
            elif b.kind == "list":
                parts.append(_h_ul(b.items, t))
            elif b.kind == "quote":
                parts.append(_h_quote(b.text, t))
            elif b.kind == "img":
                parts.append(_img_block(b.image))
            elif b.kind == "code":
                parts.append(_h_code(b.text, t, b.items[0] if b.items else ""))

    if art.closing:
        parts.append(_h_section("", "写在最后", t, closing=True))
        for b in art.closing:
            if b.kind == "p":
                parts.append(_h_p(b.text, t))
            elif b.kind == "list":
                parts.append(_h_ul(b.items, t))
            elif b.kind == "quote":
                parts.append(_h_quote(b.text, t))
            elif b.kind == "img":
                parts.append(_img_block(b.image))
            elif b.kind == "code":
                parts.append(_h_code(b.text, t, b.items[0] if b.items else ""))

    if art.cta:
        parts.append(_h_cta(art.cta_text() or "你觉得呢？欢迎在评论区聊聊。", t))
    if art.end:
        parts.append(_h_p(art.end_text() or "关注「公众号名称」，每天一个新鲜事。",
                          t, strong=True, color=t["primary"], kind="end"))
        if not art.end_text():
            parts.append(_h_p("不花钱、不扣钱，只占你 3 分钟。", t))

    parts.append('</section>')
    body = "\n".join(parts)
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{_esc(title)}｜公众号排版片段</title>\n"
        "<style>body{margin:0;padding:24px;background:#f5f6f8;}"
        ".phone{width:375px;margin:0 auto;background:#fff;padding:20px 16px 40px;"
        "box-shadow:0 2px 16px rgba(0,0,0,.08);border-radius:10px;}</style>\n</head>\n"
        f"<body>\n<div class=\"phone\">\n{body}\n</div>\n</body>\n</html>\n"
    )


# --------------------------------------------------------------------------
# 「生成后的模板」再编辑：预处理
# --------------------------------------------------------------------------

COMMENT_BLOCK_RE = re.compile(r"<!--.*?-->", re.S)
APPENDIX_RE = re.compile(r"^#{1,4}\s*附\s*[:：]", re.M)
MD_IMG_RE = re.compile(r"^!\[([^\]]*)\]\((.+)\)\s*$")   # 路径里可能含括号，用贪婪匹配
META_LINE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}\s*[·・|]\s*全文约")
CAPTION_PREFIX_RE = re.compile(r"^(?:▲\s*)?(.*)$")


_ENTITY_RE = re.compile(r"&(?:quot|amp|lt|gt|apos|nbsp|mdash|hellip|#\d{1,5}|#x[0-9a-fA-F]{1,5});")


def _decode_entities(text: str) -> str:
    """把 &quot; / &amp; / &#39; 这类实体还原成字符。

    模板是从 HTML 里抓的、或从 Word/网页复制过来的，正文里常带一层实体；
    不解码的话，预览会显示成「&quot;」这种原文。
    """
    if "&" not in text:
        return text
    import html as _html
    return _ENTITY_RE.sub(lambda m: _html.unescape(m.group(0)), text)


def prepare_markdown(text: str) -> str:
    """把「本程序生成的模板」清洗成可再次解析的源文案。

    处理四类只在模板里出现、解析器不认识的写法：
      1. <!-- 模板说明 / 本节建议配图 --> 整段注释；
      2. 文末「## 附：排版规范 / 发布前自检」；
      3. ![alt](路径) 图片 + 下一行的 > 图注  →  [IMG:路径|alt|图注]；
      4. 文首的「> 日期 · 全文约 N 字」信息行（会被误当引用块）。
    注意：读者手写的 `> 金句` 不会被误伤，只跳过「日期 · 全文约」这一种。
    """
    if not text:
        return text
    text = _decode_entities(text)
    text = COMMENT_BLOCK_RE.sub("", text)
    m = APPENDIX_RE.search(text)
    if m:
        text = text[:m.start()]
    text = re.sub(r"^\s*----+\s*$", "", text, flags=re.M)   # 只剩破折号/横线的分隔行

    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    out: List[str] = []
    i = 0
    n = len(lines)
    seen_end = False
    while i < n:
        line = lines[i]
        s = line.strip()

        # 文首信息行：> 2026-11-01　·　全文约 779 字　·　约 2 分钟
        if META_LINE_RE.match(s.lstrip(">").strip()):
            i += 1
            continue

        mimg = MD_IMG_RE.match(s)
        if mimg:
            alt, src = mimg.group(1).strip(), mimg.group(2).strip()
            cap = ""
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and lines[j].strip().startswith(">"):
                mc = CAPTION_PREFIX_RE.match(lines[j].strip()[1:].strip())
                if mc:
                    cap = mc.group(1).strip()
                    j += 1
            parts = [src]
            if alt or cap:
                parts.append(alt)
            if cap:
                parts.append(cap)
            out.append("[IMG:" + "|".join(parts) + "]")
            i = j
            continue

        # 「互动提问 / 关注引导」老版模板里的粗体小标题 → 还原成标记
        plain = s.strip("*").strip()
        if plain in ("互动提问", "互动问题") or s == "[CTA]":
            out.append("[CTA]")
            i += 1
            continue
        if plain in ("关注引导",) or s == "[END]":
            out.append("[END]")
            seen_end = True
            i += 1
            continue
        # 老模板里紧跟 CTA 的粗体「关注「…」」→ 补一个 [END]，避免被算进互动提问
        if re.match(r"^\*\*\s*关注[「『\"]", s) and not seen_end:
            out.append("[END]")
            seen_end = True

        out.append(line)
        i += 1

    text = "\n".join(out)
    # 去掉文末/文首残留的 ---（附录被裁掉后会剩一条）
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"^\s*-{3,}\s*$", "", text, flags=re.M).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _read_input(path: str) -> Tuple[str, str]:
    """返回 (文本, 基准目录)。用 utf-8-sig 读，顺手吃掉记事本可能加的 BOM。"""
    if path == "-":
        return sys.stdin.read().lstrip("\ufeff"), os.getcwd()
    p = os.path.abspath(path)
    with open(p, "r", encoding="utf-8-sig") as f:
        return f.read(), os.path.dirname(p)


def _load_any(path: str, fmt: str = "") -> Tuple[Article, str, str, str]:
    """读任意支持的格式 → (Article, base_dir, markdown, 来源说明)。

    .md/.txt 直接解析；.html/.docx 先转成规范化 Markdown 再解析，
    这样后面的排版逻辑完全复用，两种路径不会分叉。
    """
    if path == "-":
        raw, base = _read_input(path)
        raw = prepare_markdown(raw)
        return parse_content(raw, base), base, raw, ""

    p = os.path.abspath(path)
    base = os.path.dirname(p)
    ext = fmt or os.path.splitext(p)[1].lower()

    if ext in ("", "text", "md", "txt", ".md", ".markdown", ".mdown", ".txt", ".text"):
        try:
            import convert as C
            raw = C.read_text(p)          # 自动识别 UTF-8 / GBK / Big5 / BOM
        except Exception:
            raw, _ = _read_input(p)
        raw = prepare_markdown(raw)       # 兼容「生成后的模板」再编辑
        return parse_content(raw, base), base, raw, ""

    # 其余格式交给 convert（延迟导入，纯文本模式不依赖它）
    try:
        import convert as C
    except Exception as e:                      # pragma: no cover
        raise SystemExit(f"读取 {ext} 需要 convert.py：{e}")

    loaded = C.load(p)
    md = loaded.markdown
    art = parse_content(md, base)
    return art, base, md, loaded.info.line()


def _out_suffix(input_path: str) -> str:
    ext = os.path.splitext(input_path)[1].lower()
    return ".html" if ext in (".html", ".htm", ".xhtml") else ".md"


def load_config(path: str) -> Dict[str, str]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8-sig") as f:
        if path.lower().endswith(".json"):
            return json.load(f)
        # 极简 key: value 格式
        conf: Dict[str, str] = {}
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            conf[k.strip()] = v.strip()
        return conf


def build(input_path: str, theme_name: str = "business", images_dir: str = "",
          out_md: str = "", out_html: str = "", preview: str = "",
          title: str = "", summary: bool = False, cta: bool = True, end: bool = True,
          config: str = "", fmt: str = "") -> Tuple[str, str]:
    theme_name = theme_name if theme_name in THEMES else "business"
    theme = THEMES[theme_name]
    conf = load_config(config)

    art, base, raw, source_line = _load_any(input_path, fmt)
    if not art.title:
        art.title = title or conf.get("标题") or guess_title(raw)

    assign_images(art, collect_images(images_dir))
    want_summary = summary or conf.get("摘要卡", "").lower() in ("1", "true", "yes")
    normalize(art, want_summary=want_summary, want_cta=cta, want_end=end)

    if title or conf.get("标题"):
        art.title = title or conf["标题"]
    if conf.get("日期"):
        art.meta["日期"] = conf["日期"]

    md = render_markdown(art, theme_name, theme, title, summary_flag=want_summary)
    if source_line:
        md = md.replace("<!--\n  模板说明",
                        f"<!--\n  {source_line}\n  模板说明", 1)

    if not out_md:
        stem = os.path.splitext(os.path.basename(input_path))[0] or "output"
        out_md = os.path.join(os.getcwd(), f"{stem}_模板{_out_suffix(input_path)}")
    out_md = os.path.abspath(out_md)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)

    if out_html:
        html = render_html(art, theme, title)
        out_html = os.path.abspath(out_html)
        with open(out_html, "w", encoding="utf-8") as f:
            f.write(html)

    if preview:
        html = render_html(art, theme, title)
        with open(os.path.abspath(preview), "w", encoding="utf-8") as f:
            f.write(html)

    return out_md, out_html


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Windows 控制台默认 GBK，统一成 UTF-8，避免中文路径/提示乱码
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

    ap = argparse.ArgumentParser(
        prog="wechat_md",
        description="把文案+图片生成公众号排版模板（Markdown，可选 HTML）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("input", nargs="?", help="文案文件（.md/.txt/.html/.docx；- 表示从标准输入读）")
    ap.add_argument("-o", "--out", default="",
                    help="输出路径（默认 <输入名>_模板.md；HTML 输入默认输出 .html）")
    ap.add_argument("--html", default="", help="同时输出可粘贴公众号的 .html")
    ap.add_argument("--preview", default="", help="生成手机宽度预览页 .html")
    ap.add_argument("--images", default="", help="图片文件夹；按文件名序号自动分配到章节")
    ap.add_argument("--theme", default="business", choices=sorted(THEMES), help="主题")
    ap.add_argument("--title", default="", help="覆盖标题")
    ap.add_argument("--summary", action="store_true", help="强制生成「先说结论」卡片")
    ap.add_argument("--from", dest="fmt", default="",
                    help="强制输入格式：text / html / docx（默认按扩展名判断）")
    ap.add_argument("--no-cta", dest="cta", action="store_false", help="不生成互动提问")
    ap.add_argument("--no-end", dest="end", action="store_false", help="不生成关注引导")
    ap.add_argument("--config", default="", help="key: value 配置文件（可写 标题/日期/摘要卡:1）")
    ap.add_argument("--list-formats", action="store_true", help="列出支持的输入格式后退出")
    ap.add_argument("--version", action="version", version="wechat_md 1.1")
    args = ap.parse_args(argv)

    if args.list_formats:
        print("支持输入：")
        print("  .md .markdown .mdown .txt .text   纯文本 / Markdown（自动识别 GBK、BOM）")
        print("  .html .htm .xhtml                 HTML；公众号文章页会只取正文容器")
        print("  .docx                             Word（图片会自动抽到 imgs/）")
        print("  -                                 标准输入")
        return 0

    if not args.input:
        ap.error("缺少输入文件（或用 --list-formats 查看支持的格式）")

    if args.input != "-" and not os.path.exists(args.input):
        ap.error(f"输入文件不存在：{args.input}")
    if args.images and not os.path.isdir(args.images):
        ap.error(f"图片文件夹不存在：{args.images}")

    try:
        md, html = build(
            args.input, theme_name=args.theme, images_dir=args.images,
            out_md=args.out, out_html=args.html, preview=args.preview,
            title=args.title, summary=args.summary, cta=args.cta, end=args.end,
            config=args.config, fmt=args.fmt,
        )
    except SystemExit as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 1
    except Exception as e:                       # 转换失败给出可读原因
        print(f"[错误] {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print(f"[OK] Markdown 模板：{md}")
    if html:
        print(f"[OK] 可粘贴 HTML ：{html}")
    if args.preview:
        print(f"[OK] 预览页      ：{os.path.abspath(args.preview)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
