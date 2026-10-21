#!/usr/bin/env python3
"""根据 projects.json 重新生成 README 中两个标记区块：我的项目、关注的项目。

用法：GITHUB_TOKEN=xxx python3 scripts/update.py
没有 GITHUB_TOKEN 时会尝试 `gh auth token`，都没有也能跑（匿名额度 60 次/小时）。
"""
import html
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

CARDS = ROOT / "assets" / "cards"
# 卡片配色跟 banner.svg 一样写在 SVG 里，按 prefers-color-scheme 切换；取 GitHub Primer 的明暗色
PALETTE = {
    "light": dict(card="#f6f8fa", edge="#d1d9e0", mute="#59636e", ok="#1a7f37", line="#0969da"),
    "dark": dict(card="#151b23", edge="#3d444d", mute="#9198a1", ok="#3fb950", line="#4493f8"),
}
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC',sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
# Arial 字宽（单位 em，ASCII 32..126），SVG 里量不了文字，靠它估宽度来折行、摆版本号
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


def text_w(s, size, mono=False):
    """估算文字宽度：ASCII 按 Arial（等宽按 0.6em），中文和全角标点按 1em，再留 4% 余量。"""
    w = 0.0
    for c in s:
        if 32 <= ord(c) < 127:
            w += 0.6 if mono else ARIAL[ord(c) - 32]
        else:
            w += (0.6 if mono else 0.34) if c == "·" else 1.0
    return w * size * 1.04


def fit(s, size, width):
    if text_w(s, size) <= width:
        return s
    while s and text_w(s + "…", size) > width:
        s = s[:-1]
    return s.rstrip() + "…"


def wrap(s, size, width, max_lines=2):
    """按宽度折行：英文单词不拆开，行首不放中文标点，超出行数的部分截断加省略号。"""
    lines = [""]
    for t in re.findall(r"[A-Za-z0-9.\-_/+]+|\s+|.", s):
        if text_w((lines[-1] + t).rstrip(), size) <= width or not lines[-1].strip() or t in "，。：；、）":
            lines[-1] += t
        else:
            lines.append(t.lstrip())
    lines = [l.strip() for l in lines if l.strip()]
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [fit("".join(lines[max_lines - 1 :]), size, width)]
    return lines


def svg_doc(w, h, label, body):
    css = lambda p: ";".join(f"--{k}:{v}" for k, v in p.items())
    style = (
        f":root{{{css(PALETTE['light'])}}}@media (prefers-color-scheme:dark){{:root{{{css(PALETTE['dark'])}}}}}"
        ".card{fill:var(--card);stroke:var(--edge)}.mute{fill:var(--mute)}.ok{fill:var(--ok)}.lnk{fill:var(--line)}"
        ".pill{fill:var(--ok);fill-opacity:.12;stroke:var(--ok);stroke-opacity:.45}"
        ".contour{fill:none;stroke:var(--line);stroke-width:1.2;opacity:.16}"
        f".s{{font-family:{SANS}}}.m{{font-family:{MONO}}}"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{html.escape(label)}"><style>{style}</style>{body}</svg>\n'
    )


def logo(path, x, y, size):
    """把 assets/logos 里的方形 logo 原样嵌进卡片（图片里的 SVG 不能再引用外部文件）。"""
    m = re.search(r'<svg\b[^>]*?\bviewBox="([^"]+)"[^>]*>(.*)</svg>', (ROOT / path).read_text(encoding="utf-8"), re.S)
    return f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="{m[1]}">{m[2]}</svg>'


def stack_row(stack, x, y, size=12):
    out = []
    for key in stack:
        label, color = STACK[key]
        out.append(f'<circle cx="{x + 4:.1f}" cy="{y - size * 0.36:.1f}" r="4" fill="{color}"/>')
        out.append(f'<text class="s mute" x="{x + 13:.1f}" y="{y}" font-size="{size}">{label}</text>')
        x += 13 + text_w(label, size) + 14
    return "".join(out)


def tag_mark(tag, x, y, size=12, anchor="start"):
    """版本号前面带一个 tag 图标；anchor=end 时 x 是右端。"""
    if not tag:
        return ""
    x0 = x - 14 - text_w(tag, size, True) if anchor == "end" else x
    return (
        f'<path class="ok" transform="translate({x0:.1f} {y - size * 0.84:.1f}) scale({size / 16 * 0.85:.3f})" d="{TAG_ICON}"/>'
        f'<text class="m ok" x="{x0 + 14:.1f}" y="{y}" font-size="{size}">{html.escape(tag)}</text>'
    )


