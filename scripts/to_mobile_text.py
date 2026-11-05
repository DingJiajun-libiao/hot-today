#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「平台热点速览」Markdown 日报渲染成适合手机阅读的纯文本（精简版）。

规格（见 AGENTS.md 第七节）:
    - GitHub：每个项目三行——项目名 / 「语言 · 今日增长 ★」/ 一句话简介，避免长行在手机上乱折
    - 微博 / 抖音 / 小红书 / AIHOT: 仅标题
    - 不含链接、热度值、详解正文、横向观察
    - 单条约 2k 字符，通常 1-2 段发完

用法:
    python scripts/to_mobile_text.py doc/平台热点速览-2026-11-05.md
    python scripts/to_mobile_text.py <md> --out <txt> --limit 1800

输出:
    同目录 `平台热点速览-YYYY-MM-DD.mobile.txt`，超长时按段切分，
    段间用 `──── 段 N/M ────` 分隔（push_wechat.py 依赖该分隔符）。
"""

import argparse
import os
import re
import sys

DESC_MAX = 40  # GitHub 一句话简介截断长度
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

# Windows 控制台默认 GBK,中文/emoji 直出会 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def strip_md(s):
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


def cell_text(cell):
    """'[标题](url)' -> '标题'（丢弃链接，手机版不要 URL）"""
    m = re.search(r"\[([^\]]+)\]\([^)]*\)", cell)
    if m:
        return strip_md(m.group(1))
    return strip_md(cell)


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_sep_row(cells):
    return all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells)


def is_rank(cell):
    return bool(re.fullmatch(r"(🥇|🥈|🥉|\d+)", (cell or "").strip()))


def rank_of(cell):
    token = (cell or "").strip()
    return {"🥇": "1", "🥈": "2", "🥉": "3"}.get(token, token)


def parse(md):
    """返回 [(kind, payload)]；kind ∈ title/date/section/row/note"""
    lines = md.splitlines()
    blocks = []
    sec = None
    in_table = False
    skip_section = False
    note_sent = False

    for raw in lines:
        line = raw.rstrip()

        if line.startswith("# "):
            blocks.append(("title", strip_md(line[2:])))
            continue

        # 日期行（md 里是 **2026 年 11 月 5 日 · 星期四**）
        m = re.fullmatch(r"\*\*(\d{4} 年[^*]*)\*\*", line.strip())
        if m and not any(k == "date" for k, _ in blocks):
            blocks.append(("date", strip_md(m.group(1))))
            continue

        if line.startswith("## "):
            sec = strip_md(line[3:])
            sec = re.sub(r"^[📑📊🔗\U0001F300-\U0001FAFF\s]+", "", sec)
            # 手机版不收录的章节
            skip_section = any(k in sec for k in ("目录", "今日速览", "跨平台", "横向观察"))
            in_table = False
            if not skip_section:
                blocks.append(("section", sec))
            continue

        if line.startswith("### "):
            in_table = False
            continue

        if not line.strip() or re.fullmatch(r"-{3,}", line.strip()):
            continue

        # 目录项 / 引用行
        if re.match(r"^-\s*\[[^\]]+\]\(#[^)]*\)\s*$", line.strip()):
            continue
        if line.strip().startswith("> "):
            continue

        if line.startswith("|"):
            cells = split_row(line)
            if is_sep_row(cells):
                in_table = True
                continue
            if in_table and not skip_section:
                blocks.append(("row", (sec, cells)))
            continue
        in_table = False

        # 段落：只保留「数据暂不可用」这类必要说明，且只保留一条，其余详解丢弃
        text = strip_md(line)
        if not text:
            continue
        if "小红书" in (sec or "") and ("不可用" in text or "失败" in text or "500" in text):
            if not note_sent:
                note_sent = True
                blocks.append(("note", "该平台数据本轮获取失败"))
        continue

    return blocks


def render_brief(blocks):
    out = []
    last_section = None
    for kind, payload in blocks:
        if kind == "title":
            out.append("🔥 平台热点速览" if "速览" in payload else payload)
        elif kind == "date":
            out.append(payload)
            out.append("")
        elif kind == "section":
            name = payload
            name = re.sub(r"^[一二三四五六七八九十]+、", "", name).strip()
            out.append("")
            out.append(f"━━ {name} ━━")
            last_section = name
        elif kind == "row":
            sec, cells = payload
            name = sec or last_section or ""

            if "GitHub" in name:
                if len(cells) < 6 or not is_rank(cells[0]):
                    continue
                repo = cell_text(cells[1])
                lang = strip_md(cells[2])
                delta = strip_md(cells[4]).replace("🔺", "").strip()
                desc = strip_md(cells[5])
                if len(desc) > DESC_MAX:
                    desc = desc[:DESC_MAX].rstrip(" ，,。.") + "…"
                # 手机窄屏：项目名单独一行，语言/今日增长一行，简介一行，避免长行乱折
                out.append(f"{rank_of(cells[0])}. {repo}")
                meta_parts = [lang] if lang else []
                if delta and delta not in ("—", "-", "--"):
                    meta_parts.append(f"今日 {delta} ★")
                if meta_parts:
                    out.append("   " + " · ".join(meta_parts))
                if desc:
                    out.append(f"   {desc}")
                continue

            if len(cells) < 2 or not is_rank(cells[0]):
                continue
            title = cell_text(cells[1])
            out.append(f"{rank_of(cells[0])}. {title}")
        elif kind == "note":
            if out and not out[-1].startswith("━━"):
                out.append("")
            out.append("⚠️ " + payload)
    return out


def tidy(lines):
    out = []
    blank = 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank > 1:
                continue
            out.append("")
        else:
            blank = 0
            out.append(ln.rstrip())
    while out and not out[-1].strip():
        out.pop()
    return out


def chunk(lines, limit):
    """按字符数切段，尽量在「━━ 章节 ━━」边界处断开。"""
    parts, buf = [], []
    size = 0
    last_head = -1

    def bufsize(b):
        return sum(len(x) + 1 for x in b)

    for ln in lines:
        if ln.startswith("━━"):
            last_head = len(buf)
        add = len(ln) + (1 if buf else 0)
        if buf and size + add > limit:
            cut = last_head if 0 < last_head < len(buf) else len(buf)
            parts.append(buf[:cut])
            buf = buf[cut:]
            size = bufsize(buf)
            last_head = -1
            add = len(ln) + (1 if buf else 0)
        buf.append(ln)
        size += add
    if buf:
        parts.append(buf)
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=1800, help="每段最大字符数")
    args = ap.parse_args()

    if not os.path.exists(args.md):
        print(f"[error] 找不到 {args.md}", file=sys.stderr)
        return 2

    md = open(args.md, encoding="utf-8").read()
    lines = tidy(render_brief(parse(md)))
    if not lines:
        print("[error] 渲染结果为空", file=sys.stderr)
        return 3

    parts = chunk(lines, args.limit)
    total = len(parts)
    body = []
    for n, p in enumerate(parts, 1):
        body.append(f"──── 段 {n}/{total} ────")
        body.extend(p)
        body.append("")
    text = "\n".join(body).rstrip() + "\n"

    out = args.out or os.path.splitext(args.md)[0] + ".mobile.txt"
    open(out, "w", encoding="utf-8", newline="\n").write(text)

    print(f"[ok] {out}")
    print(f"[info] 字符数={len(text)} 段数={total} 每段上限={args.limit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
