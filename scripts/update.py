#!/usr/bin/env python3
"""根据 projects.json 重新生成 README 中两个标记区块：我的项目、关注的项目。

用法：GITHUB_TOKEN=xxx python3 scripts/update.py
没有 GITHUB_TOKEN 时会尝试 `gh auth token`，都没有也能跑（匿名额度 60 次/小时）。
"""
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
DATA = ROOT / "projects.json"

STACK = {
    "go": "https://img.shields.io/badge/Go-00ADD8?style=flat-square&logo=go&logoColor=white",
    "react": "https://img.shields.io/badge/React-20232a?style=flat-square&logo=react&logoColor=61DAFB",
    "vue": "https://img.shields.io/badge/Vue_3-35495e?style=flat-square&logo=vuedotjs&logoColor=4FC08D",
    "ts": "https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white",
    "swift": "https://img.shields.io/badge/Swift-F05138?style=flat-square&logo=swift&logoColor=white",
    "kotlin": "https://img.shields.io/badge/Kotlin-7F52FF?style=flat-square&logo=kotlin&logoColor=white",
}

# 1px 透明占位图把表格撑满整栏（GitHub 的表格默认按内容收缩宽度）
SPACER = '<img src="assets/spacer.svg" width="2000" height="1" align="right" alt="">'


def token():
    if t := os.environ.get("GITHUB_TOKEN"):
        return t
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


TOKEN = token()


def api(path):
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={"Accept": "application/vnd.github+json"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def fmt_stars(n):
    if n >= 1000:
        s = f"{n / 1000:.1f}".removesuffix(".0") if n < 10000 else str(round(n / 1000))
        return s + "k"
    return str(n)


def render_mine(items):
    cells = []
    for p in items:
        repo = p["repo"]
        try:
            rel = api(f"repos/{repo}/releases?per_page=1")
            tag = rel[0]["tag_name"] if rel else None
        except Exception:
            tag = None
        badges = [f'<img src="{STACK[s]}" alt="{s}">' for s in p.get("stack", [])]
        if tag:
            label = tag.replace("-", "--").replace("_", "__")
            badges.append(
                f'<a href="https://github.com/{repo}/releases"><img src="https://img.shields.io/badge/release-{label}-1a7f37?style=flat-square" alt="{tag}"></a>'
            )
        # logo 是 44x96 的高图（logo 贴顶，与标题平齐），占住左侧整列，简介折行也会对齐在右边
        cells.append(
            f'<td width="50%" valign="top">\n'
            + (SPACER + "\n" if not cells else "")
            + f'<img src="{p["logo"]}" width="44" height="96" align="left" alt="">\n'
            f'<a href="https://github.com/{repo}"><b>{p["title"]}</b></a><br>\n'
            + "\n".join(badges)
            + f'<br>\n<sub>{p["desc"]}</sub>\n'
            "</td>"
        )
    if len(cells) % 2:
        cells.append('<td width="50%"></td>')
    rows = ["<tr>\n" + "\n".join(cells[i : i + 2]) + "\n</tr>" for i in range(0, len(cells), 2)]
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def render_watching(groups):
    # 一张两列表格：每个分组一个 tbody，标题行横跨两列，下面每行两个项目，保证全表对齐
    bodies = []
    for g in groups:
        cells = []
        for repo, desc, *display in g["repos"]:
            owner, name = repo.split("/")
            try:
                stars = "★&nbsp;" + fmt_stars(api(f"repos/{repo}")["stargazers_count"])
            except Exception:
                stars = ""
            cells.append(
                f'<td width="50%" valign="top">\n'
                f'<img src="https://github.com/{owner}.png?size=64" width="32" height="32" align="left" alt="">\n'
                f'<a href="https://github.com/{repo}"><b>{display[0] if display else name}</b></a>&nbsp;&nbsp;<sub>{stars}</sub><br>\n'
                f"<sub>{desc}</sub>\n"
                f"</td>"
            )
        if len(cells) % 2:
            cells.append('<td width="50%"></td>')
        spacer = SPACER if not bodies else ""
        rows = [f'<tr>\n<th colspan="2" align="left">{spacer}{g["name"]}</th>\n</tr>']
        rows += ["<tr>\n" + "\n".join(cells[i : i + 2]) + "\n</tr>" for i in range(0, len(cells), 2)]
        bodies.append("<tbody>\n" + "\n".join(rows) + "\n</tbody>")
    return "<table>\n" + "\n".join(bodies) + "\n</table>"


def replace(text, key, body):
    pat = re.compile(rf"(<!-- {key}:START -->\n)(?:.*?\n)?(<!-- {key}:END -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"README 缺少 {key} 标记")
    return pat.sub(lambda m: m.group(1) + body + "\n" + m.group(2), text)


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    text = README.read_text(encoding="utf-8")
    text = replace(text, "MINE", render_mine(data["mine"]))
    text = replace(text, "WATCHING", render_watching(data["watching"]))
    README.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
