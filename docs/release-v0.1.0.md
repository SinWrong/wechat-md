# 发布记录

## v0.1.0（已发布）

- Release：<https://github.com/SinWrong/wechat-md/releases/tag/v0.1.0>
- 资产：`wechat-md-windows-x64.zip`（25.7 MB，含 `wechat-md-gui.exe` + `wechat-md.exe`）
- Release 正文：[docs/release-notes/v0.1.0.md](release-notes/v0.1.0.md)

### 发布流程（以后打新版本照做）

1. 在 `CHANGELOG.md` 增加 `## vX.Y.Z（日期）`；
2. 新建 `docs/release-notes/vX.Y.Z.md`，写这一版给用户看的内容；
3. 提交并推 `main`；
4. 打标签并推送：

```bash
git tag -a vX.Y.Z -m "vX.Y.Z：一句话说明"
git push origin vX.Y.Z
```

5. `build-exe` 工作流会自动构建 exe、打包、创建 Release 并把 zip 附上去；
   Release 正文取自 `docs/release-notes/<tag>.md`，所以第 2 步不能漏。

### 注意

- 标签名要和 `docs/release-notes/` 里的文件名完全一致（`v0.1.0` ↔ `v0.1.0.md`），否则工作流会在「Attach to release」这步报找不到文件；
- 重新打同一个 tag 需要先删除远端标签：`git push origin :refs/tags/vX.Y.Z`。
