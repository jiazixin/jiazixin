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

# 技术栈小标签：(显示名, 颜色)，颜色取 GitHub linguist 的语言色
STACK = {
    "go": ("Go", "#00ADD8"),
    "react": ("React", "#61DAFB"),
    "vue": ("Vue 3", "#41B883"),
    "ts": ("TypeScript", "#3178C6"),
    "swift": ("Swift", "#F05138"),
    "kotlin": ("Kotlin", "#A97BFF"),
}

BADGES = ROOT / "assets" / "badges"
RELEASE_COLOR = "#2EA043"
# 文字用中性灰：README 里的 SVG 拿不到 GitHub 的明暗主题，这个灰在白底和深色底上都看得清
TEXT_COLOR = "#768390"
# Arial 字宽（单位 em，ASCII 32..126），配合 textLength 让各平台字体下标签宽度一致
ARIAL = [
    0.278, 0.278, 0.355, 0.556, 0.556, 0.889, 0.667, 0.191, 0.333, 0.333, 0.389, 0.584, 0.278, 0.333, 0.278, 0.278,
    0.556, 0.556, 0.556, 0.556, 0.556, 0.556, 0.556, 0.556, 0.556, 0.556, 0.278, 0.278, 0.584, 0.584, 0.584, 0.556,
    1.015, 0.667, 0.667, 0.722, 0.722, 0.667, 0.611, 0.778, 0.722, 0.278, 0.5, 0.667, 0.556, 0.833, 0.722, 0.778,
    0.667, 0.778, 0.722, 0.667, 0.611, 0.722, 0.667, 0.944, 0.667, 0.667, 0.611, 0.278, 0.278, 0.278, 0.469, 0.556,
    0.333, 0.556, 0.556, 0.5, 0.556, 0.556, 0.278, 0.556, 0.556, 0.222, 0.222, 0.5, 0.222, 0.833, 0.556, 0.556,
    0.556, 0.556, 0.333, 0.5, 0.278, 0.556, 0.5, 0.722, 0.5, 0.5, 0.5, 0.334, 0.26, 0.334, 0.584,
]
# Octicons tag-16（MIT）
TAG_ICON = (
    "M1 7.775V2.75C1 1.784 1.784 1 2.75 1h5.025c.464 0 .91.184 1.238.513l6.25 6.25a1.75 1.75 0 0 1 0 2.474l-5.026 "
    "5.026a1.75 1.75 0 0 1-2.474 0l-6.25-6.25A1.752 1.752 0 0 1 1 7.775Zm1.5 0c0 .066.026.13.073.177l6.25 6.25a.25.25 "
    "0 0 0 .354 0l5.025-5.025a.25.25 0 0 0 0-.354l-6.25-6.25a.25.25 0 0 0-.177-.073H2.75a.25.25 0 0 0-.25.25ZM6 5a1 1 "
    "0 1 1 0 2 1 1 0 0 1 0-2Z"
)
CHIP_H = 18
CHIP_FONT = 11


def chip(path, label, color, icon=None, text_color=TEXT_COLOR):
    """画一个圆角小标签：浅色描边 + 半透明底，左侧圆点或图标，写到 assets/badges。"""
    tw = round(sum(ARIAL[ord(c) - 32] if 32 <= ord(c) < 127 else 1 for c in label) * CHIP_FONT, 1)
    lead = 8 + (10 if icon else 6) + 5
    w = round(lead + tw + 8)
    mark = (
        f'<path transform="translate(8 4) scale(.625)" fill="{color}" d="{icon}"/>'
        if icon
        else f'<circle cx="11" cy="9" r="3" fill="{color}"/>'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{CHIP_H}" viewBox="0 0 {w} {CHIP_H}" role="img" aria-label="{label}">'
        f'<rect x=".5" y=".5" width="{w - 1}" height="{CHIP_H - 1}" rx="{(CHIP_H - 1) / 2}" fill="{color}" fill-opacity=".12" stroke="{color}" stroke-opacity=".45"/>'
        f"{mark}"
        f'<text x="{lead}" y="12.5" textLength="{tw}" lengthAdjust="spacingAndGlyphs" fill="{text_color}" '
        f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="{CHIP_FONT}">{label}</text>'
        "</svg>\n"
    )
    BADGES.mkdir(parents=True, exist_ok=True)
    (BADGES / path).write_text(svg, encoding="utf-8")
    return f"assets/badges/{path}"


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
        badges = []
        for key in p.get("stack", []):
            label, color = STACK[key]
            badges.append(f'<img src="{chip(f"{key}.svg", label, color)}" height="{CHIP_H}" alt="{label}">')
        if tag:
            src = chip(f"release-{repo.split('/')[1]}.svg", tag, RELEASE_COLOR, TAG_ICON, RELEASE_COLOR)
            badges.append(
                f'<a href="https://github.com/{repo}/releases"><img src="{src}" height="{CHIP_H}" alt="{tag}"></a>'
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
