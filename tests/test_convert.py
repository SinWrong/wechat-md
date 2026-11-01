# -*- coding: utf-8 -*-
"""多格式输入的回归测试：HTML（公众号页 / 普通页）、TXT（GBK）、DOCX。"""
import os
import shutil
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))
sys.path.insert(0, os.path.join(BASE, "tools", "tests"))

import convert as C       # noqa: E402
import wechat_md as W     # noqa: E402

EX = os.path.join(BASE, "examples")


class TestFormatDetect(unittest.TestCase):
    def test_extensions(self):
        self.assertEqual(C.detect_format("a.html"), "html")
        self.assertEqual(C.detect_format("a.HTM"), "html")
        self.assertEqual(C.detect_format("a.docx"), "docx")
        self.assertEqual(C.detect_format("a.txt"), "text")
        self.assertEqual(C.detect_format("a.md"), "text")

    def test_all_exts(self):
        for ext in (".md", ".txt", ".html", ".docx"):
            self.assertIn(ext, C.ALL_EXTS)


class TestEncoding(unittest.TestCase):
    def test_gbk(self):
        path = os.path.join(EX, "gbk_note.txt")
        text = C.read_text(path)
        self.assertIn("GBK 编码的文案测试", text)
        self.assertIn("中文编码识别对了", text)

    def test_bom(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", suffix=".txt", delete=False) as f:
            f.write("# 带 BOM 的标题\n\n正文。\n")
            name = f.name
        try:
            text = C.read_text(name)
            self.assertTrue(text.startswith("# 带 BOM"))
        finally:
            os.unlink(name)


class TestWechatHTML(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loaded = C.load(os.path.join(EX, "wechat_article.html"))

    def test_meta(self):
        info = self.loaded.info
        self.assertTrue(info.wechat)
        self.assertEqual(info.author, "趣闻寻录")
        self.assertTrue(info.date.startswith("20"))

    def test_structure(self):
        art = self.loaded.article
        self.assertIn("一头熊闯进加州人家", art.title)
        self.assertEqual([s.title for s in art.sections],
                         ["一头熊，在别人家吃了5小时自助餐", "它最惦记的，是巧克力和焦糖糖浆"])
        self.assertEqual(art.sections[0].number, "01")
        # 正文里没有导航、隐藏块、工具条
        body = self.loaded.markdown
        for noise in ("首页 / 热点", "这段是隐藏的", "阅读 10万+"):
            self.assertNotIn(noise, body)

    def test_quote_and_list(self):
        md = self.loaded.markdown
        self.assertIn("> 野生动物专家提醒", md)
        self.assertIn("- 别堵：给它让出一条能离开的路", md)
        self.assertIn("- 慢退：", md)

    def test_image_marker(self):
        md = self.loaded.markdown
        self.assertIn("[IMG:https://mmbiz.qpic.cn/", md)
        self.assertIn("|黑熊开冰箱]", md)

    def test_closing(self):
        self.assertEqual(len(self.loaded.article.closing), 1)
        self.assertIn("别给它留菜单", self.loaded.article.closing[0].text)


class TestBlogHTML(unittest.TestCase):
    def test_title_not_duplicated(self):
        loaded = C.load(os.path.join(EX, "blog_article.html"))
        art = loaded.article
        self.assertEqual(art.title, "三个让公众号更好读的小改动")
        self.assertEqual(len(art.sections), 3)
        self.assertNotEqual(art.sections[0].title, art.title)
        self.assertEqual(art.sections[0].title, "先把结论放前面")

    def test_bold_and_figcaption(self):
        loaded = C.load(os.path.join(EX, "blog_article.html"))
        md = loaded.markdown
        self.assertIn("**结论前置**", md)
        imgs = [b.image for b in loaded.article.all_blocks() if b.kind == "img"]
        self.assertEqual(imgs[0].caption, "说明画面里发生了什么。")


class TestDocx(unittest.TestCase):
    def test_structure(self):
        loaded = C.load(os.path.join(EX, "docx_demo", "from_word.docx"))
        art = loaded.article
        self.assertEqual(art.title, "从 Word 到公众号：三步排好一篇稿")
        self.assertEqual([s.title for s in art.sections], ["先定结构", "再定节奏"])
        self.assertEqual(len(art.closing), 1)
        self.assertEqual(loaded.info.format, "docx")

    def test_image_extracted(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "t.docx")
            shutil.copyfile(os.path.join(EX, "docx_demo", "from_word.docx"), src)
            loaded = C.load(src)
            imgs = [b.image for b in loaded.article.all_blocks() if b.kind == "img"]
            self.assertEqual(len(imgs), 1)
            self.assertTrue(os.path.exists(os.path.join(d, imgs[0].path)))

    def test_bad_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".docx", delete=False) as f:
            f.write("not a zip")
            name = f.name
        try:
            with self.assertRaises(ValueError):
                C.load(name)
        finally:
            os.unlink(name)


class TestCliIntegration(unittest.TestCase):
    def test_html_to_template(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.md")
            md, _ = W.build(os.path.join(EX, "wechat_article.html"), out_md=out)
            self.assertTrue(os.path.exists(out))
            with open(out, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("来源：html", text)
            self.assertIn("## 01 一头熊", text)
            self.assertIn("## 02 它最惦记", text)

    def test_docx_default_ext(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "t.docx")
            shutil.copyfile(os.path.join(EX, "docx_demo", "from_word.docx"), src)
            cwd = os.getcwd()
            os.chdir(d)
            try:
                md, _ = W.build(src)
                self.assertTrue(os.path.basename(md).endswith(".md"))
                with open(md, encoding="utf-8") as fh:
                    self.assertIn("## 01 先定结构", fh.read())
            finally:
                os.chdir(cwd)

    def test_html_input_defaults_to_html_output(self):
        self.assertEqual(W._out_suffix("a.html"), ".html")
        self.assertEqual(W._out_suffix("a.md"), ".md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
