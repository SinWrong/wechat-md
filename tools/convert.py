# -*- coding: utf-8 -*-
"""
convert.py —— 多格式文案输入 → 公众号模板

支持：
    .md / .markdown / .txt / .text       直接解析（自动识别 UTF-8 / GBK / Big5）
    .html / .htm / .xhtml                HTML，含「公众号文章页」链接/另存文件
    .docx                                Word（标准库 zip 解析，无第三方依赖）

统一出口：
    load(path)          → Loaded(article, markdown, info)
    to_article(path)    → wechat_md.Article
    to_markdown(path)   → 规范化 Markdown（可直接在编辑器里继续改）
    convert_to_file(...) → 生成带排版说明的 .md 模板

命令行用 load() 拿 Article 再走原来的渲染；GUI 用 load() 拿 markdown 填进编辑区。
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import wechat_md as W

TEXT_EXTS = {".md", ".markdown", ".mdown", ".txt", ".text"}
HTML_EXTS = {".html", ".htm", ".xhtml"}
DOCX_EXTS = {".docx"}
ALL_EXTS = TEXT_EXTS | HTML_EXTS | DOCX_EXTS

DROP_TAGS = {
    "script", "style", "noscript", "template", "iframe", "svg", "canvas",
    "nav", "footer", "form", "button", "select", "option", "input",
    "video", "audio", "source", "track",
}
HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 4, "h6": 4}
VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "source", "track",
             "wbr", "area", "col", "embed", "param"}
BLOCK_TAGS = {"p", "div", "section", "article", "main", "pre", "table",
              "figure", "figcaption", "dl", "dt", "dd", "center", "address"}

OG_TITLE_RE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', re.I)
META_AUTHOR_RE = re.compile(r'<meta[^>]+name="author"[^>]+content="([^"]*)"', re.I)
VAR_CT_RE = re.compile(r"var\s+ct\s*=\s*\"?(\d{10})")
VAR_NICK_RE = re.compile(r"var\s+nickname\s*=\s*\"([^\"]*)\"")
TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


# --------------------------------------------------------------------------
# 读文件
# --------------------------------------------------------------------------

def read_text(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def detect_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in DOCX_EXTS:
        return "docx"
    if ext in HTML_EXTS:
        return "html"
    if ext in TEXT_EXTS:
        return "text"
    head = open(path, "rb").read(2048).decode("utf-8", errors="ignore").lower()
    if "<html" in head or "<!doctype" in head:
        return "html"
    if zipfile.is_zipfile(path):
        return "docx"
    return "text"


# --------------------------------------------------------------------------
# 轻量 HTML 树
# --------------------------------------------------------------------------

@dataclass
class HNode:
    tag: str = ""
    attrs: Dict[str, str] = field(default_factory=dict)
    children: List["HNode"] = field(default_factory=list)
    text: str = ""
    parent: Optional["HNode"] = None

    def cls(self) -> str:
        return (self.attrs.get("class") or "").lower()

    def text_of(self) -> str:
        out: List[str] = []
        stack = [self]
        while stack:
            n = stack.pop()
            if n.text:
                out.append(n.text)
            stack.extend(reversed(n.children))
        return "".join(out)


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = HNode(tag="#root")
        self.cur = self.root
        self.skip = 0
        self.skip_tag = ""

    def handle_starttag(self, tag, attrs_list):
        tag = tag.lower()
        if self.skip:
            if tag == self.skip_tag:
                self.skip += 1
            return
        if tag in ("script", "style"):
            self.skip, self.skip_tag = 1, tag
            return
        attrs = {k.lower(): (v or "") for k, v in attrs_list}
        node = HNode(tag=tag, attrs=attrs, parent=self.cur)
        self.cur.children.append(node)
        if tag not in VOID_TAGS:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        if self.skip:
            return
        tag = tag.lower()
        self.cur.children.append(HNode(
            tag=tag, attrs={k.lower(): (v or "") for k, v in attrs}, parent=self.cur))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip:
            if tag == self.skip_tag:
                self.skip -= 1
                if not self.skip:
                    self.skip_tag = ""
            return
        if tag in VOID_TAGS:
            return
        node = self.cur
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.cur = node.parent

    def handle_data(self, data):
        if self.skip or not data:
            return
        self.cur.children.append(HNode(tag="#text", text=data, parent=self.cur))


def _find(node: HNode, pred) -> Optional[HNode]:
    stack = [node]
    while stack:
        n = stack.pop()
        if pred(n):
            return n
        stack.extend(reversed(n.children))
    return None


def _img_src(node: HNode, base_dir: str) -> str:
    for key in ("data-src", "src", "data-original", "data-lazy-src", "data-actualsrc"):
        v = (node.attrs.get(key) or "").strip()
        if not v or v.startswith("data:"):
            continue
        if v.startswith("//"):
            return "https:" + v
        if v.startswith(("http://", "https://")):
            return v
        if base_dir:
            cand = os.path.normpath(os.path.join(base_dir, v))
            if os.path.exists(cand):
                return v
        return v
    return ""


# --------------------------------------------------------------------------
# HTML → Article
# --------------------------------------------------------------------------

class _Walker:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.art = W.Article()
        self.images: List[W.Image] = []
        self.target: List[W.Block] = self.art.lead
        self.buf: List[str] = []
        self.quote = 0
        self.in_list = 0
        self.dropped = 0
        self.closing = False

    # ---------- 缓冲 ----------
    def _flush(self):
        text = re.sub(r"[ \t\r\n\u3000]+", " ", "".join(self.buf)).strip()
        self.buf = []
        if not text:
            return
        if self.quote:
            self.target.append(W.Block("quote", text=text))
        elif self.in_list:
            self.target.append(W.Block("list", items=[text]))
        else:
            self.target.append(W.Block("p", text=text))

    def _merge_lists(self):
        """把相邻的单项 list 合成一个，方便渲染成 ①②③。"""
        blocks = self.target
        if not blocks:
            return
        merged: List[W.Block] = []
        for b in blocks:
            if (b.kind == "list" and merged and merged[-1].kind == "list"):
                merged[-1].items.extend(b.items)
            else:
                merged.append(b)
        blocks[:] = merged

    # ---------- 小节 ----------
    def _section(self, title: str, level: int):
        self._flush()
        self._merge_lists()
        title = re.sub(r"\s+", " ", title).strip(" #*　")
        if not title:
            return
        if W.CLOSING_RE.match(title):
            self.closing = True
            self.target = self.art.closing
            return
        if W.is_summary_section(title):
            sec = W.Section(number="", title=title, kind="summary")
            self.art.sections.append(sec)
            self.target = sec.blocks
            return
        # 原标题里自带的 "01 xxx" / "一、xxx" 先剥掉，避免后面再补一次编号
        clean = re.sub(r"^\d{1,2}\s*[.、|｜:：]\s*", "", title)
        clean = re.sub(r"^[一二三四五六七八九十]{1,2}\s*[、.．]\s*", "", clean).strip()
        if not clean:
            return
        if not self.art.title:
            self.art.title = clean
            return
        if clean == self.art.title:      # 正文里的 H1 就是标题，不重复开小节
            return
        if self.closing:
            self.target.append(W.Block("p", text=clean))
            return
        sec = W.Section(number="", title=clean)
        self.art.sections.append(sec)
        self.target = sec.blocks

    # ---------- 遍历 ----------
    def walk(self, node: HNode, depth: int = 0):
        if depth > 80:
            return
        tag = node.tag
        if tag == "#text":
            self.buf.append(re.sub(r"\s+", " ", node.text))
            return

        style = (node.attrs.get("style") or "").lower().replace(" ", "")
        if tag in DROP_TAGS or "display:none" in style or "visibility:hidden" in style:
            self.dropped += 1
            return
        if tag in ("header",):
            # 公众号正文里的 header 一般是标题区，保留；page 级 header 多为导航
            parent_tag = node.parent.tag if node.parent is not None else ""
            if parent_tag in ("body", "#root"):
                self.dropped += 1
                return

        if tag == "br":
            self._flush()
            return
        if tag == "hr":
            self._flush()
            self._merge_lists()
            return
        if tag == "img":
            src = _img_src(node, self.base_dir)
            if not src:
                return
            self._flush()
            img = W.Image(path=src, alt=(node.attrs.get("alt") or "").strip())
            self.images.append(img)
            self.target.append(W.Block("img", image=img))
            return

        if tag in HEADING_TAGS:
            text = node.text_of()
            self._section(text, HEADING_TAGS[tag])
            return
        if tag == "blockquote":
            self._flush()
            self.quote += 1
            for ch in node.children:
                self.walk(ch, depth + 1)
            self._flush()
            self.quote -= 1
            return
        if tag == "figcaption":
            # 图注：挂到上一张图上
            self._flush()
            cap = re.sub(r"\s+", " ", node.text_of()).strip()
            cap = re.sub(r"^(图注|图说|图)[:：]\s*", "", cap)
            if cap:
                img_block = next((b for b in reversed(self.target) if b.kind == "img"), None)
                if img_block is not None and img_block.image is not None:
                    img_block.image.caption = cap
                else:
                    self.target.append(W.Block("p", text=cap))
            return
        if tag in ("ul", "ol"):
            self._flush()
            self.in_list += 1
            for ch in node.children:
                self.walk(ch, depth + 1)
            self._flush()
            self.in_list -= 1
            self._merge_lists()
            return
        if tag == "li":
            if self.in_list:
                self._flush()
                for ch in node.children:
                    self.walk(ch, depth + 1)
                self._flush()
            else:
                for ch in node.children:
                    self.walk(ch, depth + 1)
            return
        if tag in ("strong", "b"):
            self.buf.append("**")
            for ch in node.children:
                self.walk(ch, depth + 1)
            self.buf.append("**")
            return
        if tag in ("em", "i"):
            for ch in node.children:
                self.walk(ch, depth + 1)
            return
        if tag in ("sup", "sub"):
            return
        if tag == "a":
            for ch in node.children:
                self.walk(ch, depth + 1)
            return
        if tag in BLOCK_TAGS:
            self._flush()
            for ch in node.children:
                self.walk(ch, depth + 1)
            self._flush()
            return

        for ch in node.children:
            self.walk(ch, depth + 1)

    def finish(self) -> Tuple[W.Article, List[W.Image]]:
        self._flush()
        self._merge_lists()
        art = self.art
        W.normalize(art, want_summary=False, want_cta=False, want_end=False)
        art.images = self.images
        return art, self.images


@dataclass
class SourceInfo:
    format: str = "text"
    title: str = ""
    author: str = ""
    date: str = ""
    paragraphs: int = 0
    images: int = 0
    sections: int = 0
    dropped: int = 0
    wechat: bool = False

    def line(self) -> str:
        parts = [f"来源：{self.format}"]
        if self.wechat:
            parts.append("公众号文章页")
        if self.author:
            parts.append(f"原作者：{self.author}")
        if self.date:
            parts.append(f"原发布日期：{self.date}")
        return "　·　".join(parts)


def _stat(art: W.Article) -> Tuple[int, int]:
    paras = sum(1 for b in art.all_blocks() if b.kind == "p" and b.text.strip())
    return paras, len(art.sections)


def html_to_article(html: str, base_dir: str = "") -> Tuple[W.Article, SourceInfo]:
    tb = _TreeBuilder()
    tb.feed(html)
    tb.close()
    root = tb.root

    info = SourceInfo(format="html")
    page_title = ""
    m = OG_TITLE_RE.search(html)
    if m:
        page_title = m.group(1).strip()
    if not page_title:
        t = _find(root, lambda n: n.tag == "title")
        page_title = re.sub(r"\s+", " ", t.text_of()).strip() if t else ""
    if not page_title:
        h1 = _find(root, lambda n: n.tag == "h1")
        page_title = re.sub(r"\s+", " ", h1.text_of()).strip() if h1 else ""

    container = _find(root, lambda n: n.attrs.get("id") == "js_content"
                      or "rich_media_content" in n.cls())
    if container is not None:
        info.wechat = True
        start = container
        walker = _Walker(base_dir)
        walker.art.title = page_title
        for ch in start.children:
            walker.walk(ch)
    else:
        body = _find(root, lambda n: n.tag == "body") or root
        main = _find(body, lambda n: n.tag in ("article", "main"))
        start = main or body
        walker = _Walker(base_dir)
        walker.art.title = page_title
        for ch in start.children:
            walker.walk(ch)

    art, imgs = walker.finish()
    info.title = art.title or page_title
    info.author = (META_AUTHOR_RE.search(html).group(1).strip()
                   if META_AUTHOR_RE.search(html) else "")
    ct = VAR_CT_RE.search(html)
    if ct:
        info.date = _dt.datetime.fromtimestamp(int(ct.group(1))).strftime("%Y-%m-%d")
    info.images = len(imgs)
    info.dropped = walker.dropped
    info.sections = len(art.sections)
    info.paragraphs, _ = _stat(art)
    return art, info


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": W_NS, "a": A_NS, "r": R_NS}


def _docx_styles(zf: zipfile.ZipFile) -> Dict[str, int]:
    out: Dict[str, int] = {}
    try:
        root = ET.fromstring(zf.read("word/styles.xml"))
        for st in root.findall("w:style", NS):
            sid = st.attrib.get("{%s}styleId" % W_NS, "")
            name_el = st.find("w:name", NS)
            name = (name_el.attrib.get("{%s}val" % W_NS, "") if name_el is not None else "").lower()
            level = 0
            m = re.search(r"heading\s*([1-4])", name) or re.search(r"标题\s*([1-4])", name)
            if m:
                level = int(m.group(1))
            elif name in ("title", "subtitle", "标题"):
                level = 1
            if sid and level:
                out[sid] = level
    except Exception:
        pass
    return out


def _docx_rels(zf: zipfile.ZipFile) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
        for rel in root:
            rid = rel.attrib.get("Id")
            if rid:
                out[rid] = rel.attrib.get("Target", "")
    except Exception:
        pass
    return out


def _docx_par_text(par) -> Tuple[str, List[str]]:
    parts: List[str] = []
    imgs: List[str] = []
    for run in par.findall("w:r", NS):
        for t in run.findall("w:t", NS):
            parts.append(t.text or "")
        for _tab in run.findall("w:tab", NS):
            parts.append(" ")
        for br in run.findall("w:br", NS):
            parts.append("\n")
        for blip in run.iter("{%s}blip" % A_NS):
            rid = blip.attrib.get("{%s}embed" % R_NS, "")
            if rid:
                imgs.append(rid)
    text = "".join(parts)
    return text, imgs


def _next_img_name(folder: str, ext: str) -> str:
    nums = []
    for f in os.listdir(folder):
        m = re.match(r"^(\d{2,3})(?:-|\.)", f)   # 只认 "01-" / "01.png"，不误伤其他图
        if m:
            nums.append(int(m.group(1)))
    n = (max(nums) + 1) if nums else 1
    while True:
        name = f"{n:02d}{ext}"
        if not os.path.exists(os.path.join(folder, name)):
            return name
        n += 1


def docx_to_article(path: str) -> Tuple[W.Article, SourceInfo]:
    if not zipfile.is_zipfile(path):
        raise ValueError("不是有效的 .docx 文件（旧版 .doc 请先用 Word 另存为 .docx）")
    info = SourceInfo(format="docx")
    art = W.Article()
    images: List[W.Image] = []
    base = os.path.dirname(os.path.abspath(path))

    with zipfile.ZipFile(path) as zf:
        styles = _docx_styles(zf)
        rels = _docx_rels(zf)
        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find("w:body", NS)
        if body is None:
            raise ValueError("docx 里没有正文内容")

        cur: Optional[W.Section] = None
        target: List[W.Block] = art.lead
        closing = False
        saved: Dict[str, W.Image] = {}      # relId → 已抽取的图片，避免重复抽取

        for par in body.findall("w:p", NS):
            style_id = ""
            ppr = par.find("w:pPr", NS)
            if ppr is not None:
                ps = ppr.find("w:pStyle", NS)
                if ps is not None:
                    style_id = ps.attrib.get("{%s}val" % W_NS, "")
            level = styles.get(style_id, 0)
            text, img_rids = _docx_par_text(par)
            text = re.sub(r"\s+", " ", text).strip()

            for rid in img_rids:
                if rid in saved:
                    target.append(W.Block("img", image=saved[rid]))
                    continue
                target_name = rels.get(rid, "")
                if not target_name:
                    continue
                zpath = target_name.lstrip("/") if target_name.startswith("/") else "word/" + target_name.lstrip("./")
                try:
                    data = zf.read(zpath)
                except KeyError:
                    continue
                ext = os.path.splitext(zpath)[1].lower() or ".png"
                img_dir = os.path.join(base, "imgs")
                os.makedirs(img_dir, exist_ok=True)
                name = _next_img_name(img_dir, ext)
                with open(os.path.join(img_dir, name), "wb") as f:
                    f.write(data)
                img = W.Image(path=f"imgs/{name}", alt=text[:24])
                saved[rid] = img
                images.append(img)
                target.append(W.Block("img", image=img))

            if not text:
                continue
            if level:
                title = re.sub(r"^\d{1,2}\s*(?:[.、|｜:：]\s*|\s+)", "", text)
                title = re.sub(r"^[一二三四五六七八九十]{1,2}\s*[、.．]\s*", "", title).strip()
                if W.CLOSING_RE.match(title):
                    closing = True
                    cur = None
                    target = art.closing
                    continue
                if not art.title and level <= 2:
                    art.title = title
                    continue
                if not title or title == art.title:
                    pass
                elif closing:
                    target.append(W.Block("p", text=title))
                else:
                    cur = W.Section(number="", title=title.rstrip("：:"))
                    art.sections.append(cur)
                    target = cur.blocks
                continue
            if closing:
                target.append(W.Block("p", text=text))
                continue
            if cur is None and not art.title:
                art.title = text
                continue
            target.append(W.Block("p", text=text))

    art.images = images
    W.normalize(art, want_summary=False, want_cta=False, want_end=False)
    if not art.title:
        art.title = os.path.splitext(os.path.basename(path))[0]
    info.title = art.title
    info.images = len(images)
    info.sections = len(art.sections)
    info.paragraphs, _ = _stat(art)
    return art, info


# --------------------------------------------------------------------------
# 文本
# --------------------------------------------------------------------------

def text_to_article(text: str, base_dir: str = "") -> Tuple[W.Article, SourceInfo]:
    art = W.parse_content(text, base_dir)
    info = SourceInfo(format="text")
    if not art.title:
        art.title = os.path.splitext(os.path.basename(base_dir))[0] if base_dir else "未命名文章"
    info.title = art.title
    info.images = len(art.images)
    info.sections = len(art.sections)
    info.paragraphs, _ = _stat(art)
    return art, info


# --------------------------------------------------------------------------
# Article → 规范化 Markdown
# --------------------------------------------------------------------------

def article_to_markdown(art: W.Article, info: Optional[SourceInfo] = None) -> str:
    out: List[str] = []
    add = out.append
    add(f"# {art.title or '未命名文章'}")
    add("")
    if info and (info.author or info.date):
        if info.date:
            add(f"日期: {info.date}")
        if info.author:
            add(f"作者: {info.author}")
        add("")

    def emit(blocks):
        for b in blocks:
            if b.kind == "p":
                if b.text.strip():
                    add(b.text)
                    add("")
            elif b.kind == "quote":
                for line in b.text.split("\n"):
                    add("> " + line)
                add("")
            elif b.kind == "list":
                for item in b.items:
                    add("- " + item)
                add("")
            elif b.kind == "img":
                img = b.image
                if not img or not img.path:
                    continue
                parts = [img.path]
                if img.alt or img.caption or img.source:
                    parts.append(img.alt)
                if img.caption or img.source:
                    parts.append(img.caption)
                if img.source:
                    parts.append(img.source)
                add("[IMG:" + "|".join(parts) + "]")
                add("")

    summary = next((b for b in art.lead if b.kind == "summary"), None)
    if summary and summary.items:
        add("## 先说结论")
        add("")
        for it in summary.items:
            add(f"> · {it}")
        add("")
    for b in art.lead:
        if b is summary:
            continue
        emit([b])

    for idx, sec in enumerate(art.sections, 1):
        if sec.kind == "summary":
            continue
        num = sec.number or f"{idx:02d}"
        add(f"## {num} {sec.title}".rstrip())
        add("")
        emit(sec.blocks)

    if art.closing:
        add("## 写在最后")
        add("")
        emit(art.closing)

    if art.cta:
        add("[CTA]")
        add(art.cta_text() or "看完这篇，你最大的感受是什么？欢迎在评论区聊聊。")
        add("")
    if art.end:
        add("[END]")
        add(art.end_text() or "**关注「公众号名称」，每天一个新鲜事。**")
        add("")
    return "\n".join(out).strip() + "\n"


# --------------------------------------------------------------------------
# 统一入口
# --------------------------------------------------------------------------

@dataclass
class Loaded:
    article: W.Article
    markdown: str
    info: SourceInfo
    path: str = ""
    base_dir: str = ""          # 源文件目录：图片相对路径按它解析
    source: str = ""            # 原始文本（再转换时直接喂给它）


def load(path: str) -> Loaded:
    fmt = detect_format(path)
    base = os.path.dirname(os.path.abspath(path))
    if fmt == "docx":
        art, info = docx_to_article(path)
        src = None
    elif fmt == "html":
        src = read_text(path)
        art, info = html_to_article(src, base)
    else:
        src = read_text(path)
        art, info = text_to_article(src, base)
    # 图片路径统一转成可被 parse_content(base) 解析的形式
    for b in art.all_blocks():
        if b.kind == "img" and b.image and b.image.path:
            p = b.image.path
            if not os.path.isabs(p) and not p.startswith(("http://", "https://")):
                cand = os.path.normpath(os.path.join(base, p))
                if os.path.exists(cand):
                    b.image.path = os.path.relpath(cand, base).replace(os.sep, "/")
    md = article_to_markdown(art, info)
    return Loaded(article=art, markdown=md, info=info, path=path, base_dir=base,
                  source=src or "")


def to_article(path: str) -> W.Article:
    return load(path).article


def to_markdown(path: str) -> str:
    return load(path).markdown


def convert_to_file(src: str, dst: str, theme: str = "business",
                    want_summary: bool = False) -> Loaded:
    loaded = load(src)
    W.normalize(loaded.article, want_summary=want_summary, want_cta=True, want_end=True)
    md = W.render_markdown(loaded.article, theme, W.THEMES.get(theme, W.THEMES["business"]),
                           loaded.article.title)
    if loaded.info.format != "text":
        md = md.replace("<!--\n  模板说明",
                        f"<!--\n  {loaded.info.line()}\n  模板说明", 1)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(md)
    return loaded
