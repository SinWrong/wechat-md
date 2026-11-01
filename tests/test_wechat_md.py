# -*- coding: utf-8 -*-
"""wechat_md 的最小回归测试：python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import wechat_md as W  # noqa: E402


SAMPLE = """# 测试标题

导语第一段。第二句。

## 01 第一节

正文一。

- 要点一
- 要点二

[IMG:图1.jpg|图一|说明一。图源：A]

## 二、第二节

正文二。

> 引用一句话

## 写在最后

收尾句。

[CTA]
[END]
"""


class TestParse(unittest.TestCase):
    def setUp(self):
        self.art = W.parse_content(SAMPLE, ".")

    def test_title(self):
        self.assertEqual(self.art.title, "测试标题")

    def test_sections(self):
        self.assertEqual(len(self.art.sections), 2)
        self.assertEqual(self.art.sections[0].number, "01")
        self.assertEqual(self.art.sections[0].title, "第一节")
        self.assertEqual(self.art.sections[1].number, "02")   # 中文数字
        self.assertEqual(self.art.sections[1].title, "第二节")

    def test_list_not_split_into_sections(self):
        sec = self.art.sections[0]
        kinds = [b.kind for b in sec.blocks]
        self.assertIn("list", kinds)
        lists = [b for b in sec.blocks if b.kind == "list"]
        self.assertEqual(lists[0].items, ["要点一", "要点二"])

    def test_closing(self):
        self.assertEqual(len(self.art.closing), 1)
        self.assertEqual(self.art.closing[0].text, "收尾句。")
        self.assertFalse(any(s.title == "写在最后" for s in self.art.sections))

    def test_image(self):
        imgs = [b for s in self.art.sections for b in s.blocks if b.kind == "img"]
        self.assertEqual(len(imgs), 1)
        self.assertEqual(imgs[0].image.caption, "说明一。")
        self.assertEqual(imgs[0].image.source, "图源：A")

    def test_quote(self):
        q = [b for s in self.art.sections for b in s.blocks if b.kind == "quote"]
        self.assertEqual(q[0].text, "引用一句话")


class TestRender(unittest.TestCase):
    def test_md_contains_key_parts(self):
        art = W.parse_content(SAMPLE, ".")
        W.normalize(art, want_summary=True)
        md = W.render_markdown(art, "business", W.THEMES["business"])
        for token in ("# 测试标题", "## 01 第一节", "先说结论", "## 写在最后",
                      "![图一]", "> 说明一。　图源：A", "附：发布前自检"):
            self.assertIn(token, md)
        self.assertNotIn("## 01 01", md)
        self.assertEqual(md.count("## 写在最后"), 1)

    def test_html_inline_styles_only(self):
        art = W.parse_content(SAMPLE, ".")
        W.normalize(art)
        html = W.render_html(art, W.THEMES["news"])
        self.assertIn("#C0302F", html)   # 新闻红主题色出现在编号/标题/关注引导里
        self.assertNotIn("class=\"note\"", html)
        self.assertNotIn("<link", html)

    def test_summary_from_lead(self):
        art = W.parse_content("标题\n\n第一句。第二句。第三句。\n\n## 01 小节\n\n正文。", ".")
        W.normalize(art, want_summary=True)
        sb = [b for b in art.lead if b.kind == "summary"][0]
        self.assertEqual(len(sb.items), 3)
        self.assertTrue(all(len(i) <= 33 for i in sb.items))


class TestImages(unittest.TestCase):
    def test_assign_by_number(self):
        art = W.parse_content("标题\n\n## 01 第一节\n\n正文。\n\n## 02 第二节\n\n正文。", ".")
        pool = [W.Image(path="x/01-a.jpg"), W.Image(path="x/02-b.jpg")]
        W.assign_images(art, pool)
        self.assertEqual(len(art.sections[0].blocks), 2)
        self.assertEqual(art.sections[0].blocks[-1].image.path, "x/01-a.jpg")
        self.assertEqual(art.sections[1].blocks[-1].image.path, "x/02-b.jpg")

    def test_collect_and_caption(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("01-监控-黑熊.png", "02-网友配图.jpg"):
                open(os.path.join(d, name), "wb").close()
            imgs = W.collect_images(d)
            self.assertEqual(len(imgs), 2)
            self.assertTrue(imgs[0].caption)
            self.assertNotIn("01", imgs[0].caption)


class TestCLI(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.md")
            with open(src, "w", encoding="utf-8") as f:
                f.write(SAMPLE)
            out_md, out_html = W.build(src, theme_name="warm", out_md=os.path.join(d, "o.md"),
                                       out_html=os.path.join(d, "o.html"))
            self.assertTrue(os.path.getsize(out_md) > 500)
            self.assertTrue(os.path.getsize(out_html) > 500)
            with open(out_html, encoding="utf-8") as fh:
                html = fh.read()
            self.assertIn("#C96A1E", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
