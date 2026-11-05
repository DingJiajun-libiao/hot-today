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
    - 表格转「行式」，去掉 Markdown 符号(微信不渲染表格/粗体)
    - 微博/抖音的搜索链接是长串百分号编码，手机上不可读，默认省略；
      GitHub / AIHOT 的链接短且可读，保留
    - 详解正文过长，手机版只保留榜单与观察；完整详解仍在 .md 里
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


def render(blocks, keep_url_platforms=("github", "aihot")):
    lines = []
    cur_table = None
    keep = {}
    for kind, payload in blocks:
        if kind == "title":
            lines.append(payload)
        elif kind == "date":
            lines.append(payload)
            lines.append("")
        elif kind == "row":
            sec, cells = payload
            sec_name = (sec or "")
            if "今日速览" in sec_name:
                if cur_table != "summary":
                    lines.append("")
                    lines.append("【今日速览】")
                    cur_table = "summary"
                # 平台 | 榜首 | 热度 | 关键词
                plat = cells[0]
                title, _ = cell_link(cells[1]) if len(cells) > 1 else ("", "")
                extra = cells[1] if len(cells) > 1 else ""
                growth = re.search(r"\(([^)]*★)\)", extra)
                heat = cells[2] if len(cells) > 2 else ""
                badge = f" {growth.group(1)}" if growth else ""
                if heat and heat != "—":
                    lines.append(f"{plat}｜{title}{badge}｜{heat}")
                else:
                    lines.append(f"{plat}｜{title}{badge}")
                continue
            # 非榜单表格(如「跨平台热点」「小红书失败说明」)：合并成一行
            if len(cells) < 3 or not re.fullmatch(r"(🥇|🥈|🥉|\d+)", cells[0] or ""):
                if cur_table != sec_name:
                    lines.append("")
                    lines.append(f"━━ {sec_name} ━━")
                    cur_table = sec_name
                pieces = [strip_md(c) for c in cells if c and c != "—"]
                if pieces:
                    lines.append("· " + "｜".join(pieces))
                continue

            # 榜单表格
            if cur_table != sec_name:
                lines.append("")
                lines.append(f"━━ {sec_name} ━━")
                cur_table = sec_name
            keep_url = any(k in sec_name.lower() for k in keep_url_platforms)

            if "GitHub" in sec_name:
                # # | 项目 | 语言 | 星标 | 增长 | 简介
                rank, name_c, lang, stars, delta = cells[0], cells[1], cells[2], cells[3], cells[4]
                name, url = cell_link(name_c)
                mark = {"🥇": "1", "🥈": "2", "🥉": "3"}.get(rank, rank)
                d = delta.replace("🔺", "").strip()
                piece = f"{mark}. {name}｜{lang}｜{stars}★｜{d}"
                if keep_url and url:
                    piece += f"\n   {url}"
                lines.append(piece)
            elif "AIHOT" in sec_name or "AI 行业热点" in sec_name:
                # # | 话题 | 印证度 | 首发源 | 分类
                rank, t_c, proof, src = cells[0], cells[1], cells[2], cells[3]
                title, url = cell_link(t_c)
                mark = {"🥇": "1", "🥈": "2", "🥉": "3"}.get(rank, rank)
                piece = f"{mark}. {title}（{proof}）"
                if keep_url and url:
                    piece += f"\n   {url}"
                lines.append(piece)
            else:
                # # | 话题 | 热度 | 分类  (微博/抖音)
                rank, t_c, heat = cells[0], cells[1], cells[2]
                title, url = cell_link(t_c)
                mark = {"🥇": "1", "🥈": "2", "🥉": "3"}.get(rank, rank)
                piece = f"{mark}. {title}｜{heat}"
                if keep_url and url:
                    piece += f"\n   {url}"
                lines.append(piece)
        elif kind == "item_head":
            sec_name, num, title, heat = payload
            if "横向观察" in sec_name:
                idx = int(num) - 1
                mark = CIRCLED[idx] if 0 <= idx < len(CIRCLED) else f"{num}."
                lines.append("")
                lines.append(f"{mark} {title}")
            # 详解标题行不单独输出（详解正文在手机版中省略）
        elif kind == "para":
            sec_name, text = payload
            if "横向观察" in sec_name:
                keep["obs"] = keep.get("obs", 0) + 1
                if keep["obs"] <= 3:
                    lines.append("")
                    lines.append(text)
                continue
            if "详解" in sec_name or len(text) > 200:
                # 手机版不收录长篇详解正文
                continue
            lines.append(text)
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
    if parts:
        parts[-1].append("")
        parts[-1].append(
            "〔完整详解与全部链接见：%s〕" % os.path.basename(args.md)
        )
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
