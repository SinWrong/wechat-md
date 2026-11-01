# 更新日志

版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)：`主版本.次版本.修订号`。

## v0.1.0（2026-11-01）

首个公开版本。

### 命令行

- `tools/wechat_md.py`：把文案渲染成 Markdown 模板、可粘贴 HTML、手机宽度预览页；
- 三套主题：商务蓝 / 新闻红 / 暖橙，字距、标题样式、代码配色随主题；
- 参数：`--theme`、`--summary`、`--html`、`--preview`、`--images`、`--from`、`--title`、`--config`、`--list-formats`。

### 多格式输入

- `tools/convert.py`：
  - `.md` `.txt`：自动识别 UTF-8 / GBK / Big5 / BOM；
  - `.html`：支持公众号文章页（只取 `#js_content`，过滤导航、工具条、隐藏块）与普通网页（`<article>` / `<main>`）；
  - `.docx`：按标题样式分小节，图片自动抽到同目录 `imgs/`；
- 生成后的模板可以再次喂回程序：注释、附录、Markdown 图片、`[CTA]`/`[END]` 都能正确还原。

### 排版能力

- 正文 16px / 行高 1.75 / 段后 16px / 字距 0.2–0.5px / `word-break`；
- 小标题三种样式：左竖条 / 下划线 / 居中；
- 图片用 `<figure>` + `<figcaption>`，图注贴图；
- 列表输出 `<ul>/<li>`，解析同时认 `- `、`1. `、`①–⑩`、`· `；
- 围栏代码块 `<pre><code>` 深色底；
- 行内格式：`**加粗**`、`` `行内代码` ``、`[文字](链接)`。

### 桌面编辑器

- `tools/wechat_md_gui.py`（Tk，标准库）：
  - 左侧写稿 + 右侧实时手机预览，可缩放；预览用 Canvas + 固定页宽，图文左右对齐；
  - 工具条插入小标题、结论卡、配图、引用、列表、互动、关注；
  - 配图对话框支持「复制到 imgs/」；光标在 `[IMG:…]` 行上可编辑该图；
  - `Ctrl+K` 发布前体检：标题长度、结论卡、编号重复、图片路径、图注缺失、段落过长、分隔线、结尾组件；
  - 打开 md / txt / html / docx，保存默认另存为 `.md`；批量转换。

### 提示词

- `prompts/公众号文案生成提示词.md`（完整版）与精简版：把本程序语法写成格式契约；
- `tools/check_prompt_output.py`：校验模型输出是否符合格式，输出「必须修 / 建议改」。

### 测试与 CI

- `tests/` 5 个文件、70 项测试：解析渲染、多格式转换、模板往返、提示词校验、插件特性；
- `.github/workflows/tests.yml`：Ubuntu + Windows × Python 3.8 / 3.11 / 3.12；
- `.github/workflows/build-exe.yml`：打 tag 时用 PyInstaller 构建 `wechat-md-gui.exe` 与 `wechat-md.exe`，
  压缩成 `wechat-md-windows-x64.zip` 并附到 Release。

### 发布

- Release：<https://github.com/SinWrong/wechat-md/releases/tag/v0.1.0>
- 文档站：<https://sinwrong.github.io/wechat-md/>（`site/`，由 `.github/workflows/pages.yml` 部署）

### 已知限制

- 公众号后台会过滤外链图片，粘贴后需重新上传；
- 不支持旧版 `.doc`；
- 预览是模拟渲染，最终效果以后台保存后的手机预览为准。
