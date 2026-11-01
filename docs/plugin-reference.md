# 参考 wechat_tool_reverse（织页）的改造说明

**参考对象**：`E:\savepath\agent\wechat_tool_reverse`——一个本地优先、权限克制的公众号排版浏览器扩展，基于对「壹伴·小插件」12.4.2 的静态逆向分析独立实现。
**本程序**：命令行 `tools/wechat_md.py` + 桌面编辑器 `wechat_md_gui.py` + 多格式转换 `tools/convert.py`。

两者定位不同：织页是**在公众号后台编辑器里直接改 DOM** 的扩展；本程序是**离线生成模板 / HTML** 再粘贴。所以不能整体照搬，但它的排版引擎和导出器里有几处做法明显更专业，这次挑了 6 处吸收。

---

## 一、先看它做了什么（结构审计）

```
extension/src/shared/
├─ themes.js      7 套主题，每套 30+ 个 token（字号/行距/字距/强调色/代码色/表格色…）
├─ formatter.js   内联样式排版引擎，逐标签设置 style，快照 + 还原
├─ markdown.js    HTML → Markdown，支持标题/列表/引用/代码/表格/图注
└─ util.js        字数、阅读时间、URL 识别
extension/src/content/content.js   编辑器适配（ProseMirror / 旧版 ueditor）+ 组件插入
```

**值得注意的 6 个细节**

| # | 织页的做法 | 出处 |
| --- | --- | --- |
| 1 | 正文带 `letter-spacing`（0.2–0.5px），小标题字距略小 | `formatter.js` `styleParagraph` |
| 2 | 正文带 `word-break: break-word` + `overflow-wrap: break-word` | 同上 |
| 3 | 小标题三种样式：`bar`（左竖条）/ `underline`（下划线）/ `center` | `styleHeading` |
| 4 | 图片用 `<figure>` + `<figcaption>` 语义标签，图注 13px 灰色居中 | `styleImage` / `blockHtml` |
| 5 | 列表输出真正的 `<ul>/<li>`，不是 ①②③ 纯文本 | `formatter.js` `UL/LI` |
| 6 | 代码块 `<pre><code>` 深色底、等宽字体、`white-space: pre-wrap` | `formatter.js` `PRE` |

另外它还有：7 套主题、组件插入（提示框/关注卡片）、快照还原、只读微信连接、ProseMirror/ueditor 双适配。这些要么依赖浏览器环境，要么和「离线出模板」的定位不匹配，见第四节。

---

## 二、这次吸收了什么

### 1. 字距与断词（最影响长文观感）

之前正文只有 `font-size / line-height / margin`，中文长文在手机上会显得「挤」。现在每个主题带 `letter_spacing`：

| 主题 | 字距 | 标题样式 |
| --- | --- | --- |
| business 商务蓝 | 0.3px | 左竖条 |
| news 新闻红 | 0.2px | 下划线 |
| warm 暖橙 | 0.5px | 左竖条 |

正文、列表项、小程序标题都带 `letter-spacing`，并统一加 `word-break: break-word; overflow-wrap: break-word`——长链接、英文单词不会撑破手机屏幕。

### 2. 小标题三变体

`THEMES["news"]` 用小标题下划线，`business`/`warm` 用左竖条；`heading_style` 还可以设 `center`。换主题时版式会真的变，不只是换颜色。

### 3. 图片语义化：`<figure>` + `<figcaption>`

```html
<figure data-b="img" data-idx="0" style="…">
  <img src="…" alt="…" style="…">
  <figcaption style="margin: 8px 0 0; font-size: 12px; color: #888; text-align: center;">说明。　图源：某处</figcaption>
</figure>
```

好处：编辑器预览、第三方工具、浏览器阅读模式都能识别成「图 + 图注」；也顺手修掉了旧实现里图注是独立 `<p>`、容易被一起选中删除的问题。

### 4. 列表输出 `<ul>/<li>`

之前列表被渲染成 `① ② ③` 的 `<p>` 文本，现在输出真正的 `<ul><li>`。解析器同时认 `- ` / `1. ` / `①–⑩` / `· ` 四种前缀，「生成后的模板」再读回来也不会拼成一段。

### 5. 代码块

新增：

