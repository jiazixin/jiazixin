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
}


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
        cells.append(
            f'<tr>\n<td width="64" align="center" valign="middle">\n'
            f'<img src="{p["logo"]}" width="44" alt="">\n'
            f"</td>\n<td>\n"
            f'<a href="https://github.com/{repo}"><b>{p["title"]}</b></a><br>\n'
            f'{p["desc"]}<br>\n'
            + "\n".join(badges)
            + "\n</td>\n</tr>"
        )
    return "<table>\n" + "\n".join(cells) + "\n</table>"


def render_watching(groups):
    # 两列：分组可用 "col": 0/1 指定列，否则放进当前更短的那一列
    cols, heights = [[], []], [0, 0]
    for g in groups:
        lines = []
        for repo, desc in g["repos"]:
            owner, name = repo.split("/")
            try:
                stars = "★&nbsp;" + fmt_stars(api(f"repos/{repo}")["stargazers_count"])
            except Exception:
                stars = ""
            lines.append(
                f'<img src="https://github.com/{owner}.png?size=40" width="16" height="16" alt=""> '
                f'<a href="https://github.com/{repo}"><b>{name}</b></a> · {desc} <sub><code>{stars}</code></sub>'
            )
        block = f"<h4>{g['name']}</h4>\n" + "<br>\n".join(lines)
        i = g.get("col", 0 if heights[0] <= heights[1] else 1)
        cols[i].append(block)
        heights[i] += len(g["repos"]) * 1.6 + 2
    tds = [f'<td width="50%" valign="top">\n\n' + "\n\n".join(c) + "\n\n</td>" for c in cols]
    return "<table>\n<tr>\n" + "\n".join(tds) + "\n</tr>\n</table>"


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
