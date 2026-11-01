# -*- coding: utf-8 -*-
"""提示词输出 / 校验器的回归测试。"""
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))

import check_prompt_output as K  # noqa: E402
import wechat_md as W            # noqa: E402

EX = os.path.join(BASE, "examples")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestGoodSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(os.path.join(EX, "prompt_sample.md"))
        cls.errors, cls.warns, cls.stats = K.check(cls.text)

    def test_no_errors(self):
        self.assertEqual(self.errors, [])

    def test_no_warnings(self):
        self.assertEqual(self.warns, [])

    def test_stats(self):
        self.assertEqual(self.stats["标题字数"], 30)
        self.assertEqual(self.stats["小节数"], 5)
        self.assertEqual(self.stats["图片数"], 1)

    def test_renders(self):
        art = W.parse_content(self.text, EX)
        W.normalize(art, want_summary=True, want_cta=True, want_end=True)
        md = W.render_markdown(art, "business", W.THEMES["business"])
        self.assertIn("> **先说结论**", md)
        self.assertIn("## 01 一头熊", md)
        self.assertEqual(md.count("## 写在最后"), 1)


class TestBadSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(os.path.join(EX, "bad_sample.md"))
        cls.errors, cls.warns, _ = K.check(cls.text)

    def test_errors_detected(self):
        joined = "\n".join(self.errors)
        self.assertIn("标题：", joined)
        self.assertIn("重复编号", joined)
        self.assertIn("编号不连续", joined)

    def test_warnings_detected(self):
        joined = "\n".join(self.warns)
        self.assertIn("分隔线", joined)
        self.assertIn("图注", joined)
        self.assertIn("CTA", joined)


class TestEdgeCases(unittest.TestCase):
    def test_empty(self):
        errors, _, _ = K.check("")
        self.assertTrue(errors)

    def test_missing_hash(self):
        errors, _, _ = K.check("一个没有井号的标题\n\n正文。\n")
        self.assertTrue(any("标题" in e for e in errors))

    def test_non_consecutive(self):
        text = "# 标题\n\n## 02 甲\n\n正文。\n\n## 04 乙\n\n正文。\n"
        errors, _, _ = K.check(text)
        self.assertTrue(any("编号不连续" in e for e in errors))

    def test_long_paragraph(self):
        text = "# 标题\n\n## 01 小节\n\n" + "啊" * 120 + "\n"
        _, warns, _ = K.check(text)
        self.assertTrue(any("段落" in w for w in warns))

    def test_duplicate_numbering(self):
        text = "# 标题\n\n## 01 01 重复\n\n正文。\n"
        errors, _, _ = K.check(text)
        self.assertTrue(any("重复编号" in e for e in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
