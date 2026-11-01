# Release 说明 · v0.1.0

> 用法：打开 <https://github.com/SinWrong/wechat-md/releases/new?tag=v0.1.0>，
> 标题填 `v0.1.0：公众号排版工具首个版本`，把下面的正文粘进去，勾选 **Set as the latest release**，发布。

## 正文

首个公开版本：把「文案 + 图片」变成公众号能直接用的排版。

```markdown
## 这个版本能做什么

- **命令行**：`python tools/wechat_md.py 文案.md -o 输出.md --html 输出.html`
- **桌面编辑器**：`wechat_md_gui.bat`，左边写稿、右边实时手机预览
- **多格式输入**：`.md` `.txt`（GBK/BOM）、`.html`（含公众号文章页）、`.docx`（图片自动抽出）
- **三套主题**：商务蓝 / 新闻红 / 暖橙
- **发布前体检**：标题、结论卡、编号、图注、段长、结尾组件逐条检查
- **AI 提示词**：`prompts/` 里是对大模型的格式约束，生成即可导入

## 快速开始

```bash
git clone git@github.com:SinWrong/wechat-md.git
cd wechat-md
python tools/wechat_md.py examples/bear.md -o 输出.md --html 输出.html
python tools/wechat_md_gui.py examples/bear.md      # 桌面编辑器
```

需要 Python 3.8+，零第三方依赖（GUI 预览 JPG 可选 Pillow）。

## 已知限制

- 公众号后台会过滤外链图片，粘贴后需重新上传；
- 不支持旧版 `.doc`，请先另存为 `.docx`；
- 预览是模拟渲染，最终效果以保存后的手机预览为准。

## 验证

- 70 项单元测试通过；
- CI：Ubuntu + Windows × Python 3.8 / 3.11 / 3.12 全绿。
```

## 附件

不需要传二进制。如果以后想给「不想装 Python」的人用，可以再打一个 PyInstaller 的 exe 包。
