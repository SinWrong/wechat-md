# -*- coding: utf-8 -*-
"""
make_demo.py —— 生成多格式输入的演示素材（示例用，不参与运行）

产出：
    examples/wechat_article.html   公众号文章页（含导航、工具条、隐藏块）
    examples/blog_article.html     普通博客页（h1/h2、加粗、figure 图注）
    examples/gbk_note.txt          GBK 编码文本
    examples/docx_demo/from_word.docx  Word 文档（含一张图）

用法：python tools/make_demo.py
"""

import os
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(BASE, "examples")
IMGS = os.path.join(EX, "imgs")
DOCX_DIR = os.path.join(EX, "docx_demo")
os.makedirs(IMGS, exist_ok=True)
os.makedirs(DOCX_DIR, exist_ok=True)

# ---------------------------------------------------------------- 1. 公众号文章页
WECHAT_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta property="og:title" content="一头熊闯进加州人家，拉开冰箱吃了5小时，还专挑巧克力和焦糖糖浆" />
<meta name="author" content="趣闻寻录" />
<title>一头熊闯进加州人家</title>
<script>var ct = "1760000000"; var nickname = "趣闻寻录";</script>
<style>.rich_media_content p{font-size:16px}</style>
</head>
<body>
<header id="js_header"><nav>首页 / 热点</nav></header>
<div class="rich_media_area">
  <h1 class="rich_media_title" id="activity-name">一头熊闯进加州人家，拉开冰箱吃了5小时，还专挑巧克力和焦糖糖浆</h1>
  <div class="rich_media_content" id="js_content">
    <p>家里冰箱要是忘了关，顶多化几块肉。可美国加州有一户人家，冰箱没等主人忘关，自己来了位“客人”——一头大黑熊。</p>
    <p>等屋主发现，这熊在自己家厨房，已经“自助”了整整5个小时。</p>
    <h2>一头熊，在别人家吃了5小时自助餐</h2>
    <p>近日，美国加利福尼亚州红杉国家公园附近的一处民宅，发生了一桩让人哭笑不得的事。</p>
    <p><img data-src="https://mmbiz.qpic.cn/mmbiz_jpg/demo/640?wx_fmt=jpeg" alt="黑熊开冰箱"></p>
    <h2>它最惦记的，是巧克力和焦糖糖浆</h2>
    <p>屋主发现，冰箱里的东西它不是随便乱吃，而是有明显的口味偏好——尤其钟情巧克力和焦糖糖浆。</p>
    <blockquote>野生动物专家提醒：住在野生动物活跃区附近的人，要加固房屋门窗。</blockquote>
    <ul>
      <li>别堵：给它让出一条能离开的路</li>
      <li>别喂：投喂只会让它下次还来</li>
      <li>慢退：别大喊大叫，退到安全处再联系管理部门</li>
    </ul>
    <h2>写在最后</h2>
    <p>熊来不来是它的事，咱们先别给它留菜单。</p>
    <p style="display:none">这段是隐藏的，不该被抓取。</p>
  </div>
  <div class="rich_media_tool">阅读 10万+ · 在看 2333</div>
</div>
</body>
</html>
"""

BLOG_HTML = """<!doctype html>
<html><head><title>三个让公众号更好读的小改动</title></head>
<body>
<nav><a href="/">首页</a> | <a href="/about">关于</a></nav>
<article>
  <h1>三个让公众号更好读的小改动</h1>
  <p>这是导语。讲清楚为什么要改。</p>
  <h2>一、先把结论放前面</h2>
  <p>读者只有三秒决定要不要继续读，<strong>结论前置</strong>是最有效的改动。</p>
  <h2>二、段落别超过三行</h2>
  <p>手机一屏只有十几行，超过三行的段落，滑走率明显变高。</p>
  <p>可以这样拆：<br>第一句给事实。<br>第二句给判断。</p>
  <h2>三、给图片加说明</h2>
  <figure>
    <img src="imgs/example.png" alt="示例图">
    <figcaption>图注：说明画面里发生了什么。</figcaption>
  </figure>
</article>
<footer>© 2026 示例博客</footer>
</body></html>
"""

GBK_TEXT = """# GBK 编码的文案测试

这是一段用 GBK 保存的正文，程序应该能自动识别编码。

## 01 第一小节

中文编码识别对了，就不会出现乱码。

## 02 第二小节

第二段正文。
"""


def write_html():
    with open(os.path.join(EX, "wechat_article.html"), "w", encoding="utf-8") as f:
        f.write(WECHAT_HTML)
    with open(os.path.join(EX, "blog_article.html"), "w", encoding="utf-8") as f:
        f.write(BLOG_HTML)


def write_gbk():
    with open(os.path.join(EX, "gbk_note.txt"), "wb") as f:
        f.write(GBK_TEXT.encode("gbk"))


# ---------------------------------------------------------------- 2. docx
CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>
</w:styles>"""


def _p(text, style=None, bold=False, image=False):
    ppr = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ""
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    runs = ('<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr, text)) if text else ""
    if image:
        runs += ('<w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
                 '<wp:extent cx="1905000" cy="1079500"/><wp:docPr id="1" name="pic"/>'
                 '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                 '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                 '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                 '<pic:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="rId2"/></pic:blipFill>'
                 '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
    return "<w:p>%s%s</w:p>" % (ppr, runs)


DOCUMENT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + _p("从 Word 到公众号：三步排好一篇稿", "Heading1")
            + _p("这是 Word 里写的导语，直接转换应该能保住段落结构。")
            + _p("01 先定结构", "Heading2")
            + _p("小标题会被识别成公众号的 01 小节，正文按段保留。")
            + _p("这一句在 Word 里是加粗的。", bold=True)
            + _p("", image=True)
            + _p("02 再定节奏", "Heading2")
            + _p("段落之间留空，手机上更好读。")
            + _p("写在最后", "Heading2")
            + _p("最后一句话。")
            + "</w:body></w:document>")


def write_docx():
    from PIL import Image
    img_path = os.path.join(IMGS, "docx_sample.png")
    Image.new("RGB", (600, 340), (210, 220, 240)).save(img_path)
    with open(img_path, "rb") as f:
        img_bytes = f.read()

    # 每次重新生成前清空抽取目录，保证 demo 可重复
    demo_imgs = os.path.join(DOCX_DIR, "imgs")
    if os.path.isdir(demo_imgs):
        for f in os.listdir(demo_imgs):
            os.remove(os.path.join(demo_imgs, f))

    out = os.path.join(DOCX_DIR, "from_word.docx")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", DOCUMENT)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/media/image1.png", img_bytes)
    return out


def main():
    write_html()
    write_gbk()
    docx = write_docx()
    print("生成完成：")
    for p in (os.path.join(EX, "wechat_article.html"),
              os.path.join(EX, "blog_article.html"),
              os.path.join(EX, "gbk_note.txt"), docx):
        print("  ", os.path.relpath(p, BASE), os.path.getsize(p), "bytes")


if __name__ == "__main__":
    main()