def card_wide(p, tag):
    """横跨整行的大卡：大 logo、标题旁一个版本胶囊，右侧铺 banner 同款等高线。"""
    w, h = 880, 176
    contours = "".join(
        f'<path d="M{w} {14 + i * 30} C{w - 90} {4 + i * 30} {w - 150} {64 + i * 30} {w - 230} {44 + i * 30} '
        f'S{w - 350} {i * 30 - 16} {w - 420} {i * 30 - 26}"/>'
        for i in range(7)
    )
    pill = ""
    if tag:
        px = 112 + text_w(p["title"], 22) + 14
        pill = (
            f'<rect class="pill" x="{px:.1f}" y="38.5" width="{32 + text_w(tag, 12, True):.1f}" height="23" rx="11.5"/>'
            + tag_mark(tag, px + 9, 55)
        )
    desc = "".join(
        f'<text class="s mute" x="112" y="{90 + i * 23}" font-size="15">{html.escape(line)}</text>'
        for i, line in enumerate(wrap(p["desc"], 15, 470))
    )
    body = (
        f'<clipPath id="c"><rect width="{w}" height="{h}" rx="14"/></clipPath>'
        f'<rect class="card" x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="14"/>'
        f'<g class="contour" clip-path="url(#c)">{contours}</g>'
        + logo(p["logo"], 28, 28, 64)
        + f'<text class="s lnk" x="112" y="56" font-size="22" font-weight="600">{html.escape(p["title"])}</text>'
        + pill
        + desc
        + stack_row(p.get("stack", []), 112, 146, 13)
    )
    return svg_doc(w, h, f'{p["title"]} — {p["desc"]}', body)


def card(p, tag):
    """半宽小卡，两张一排：logo、标题、右上角版本号，简介最多两行，底部技术栈。"""
    w, h = 430, 140
    desc = "".join(
        f'<text class="s mute" x="82" y="{64 + i * 20}" font-size="13.5">{html.escape(line)}</text>'
        for i, line in enumerate(wrap(p["desc"], 13.5, w - 82 - 22))
    )
    body = (
        f'<rect class="card" x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12"/>'
        + logo(p["logo"], 22, 22, 44)
        + f'<text class="s lnk" x="82" y="40" font-size="16" font-weight="600">{html.escape(p["title"])}</text>'
        + tag_mark(tag, w - 22, 39, 12, "end")
        + desc
        + stack_row(p.get("stack", []), 82, h - 22)
    )
    return svg_doc(w, h, f'{p["title"]} — {p["desc"]}', body)


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
    # featured 的项目用整行大卡排在最前，其余半宽卡两两一排；剩单个时最后一张也画成大卡，不留空位。
    # 不用表格：<p> 里的行内图片之间没有边框和斑马纹，半宽卡取 49% 加一个空格的间距正好一行两张，
    # 大卡取 98.6% 并整段居中，左右边缘和下面成对的小卡基本对齐
    wide = [p for p in items if p.get("featured")]
    half = [p for p in items if not p.get("featured")]
    tail = [half.pop()] if len(half) % 2 else []
    CARDS.mkdir(parents=True, exist_ok=True)
    written, imgs = set(), []
    for p, is_wide in [(p, True) for p in wide] + [(p, False) for p in half] + [(p, True) for p in tail]:
        repo = p["repo"]
        try:
            rel = api(f"repos/{repo}/releases?per_page=1")
            tag = rel[0]["tag_name"] if rel else None
        except Exception:
            tag = None
        name = repo.split("/")[1] + ".svg"
        (CARDS / name).write_text(card_wide(p, tag) if is_wide else card(p, tag), encoding="utf-8")
        written.add(name)
        alt = html.escape(f'{p["title"]} — {p["desc"]}', quote=True)
        imgs.append(
            f'<a href="https://github.com/{repo}"><img src="assets/cards/{name}" '
            f'width="{"98.6%" if is_wide else "49%"}" alt="{alt}"></a>'
        )
    for old in CARDS.glob("*.svg"):
        if old.name not in written:
            old.unlink()
    return '<p align="center">\n' + "\n".join(imgs) + "\n</p>"


def render_watching(groups):
    # 每个分组一张两列表格：标题行横跨两列，下面每行两个项目；每张表都用占位图撑满整栏，
    # 列宽一致所以上下仍然对齐，表与表之间空一行把分组隔开
    tables = []
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
        rows = [f'<tr>\n<th colspan="2" align="left">{SPACER}{g["name"]}</th>\n</tr>']
        rows += ["<tr>\n" + "\n".join(cells[i : i + 2]) + "\n</tr>" for i in range(0, len(cells), 2)]
        tables.append("<table>\n" + "\n".join(rows) + "\n</table>")
    return "\n<br>\n".join(tables)


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
