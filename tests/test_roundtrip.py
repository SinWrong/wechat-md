# -*- coding: utf-8 -*-
"""往返测试：生成模板 → 再解析，结构不能丢。"""
import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))

import wechat_md as W   # noqa: E402

EX = os.path.join(BASE, "examples")


def make_template(text: str) -> str:
    art = W.parse_content(text, EX)
    W.normalize(art, want_summary=True, want_cta=True, want_end=True)
    return W.render_markdown(art, "business", W.THEMES["business"])


class TestRoundTrip(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(EX, "bear.md"), encoding="utf-8") as f:
            self.src = f.read()
        self.tpl = make_template(self.src)

    def test_source_has_markers(self):
        self.assertIn("[IMG:", self.src)
        self.assertIn("[CTA]", self.src)
        self.assertIn("[END]", self.src)

    def test_template_is_clean(self):
        # 生成物里不应该有「模板说明」以外的裸标记残留
        self.assertIn("<!--", self.tpl)
        self.assertIn("![", self.tpl)

    def test_reparse_keeps_sections(self):
        art = W.parse_content(self.tpl, EX)
        titles = [s.title for s in art.sections]
        self.assertEqual(titles, [
            "一头熊，在别人家吃了5小时自助餐",
            "它最惦记的，是巧克力和焦糖糖浆",
            "好笑归好笑，屋主已经报了管理部门",
            "真遇上熊，记住\"别堵、别喂、给退路\"",
        ])

    def test_reparse_keeps_images(self):
        art = W.parse_content(self.tpl, EX)
        self.assertEqual(len(art.images), 3)   # 2 张真图 + 1 个「本节配图」占位
        self.assertIn("黑熊拉开冰箱门", art.images[0].alt)
        # 图注不能变成孤立引用
        quotes = [b.text for b in art.all_blocks() if b.kind == "quote"]
        self.assertFalse(any("监控画面" in q for q in quotes))

    def test_reparse_keeps_caption_and_source(self):
        art = W.parse_content(self.tpl, EX)
        img = art.images[0]
        self.assertTrue(img.caption or img.source)
        text = (img.caption + img.source)
        self.assertIn("图源", text)

    def test_reparse_strips_comment_and_appendix(self):
        art = W.parse_content(self.tpl, EX)
        body = "\n".join(b.text for b in art.all_blocks())
        self.assertNotIn("模板说明", body)
        self.assertNotIn("排版规范", body)
        self.assertNotIn("发布前自检", body)
        self.assertNotIn("<!--", body)

    def test_reparse_keeps_summary_card(self):
        art = W.parse_content(self.tpl, EX)
        sb = [b for b in art.lead if b.kind == "summary"]
        self.assertEqual(len(sb), 1)
        self.assertEqual(len(sb[0].items), 3)

    def test_reparse_keeps_closing_cta_end(self):
        art = W.parse_content(self.tpl, EX)
        self.assertEqual(len(art.closing), 1)
        self.assertTrue(art.cta is not None)
        self.assertTrue(art.end)
        self.assertTrue(art.cta_text())
        # 关注引导不能被算进互动提问
        self.assertNotIn("关注", art.cta_text())

    def test_html_has_images_and_bold(self):
        art = W.parse_content(self.tpl, EX)
        html = W.render_html(art, W.THEMES["business"])
        self.assertEqual(html.count("<img"), 3)
        self.assertNotIn("**", html)

    def test_double_roundtrip_stable(self):
        tpl2 = make_template(self.tpl)
        art1 = W.parse_content(self.tpl, EX)
        art2 = W.parse_content(tpl2, EX)
        self.assertEqual(len(art1.sections), len(art2.sections))
        real1 = [i for i in art1.images if not i.path.startswith("图片路径")]
        real2 = [i for i in art2.images if not i.path.startswith("图片路径")]
        self.assertEqual(len(real1), len(real2))

    def test_prepare_idempotent(self):
        once = W.prepare_markdown(self.tpl)
        twice = W.prepare_markdown(once)
        self.assertEqual(once, twice)


class TestPrepareMarkdown(unittest.TestCase):
    def test_md_image_with_caption(self):
        text = "# T\n\n![图](a.jpg)\n\n> 图注一句话。图源：某处\n"
        out = W.prepare_markdown(text)
        self.assertIn("[IMG:a.jpg|图|图注一句话。图源：某处]", out)

    def test_comment_removed(self):
        text = "# T\n\n<!-- 说明 -->\n\n正文。\n"
        self.assertNotIn("说明", W.prepare_markdown(text))

    def test_appendix_removed(self):
        text = "# T\n\n正文。\n\n## 附：排版规范\n\n表格\n"
        out = W.prepare_markdown(text)
        self.assertNotIn("排版规范", out)
        self.assertIn("正文", out)

    def test_meta_line_removed(self):
        text = "# T\n\n> 2026-01-01　·　全文约 100 字　·　约 1 分钟\n\n正文。\n"
        self.assertNotIn("全文约", W.prepare_markdown(text))

    def test_quote_not_eaten(self):
        text = "# T\n\n> 这是一句金句引用，应该保留。\n"
        self.assertIn("> 这是一句金句引用", W.prepare_markdown(text))

    def test_old_cta_heading(self):
        text = "# T\n\n**互动提问**\n\n你的看法？\n"
        self.assertIn("[CTA]", W.prepare_markdown(text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
