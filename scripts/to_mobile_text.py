#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「平台热点速览」Markdown 日报渲染成适合手机阅读的纯文本。

用法:
    python scripts/to_mobile_text.py 平台热点速览-2026-11-05.md
    python scripts/to_mobile_text.py <md> --out <txt> --width 30 --limit 1500

输出:
    同目录 `平台热点速览-YYYY-MM-DD.mobile.txt`，按段切分(每段 ≤ limit 字符)，
    段与段之间用 `──── 段 N/M ────` 分隔，便于 IM 逐条发送。

设计取舍:
    - 手机版只保留「热点名」级别的信息，不带任何链接
    - GitHub：项目名｜语言｜增长｜一句话简介
    - 微博 / 抖音 / 小红书 / AIHOT：仅热点标题
    - 热度值、详解正文、横向观察不进入手机版（完整内容见 .md）
"""

import argparse
import os
import re
import sys

# Windows 控制台默认 GBK,中文/emoji 直出会 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def strip_md(s):
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


def cell_link(cell):
    """'[标题](url)' -> (标题, url)"""
    m = re.search(r"\[([^\]]+)\]\(([^)]+)\)", cell)
    if m:
        return strip_md(m.group(1)), m.group(2)
    return strip_md(cell), ""


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_sep_row(cells):
    return all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells)


def parse(md):
    lines = md.splitlines()
    out = []          # [(kind, text)]
    date_line = ""
    sec = None        # 当前二级标题
    in_table = False
    pending_detail = None

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        i += 1

        if line.startswith("# "):
            out.append(("title", strip_md(line[2:])))
            continue
        if re.fullmatch(r"\*\*\d{4}.*\*\*", line.strip()) or re.fullmatch(
            r"^.{0,4}\d{4} 年.*星期.*$", strip_md(line)
        ):
            if not date_line and "年" in line and "星期" in line:
                date_line = strip_md(line)
                out.append(("date", date_line))
            continue
        if line.startswith("## "):
            sec = strip_md(line[3:])
            sec = re.sub(r"^[📑📊🔗\U0001F300-\U0001FAFF\s]+", "", sec)
            pending_detail = None
            in_table = False
            continue
        if line.startswith("### "):
            pending_detail = strip_md(line[4:])
            in_table = False
            continue

        if line.startswith("|"):
            cells = split_row(line)
            if is_sep_row(cells):
                in_table = True
                continue
            if in_table:
                out.append(("row", (sec, cells)))
            continue
        in_table = False

        # 详解条目标题行: **N. 标题** — 热度
        m = re.match(r"^\*\*(\d+)\.\s*(.+?)\*\*\s*(?:—|–|-)\s*(.+)$", line.strip())
        if m:
            out.append(
                ("item_head", (pending_detail or "", m.group(1), strip_md(m.group(2)), strip_md(m.group(3))))
            )
            continue

        if not line.strip():
            continue
        # 跳过目录项
        if re.match(r"^-\s*\[[^\]]+\]\(#[^)]*\)\s*$", line.strip()):
            continue
        s = strip_md(line)
        if not s or s == "---":
            continue
        if s.startswith("> "):
            s = s[2:]
        out.append(("para", (pending_detail or sec or "", s)))

    return out


def render(blocks):
    """手机版只保留「热点名」级别的信息：不带任何链接、热度与详解正文。

    - GitHub：`项目名｜语言｜增长｜一句话简介`
    - 微博 / 抖音 / 小红书 / AIHOT：仅热点标题
    """
    lines = []
    cur_sec = None
    sec_printed = False
    github = False
    failed_note = False

    for kind, payload in blocks:
        if kind == "title":
            lines.append(payload)
            continue
        if kind == "date":
            lines.append(payload)
            lines.append("")
            continue
        if kind == "row":
            sec, cells = payload
            sec_name = sec or ""
            if not sec_name or "今日速览" in sec_name or "跨平台" in sec_name or "目录" in sec_name:
                continue
            if sec_name != cur_sec:
                cur_sec = sec_name
                sec_printed = False
                github = "GitHub" in sec_name
            if not sec_printed:
                lines.append("")
                lines.append(f"━━ {sec_name} ━━")
                sec_printed = True
            if len(cells) < 2:
                continue
            rank = {"🥇": "1", "🥈": "2", "🥉": "3"}.get(cells[0], cells[0])
            if not re.fullmatch(r"\d+", rank or ""):
                # 非榜单表格（如小红书失败说明），明细行不进入手机版
                continue
            if github:
                # # | 项目 | 语言 | 总星标 | 增长 | 一句话简介
                name = cell_link(cells[1])[0]
                lang = strip_md(cells[2]) if len(cells) > 2 else ""
                delta = strip_md(cells[4]).replace("🔺", "").strip() if len(cells) > 4 else ""
                intro = strip_md(cells[5]) if len(cells) > 5 else ""
                piece = f"{rank}. {name}"
                for part in (lang, delta, intro):
                    if part:
                        piece += f"｜{part}"
                lines.append(piece)
            else:
                # 微博 / 抖音 / 小红书 / AIHOT：只要标题
                lines.append(f"{rank}. {cell_link(cells[1])[0]}")
            continue
        if kind == "para":
            sec_name, text = payload
            sec_name = sec_name or ""
            if "小红书" in sec_name and ("失败" in text or "暂不可用" in text):
                if not failed_note:
                    failed_note = True
                    if sec_name != cur_sec:
                        cur_sec, sec_printed, github = sec_name, False, False
                    if not sec_printed:
                        lines.append("")
                        lines.append(f"━━ {sec_name} ━━")
                        sec_printed = True
                    lines.append("⚠️ 该平台数据本轮获取失败")
            continue
    return lines


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
    last_head = -1  # buf 中最近一个章节标题的下标

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
    ap.add_argument("--limit", type=int, default=1400, help="每段最大字符数")
    args = ap.parse_args()

    if not os.path.exists(args.md):
        print(f"[error] 找不到 {args.md}", file=sys.stderr)
        return 2

    md = open(args.md, encoding="utf-8").read()
    lines = tidy(render(parse(md)))
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

    out = args.out
    if not out:
        base = os.path.splitext(args.md)[0]
        out = base + ".mobile.txt"
    open(out, "w", encoding="utf-8", newline="\n").write(text)

    print(f"[ok] {out}")
    print(f"[info] 字符数={len(text)} 段数={total} 每段上限={args.limit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
