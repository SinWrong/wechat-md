# 仓库 About 信息

GitHub 仓库右侧的 **About** 面板由三部分组成：Description、Topics、Website。这三项影响搜索结果和第一印象，建议按下文填写。

## Description（推荐）

```
公众号排版工具：文案 + 图片 → Markdown 模板 / 可粘贴 HTML。支持 md/txt/html/docx 输入、桌面编辑器实时预览、发布前体检与 AI 提示词，纯 Python 标准库。
```

> GitHub 限制 350 字符，上面这条 96 字符，留有余量。

### 备选

**英文版**

```
WeChat Official Account typesetting toolkit: copy + images → Markdown template / paste-ready HTML. CLI and desktop editor, multi-format input, pre-publish checks, zero dependencies.
```

**极简版**

```
把公众号文案排成统一版式：Markdown 模板 + 可粘贴 HTML，带桌面编辑器与发布前体检。
```

## Topics（最多 20 个，小写、连字符）

```
wechat
wechat-mp
wechat-official-account
markdown
typesetting
formatting
cli
tkinter
python
docx
html-to-markdown
content-tools
prompt-engineering
```

## Website

留空即可。如果以后有文档站（比如 GitHub Pages），再填站点地址。

## 怎么设置

### 网页

1. 打开 <https://github.com/SinWrong/wechat-md>；
2. 右侧 **About** → 点齿轮图标；
3. 粘贴 Description，把上面的 Topics 逐个加进去；
4. **Save changes**。

### GitHub CLI

```bash
gh repo edit SinWrong/wechat-md \
  --description "公众号排版工具：文案 + 图片 → Markdown 模板 / 可粘贴 HTML。支持 md/txt/html/docx 输入、桌面编辑器实时预览、发布前体检与 AI 提示词，纯 Python 标准库。" \
  --add-topic wechat \
  --add-topic wechat-mp \
  --add-topic wechat-official-account \
  --add-topic markdown \
  --add-topic typesetting \
  --add-topic formatting \
  --add-topic cli \
  --add-topic tkinter \
  --add-topic python \
  --add-topic docx \
  --add-topic html-to-markdown \
  --add-topic content-tools \
  --add-topic prompt-engineering
```

### REST API

```bash
curl -X PATCH \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/SinWrong/wechat-md \
  -d '{"description":"公众号排版工具：文案 + 图片 → Markdown 模板 / 可粘贴 HTML。","topics":["wechat","markdown","typesetting"]}'
```