- 输入：Markdown 围栏代码块 ```` ```python … ``` ````；
- 输出：`<pre><code>` 深色底、等宽字体、`white-space: pre-wrap`，主题各有一套 `code_bg/code_text`；
- 预览：GUI 里用深色块渲染，等宽字体换行。

技术类、工具类文章以前只能贴图，现在可以直接贴代码。

### 6. 行内格式

`_rich()` 现在支持三种行内格式并统一转义：

| 写法 | 输出 |
| --- | --- |
| `**加粗**` | `<strong>` |
| `` `行内代码` `` | `<code>` 浅底小字号 |
| `[文字](链接)` | `<a>` 下划线、继承颜色 |

以前这些语法在 HTML 里会原样漏出星号/反引号。

---

## 三、没有照搬的部分，以及为什么

| 织页的能力 | 没做的原因 | 替代方案 |
| --- | --- | --- |
| 在公众号后台直接改 DOM | 本程序是离线生成，不注入后台；改 DOM 需要浏览器扩展权限 | 保持「HTML 全选复制 → 粘贴」的路子 |
| ProseMirror / ueditor 双适配 | 同上，粘贴时由微信编辑器自己解析 | 输出语义化 HTML（figure/ul/li/pre），编辑器识别率更高 |
| 7 套主题（墨青/暖纸/极简/杂志/科技/松间/暮色） | 主题是产品审美选择，照搬会稀释「趣闻寻录」的识别度 | 保留 3 套，但把 token 补全（字距/标题样式/代码色），要加新主题只需加一组色值 |
| 快照 + 一键还原内联样式 | 离线模式没有 DOM 可快照 | 编辑器打开文件时会保留原文件，另存为 `.md` 不覆盖；这就是天然的「还原」 |
| 只读微信连接（账号/最近文章/素材） | 依赖登录态和后台私有接口，且不属于「排版」范畴 | 不纳入 |
| 素材库（收藏选中文字） | 依赖 `chrome.storage` | 不纳入；文案本身就在 `.md` 里，更好管理 |
| 提示框/关注卡片等组件 | 目前模板的结论卡、引用块、收束卡已覆盖高频需求 | 需要时可在 `Block.kind` 里加一种，md/html/预览各写一个分支 |

---

## 四、实测效果

用同一篇含代码、列表、图注的样例 `examples/code_demo.md` 生成：

| 检查项 | 改造前 | 改造后 |
| --- | --- | --- |
| 正文字距 | 无 | `letter-spacing: 0.3px` |
| 长链接断行 | 可能溢出 | `word-break: break-word` |
| 小标题 | 只有左竖条 | 竖条 / 下划线 / 居中三选一 |
| 图片图注 | 独立 `<p>` | `<figure>` + `<figcaption>` |
| 列表 | `① ② ③` 文本 | `<ul><li>` |
| 代码块 | 不支持 | `<pre><code>` 深色块 |
| 行内代码/链接 | 原样漏出符号 | `<code>` / `<a>` |

编辑器预览里，代码块是深色圆角块、列表是逐行项目符号、图注贴在图片下方，与生成后的 HTML 一致。

---

## 五、测试

新增 `tests/test_plugin_features.py` 13 项：

- 段落 token（字距 / 断词）；
- 三种小标题样式（bar / underline / center）；
- 语义标签（`<ul><li>`、`<figure><figcaption>`、`<pre><code>`）；
- 行内格式（加粗 / 行内代码 / 链接）；
- 预览解析（figure→图块、ul→列表、code→代码块）；
- 与往返测试联动（新标记重新解析后结构不丢）。

当前 **70 项测试全部通过**。

---

## 六、一句话结论

织页的价值不在「它做了什么功能」，而在**它对公众号长文的排版参数更细**：字距、断词、标题变体、语义标签、代码/表格。这次把其中和「离线出模板」兼容的 6 处吸收进来，本程序的产出更接近一个成熟排版工具的水准；需要浏览器内实时改后台、素材库、微信只读连接的部分，仍然交给织页这类扩展更合适。

两者其实可以互补：**本程序负责「写和排」（离线、可批量、可版本管理），织页负责「贴进后台后的最后微调」**。如果以后想做浏览器扩展版，`tools/wechat_md.py` 的 `render_html()` 已经是现成的排版引擎，套一层 content script 就能用。
