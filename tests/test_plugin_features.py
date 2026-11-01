# -*- coding: utf-8 -*-
"""参考 wechat_tool_reverse（织页）补的能力回归测试。"""
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))

import wechat_md as W    # noqa: E402
import gui_core as G     # noqa: E402

EX = os.path.join(BASE, "examples")


class TestParagraphTokens(unittest.TestCase):
    def setUp(self):
        art = W.parse_content("# T\n\n## 01 节\n\n正文。\n", ".")
        self.html = W.render_html(art, W.THEMES["business"])

    def test_letter_spacing(self):
        self.assertIn("letter-spacing: 0.3px", self.html)

    def test_word_break(self):
        self.assertIn("word-break: break-word", self.html)
        self.assertIn("overflow-wrap: break-word", self.html)


class TestHeadingVariants(unittest.TestCase):
    def _html(self, theme):
        art = W.parse_content("# T\n\n## 01 节\n\n正文。\n", ".")
        return W.render_html(art, W.THEMES[theme])

    def test_bar(self):
        self.assertIn("border-left: 3px solid #2F6FD0", self._html("business"))

    def test_underline(self):
        html = self._html("news")
        self.assertIn("border-bottom: 2px solid #FBEDED", html)
        self.assertNotIn("border-left: 3px solid #C0302F", html)

    def test_center(self):
        art = W.parse_content("# T\n\n## 01 节\n\n正文。\n", ".")
        theme = dict(W.THEMES["warm"])
        theme["heading_style"] = "center"
        html = W.render_html(art, theme)
        self.assertIn('data-b="section-title"', html)
        self.assertIn("text-align: center", html)


class TestSemanticMarkup(unittest.TestCase):
    def setUp(self):
        src = ("# T\n\n## 01 节\n\n- 甲\n- 乙\n\n"
               "[IMG:a.jpg|图|说明。图源：某处]\n\n"
               "```python\nprint(1)\n```\n\n"
               "正文有 `code`、**粗** 和 [链接](https://x.com)。\n")
        art = W.parse_content(src, ".")
        self.html = W.render_html(art, W.THEMES["business"])

    def test_list_semantic(self):
        self.assertIn("<ul", self.html)
        self.assertEqual(self.html.count("<li"), 2)

    def test_figure_figcaption(self):
        self.assertIn("<figure", self.html)
        self.assertIn("<figcaption", self.html)
        self.assertIn("说明。　图源：某处", self.html)

    def test_code_block(self):
        self.assertIn("<pre", self.html)
        self.assertIn("<code", self.html)
        self.assertIn("print(1)", self.html)

    def test_inline(self):
        self.assertIn("<strong>粗</strong>", self.html)
        self.assertIn('href="https://x.com"', self.html)
        # 行内 code 与代码块里的 <code> 都在
        self.assertGreaterEqual(self.html.count("<code"), 2)


class TestPreviewParsing(unittest.TestCase):
    def test_figure_becomes_caption(self):
        src = "# T\n\n## 01 节\n\n[IMG:a.jpg|图|说明。图源：某处]\n"
        art = W.parse_content(src, ".")
        blocks = G.parse_preview_blocks(W.render_html(art, W.THEMES["business"]))
        kinds = [b.kind for b in blocks]
        self.assertIn("img", kinds)
        self.assertNotIn("caption", kinds)      # 图注并进 img 块
        img = next(b for b in blocks if b.kind == "img")
        self.assertIn("图源", img.text)

    def test_ul_becomes_list(self):
        art = W.parse_content("# T\n\n## 01 节\n\n- 甲\n- 乙\n", ".")
        blocks = G.parse_preview_blocks(W.render_html(art, W.THEMES["business"]))
        lst = next(b for b in blocks if b.kind == "list")
        self.assertIn("甲", lst.text)
        self.assertIn("乙", lst.text)

    def test_code_block_kept(self):
        art = W.parse_content("# T\n\n## 01 节\n\n```\nprint(1)\n```\n", ".")
        blocks = G.parse_preview_blocks(W.render_html(art, W.THEMES["business"]))
        self.assertTrue(any(b.kind == "code" for b in blocks))


class TestRoundtripWithNewMarkup(unittest.TestCase):
    def test_list_and_figure_survive(self):
        src = open(os.path.join(EX, "bear.md"), encoding="utf-8").read()
        art = W.parse_content(src, EX)
        W.normalize(art, want_summary=True, want_cta=True, want_end=True)
        tpl = W.render_markdown(art, "business", W.THEMES["business"])
        art2 = W.parse_content(tpl, EX)
        self.assertEqual(len(art.sections), len(art2.sections))
        real1 = [i for i in art.images if not i.path.startswith("图片路径")]
        real2 = [i for i in art2.images if not i.path.startswith("图片路径")]
        self.assertEqual(len(real1), len(real2))
        # 列表仍然存在（①②③ 还原成列表）
        self.assertTrue(any(b.kind == "list" for b in art2.all_blocks()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
