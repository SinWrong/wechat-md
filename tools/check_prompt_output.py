# -*- coding: utf-8 -*-
"""校验一份「按提示词生成」的文案是否符合本程序的格式约定。

用法：
    python tools/check_prompt_output.py 文案.md
    python tools/check_prompt_output.py 文案.md --strict   # 有警告也算失败

输出 0 表示能直接进程序；非 0 表示有问题（可直接给模型看）。
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wechat_md as W


def check(text: str) -> tuple:
    """返回 (errors, warnings, stats)"""
    errors: list = []
    warns: list = []
    lines = text.replace("\r\n", "\n").split("\n")
    nonempty = [ln.strip() for ln in lines if ln.strip()]

    if not nonempty:
        return ["文案是空的"], [], {}

    # 1. 标题
    first = nonempty[0]
    if first.startswith("# "):
        title = first[2:].strip()
    elif first.startswith("#"):
        errors.append("第一行标题要用「# 标题」（# 后有一个空格）")
        title = first.lstrip("#").strip()
    else:
        errors.append("第一行不是标题：应以「# 标题」开头")
        title = first
    if not title:
        errors.append("标题为空")
    elif len(title) > 30:
        warns.append(f"标题 {len(title)} 字，建议 ≤30 字")
    if re.match(r"^(标题|题目)\s*[:：]", title):
        errors.append("标题不要带「标题：」前缀")

    # 2. 结论卡
    if "## 先说结论" not in text:
        warns.append("没有「## 先说结论」，编辑器会替你生成一句占位，建议自己写 3 条")
    else:
        block = text.split("## 先说结论", 1)[1].split("\n## ", 1)[0]
        bullets = [ln for ln in block.split("\n") if ln.strip().startswith("> ·")]
        if len(bullets) != 3:
            warns.append(f"结论卡应有 3 条「> · 」，当前 {len(bullets)} 条")
        for b in bullets:
            body = b.strip().lstrip(">").strip().lstrip("·").strip()
            if len(body) > 26:
                warns.append(f"结论条偏长（{len(body)} 字）：{body[:18]}…")

    # 3. 小节
    secs = [ln for ln in lines if re.match(r"^##\s+\d", ln.strip())]
    if len(secs) < 2:
        warns.append(f"小节数量 {len(secs)} 个，建议 3–5 个")
    nums = []
    for s in secs:
        m = re.match(r"^##\s+(\d{1,2})\s*(.*)$", s.strip())
        nums.append(int(m.group(1)))
        title_s = m.group(2)
        if len(title_s) > 22:
            warns.append(f"小节标题偏长（{len(title_s)} 字）：{title_s}")
        if title_s.endswith(("？", "?")):
            warns.append(f"小节标题别用问号：{title_s}")
    if nums and nums != list(range(1, len(nums) + 1)):
        errors.append(f"小节编号不连续：{nums}（应从 01 开始递增）")
    if re.search(r"^##\s+\d{1,2}\s+\d{1,2}\s", text, flags=re.M):
        errors.append("出现「## 01 01」这种重复编号")

    # 4. 段落
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if not s or s[0] in "#>-[!" or s.startswith(("日期", "作者")):
            continue
        if len(s) > 90:
            warns.append(f"第 {i} 行段落 {len(s)} 字，建议 ≤55 字（最多 90）")

    # 5. 加粗与列表
    bolds = re.findall(r"\*\*(.+?)\*\*", text)
    if len(bolds) > 5:
        warns.append(f"加粗 {len(bolds)} 处，建议 ≤5 处")

    # 6. 图片
    for m in re.finditer(r"\[IMG:([^\]]*)\]", text):
        parts = [p.strip() for p in m.group(1).split("|")]
        line = text.count("\n", 0, m.start()) + 1
        if not parts[0]:
            errors.append(f"第 {line} 行图片标记缺少文件名")
        if len(parts) < 3 or not parts[2]:
            warns.append(f"第 {line} 行图片缺图注（第三段）")

    # 7. 分隔线
    dashes = len(re.findall(r"^---\s*$", text, flags=re.M))
    if dashes > 2:
        warns.append(f"分隔线 {dashes} 条，建议 ≤2 条（小节之间不用写）")

    # 8. 结尾
    if "[CTA]" not in text:
        warns.append("没有 [CTA]（互动提问）")
    if "[END]" not in text:
        warns.append("没有 [END]（关注引导）")
    if text.count("关注") > 3:
        warns.append(f"「关注」出现 {text.count('关注')} 次，建议只保留 1 次")
    if "写在最后" not in text:
        warns.append("没有「## 写在最后」收尾段")

    # 9. 程序能否解析
    art = W.parse_content(text, os.getcwd())
    if not art.sections:
        errors.append("解析后没有小节，检查「## 01 标题」写法")

    stats = {
        "标题字数": len(title),
        "小节数": len(art.sections),
        "正文字数": art.char_count(),
        "图片数": len(art.images),
        "加粗数": len(bolds),
    }
    return errors, warns, stats


def main(argv=None):
    import argparse
    # Windows 控制台默认 GBK，统一 UTF-8，避免 ✓ / ✖ 打印报错
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="校验提示词生成的文案格式")
    ap.add_argument("file", help="文案 .md 路径")
    ap.add_argument("--strict", action="store_true", help="把警告也当失败")
    args = ap.parse_args(argv)

    path = args.file
    if not os.path.exists(path):
        print(f"[错误] 文件不存在：{path}", file=sys.stderr)
        return 2
    try:
        import convert
        text = convert.read_text(path)
    except Exception:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()

    errors, warns, stats = check(text)
    print(f"文件：{path}")
    print("统计：" + "　".join(f"{k} {v}" for k, v in stats.items()) if stats else "")
    if errors:
        print("\n必须修：")
        for e in errors:
            print("  ✖", e)
    if warns:
        print("\n建议改：")
        for w in warns:
            print("  ▲", w)
    if not errors and not warns:
        print("\n✓ 格式没问题，可以直接导入。")
    elif not errors:
        print("\n✓ 没有硬错误，可以直接导入；上面几条建议改完更好。")
    bad = bool(errors) or (args.strict and bool(warns))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
