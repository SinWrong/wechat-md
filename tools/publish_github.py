#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本仓库发布到 GitHub（创建仓库 + 推送）。

用法：
    # 方式一：token 放环境变量
    GITHUB_TOKEN=ghp_xxx python tools/publish_github.py --repo wechat-md --public

    # 方式二：token 放文件（脚本读完会提示，不会写入 git 配置）
    python tools/publish_github.py --token-file .token --repo wechat-md --public

说明：
- 只用标准库（urllib + subprocess），不需要 gh；
- token 只用于本次 HTTP 请求和一次 push，不写进 .git/config；
- 推送完成后，remote 会改成不带 token 的 https 地址。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
UA = "wechat-md-publish"


def _req(method: str, url: str, token: str, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", UA)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"message": body[:300]}
        return e.code, parsed


def get_user(token: str) -> str:
    status, data = _req("GET", f"{API}/user", token)
    if status != 200:
        raise SystemExit(f"token 无效或没有权限（HTTP {status}）：{data.get('message')}")
    return data.get("login", "")


def ensure_repo(token: str, owner: str, repo: str, private: bool, desc: str) -> str:
    status, data = _req("GET", f"{API}/repos/{owner}/{repo}", token)
    if status == 200:
        print(f"[i] 仓库已存在：{data.get('html_url')}")
        return data.get("clone_url") or f"https://github.com/{owner}/{repo}.git"
    if status != 404:
        raise SystemExit(f"查询仓库失败（HTTP {status}）：{data.get('message')}")

    status, data = _req("POST", f"{API}/user/repos", token, {
        "name": repo,
        "description": desc,
        "private": private,
        "has_issues": True,
        "has_wiki": False,
        "auto_init": False,
    })
    if status not in (200, 201):
        raise SystemExit(f"创建仓库失败（HTTP {status}）：{data.get('message')} / {data.get('errors')}")
    print(f"[+] 已创建：{data.get('html_url')}")
    return data.get("clone_url") or f"https://github.com/{owner}/{repo}.git"


def run(cmd, **kw):
    print("    $", " ".join(cmd))
    return subprocess.run(cmd, check=True, text=True, **kw)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="创建 GitHub 仓库并推送当前仓库")
    ap.add_argument("--repo", default="wechat-md", help="仓库名")
    ap.add_argument("--owner", default="", help="用户名/组织（默认取 token 对应账号）")
    ap.add_argument("--desc", default="公众号排版工具：文案 + 图片 → Markdown 模板 / 可粘贴 HTML，带桌面编辑器与发布前体检",
                    help="仓库描述")
    ap.add_argument("--public", action="store_true", help="公开仓库（默认私有）")
    ap.add_argument("--token-file", default="", help="token 文件路径")
    ap.add_argument("--branch", default="main", help="推送分支")
    args = ap.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token and args.token_file:
        with open(args.token_file, "r", encoding="utf-8") as f:
            token = f.read().strip()
    if not token:
        print("缺少 token：设置 GITHUB_TOKEN 环境变量，或用 --token-file 指定文件", file=sys.stderr)
        return 2

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    if not os.path.isdir(".git"):
        print("当前目录不是 git 仓库，请先在项目根目录执行 git init", file=sys.stderr)
        return 2
    if shutil.which("git") is None:
        print("没有找到 git 命令", file=sys.stderr)
        return 2

    owner = args.owner or get_user(token)
    print(f"[i] 账号：{owner}")

    clone_url = ensure_repo(token, owner, args.repo, not args.public, args.desc)
    authed = clone_url.replace("https://", f"https://x-access-token:{token}@")
    run(["git", "remote", "remove", "origin"], check=False)
    run(["git", "remote", "add", "origin", authed])
    run(["git", "push", "-u", "origin", args.branch])
    # 推送后把 remote 换回不带 token 的地址
    run(["git", "remote", "set-url", "origin", clone_url])
    print(f"\n[OK] https://github.com/{owner}/{args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
