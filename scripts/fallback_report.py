#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 fetch_trends.py 的原始 JSON 生成「保底版」中文 Markdown 日报。

用途（见 SKILL.md「交付优先」）:
    定时 / 无人值守任务中，先确保磁盘上有一份可交付的报告（文件存在且 >0），
    再由 Agent 按输出规范补全详解并覆盖它。

原则:
    - 只使用 raw JSON 里的真实数据，不编造热度、链接或解读；
    - 抓取失败的平台整节标注「数据暂不可用」并附 meta 错误摘要；
    - 目标文件已存在且大小 >0 时默认跳过（防止覆盖已完成的完整报告），--force 强制重写。

用法:
    python scripts/fallback_report.py trends_raw.json
    python scripts/fallback_report.py trends_raw.json --out 平台热点速览-2026-11-05.md --force

退出码:
    0 已写出一份报告（或已存在、跳过）
    2 参数 / 数据错误，未能写出
"""

import argparse
import io
import json
import os
import sys

# Windows 控制台默认 GBK，中文/emoji 直出会 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
PLATFORM_ORDER = ("github", "weibo", "douyin", "xhs", "aihot")
PLATFORM_ICON = {
    "github": "🐙", "weibo": "📱", "douyin": "🎬", "xhs": "📕", "aihot": "🤖",
}
PLATFORM_CN = {
    "github": "GitHub", "weibo": "微博", "douyin": "抖音",
    "xhs": "小红书", "aihot": "AIHOT",
}
CATEGORY_CN = {
    "ai-models": "模型", "ai-products": "产品", "industry": "产业",
    "paper": "论文", "tip": "教程", "opinion": "观点",
}
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def esc(value):
    """表格单元格转义：竖线、换行。"""
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def rank_cell(i):
    return MEDALS.get(i, str(i))


def fmt_num(value):
    """'6467' -> '6,467'；无法解析时原样返回。"""
    try:
        return "{:,}".format(int(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return str(value or "—") or "—"


def fmt_delta(value):
    try:
        n = int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return "—"
    return "{:+,}".format(n)


def fmt_hot(value):
    """1167851 -> '116.8 万'；12045068 -> '1,204.5 万'；字符串原样。"""
    try:
        n = int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return esc(value) or "—"
    if n >= 10000:
        return "{:,.1f} 万".format(n / 10000.0)
    return "{:,}".format(n)


def truncate(text, limit):
    text = text or ""
    return text if len(text) <= limit else text[:limit].rstrip(" ，,。.") + "…"


def platform_meta(raw, plat):
    return (raw.get("meta") or {}).get(plat) or {}


def requested(raw, plat):
    return plat in (raw.get("meta") or {}) or plat in (raw.get("platforms") or {})


def failure_block(plat, raw, date_label):
    meta = platform_meta(raw, plat)
    if not requested(raw, plat):
        return ["**⚠️ 本轮未抓取该平台（`--platform` 未包含）。**", ""]
    err = meta.get("error") or "未返回数据"
    tried = meta.get("attempts") or 0
    lines = [
        "**⚠️ 该平台数据本轮获取失败，本节不含任何数据。**",
        "",
        "| 项目 | 情况 |",
        "|:---|:---|",
        "| 失败时间 | %s |" % date_label,
        "| 尝试源数 | %s 个 |" % esc(tried or "—"),
        "| 错误摘要 | `%s` |" % esc(err),
        "",
    ]
    return lines


def github_rows(raw):
    gh = (raw.get("platforms") or {}).get("github") or {}
    daily = gh.get("daily") or []
    weekly = gh.get("weekly") or []
    rows = []
    for i, it in enumerate(daily[:10], 1):
        rows.append((rank_cell(i), it, False))
    if len(rows) < 10:
        for it in weekly[: 10 - len(rows)]:
            rows.append((rank_cell(len(rows) + 1), it, True))
    return rows


def render(raw):
    generated_at = raw.get("generated_at") or ""
    date_label = generated_at or "未知时间"
    day = generated_at[:10] if len(generated_at) >= 10 else ""
    try:
        y, m, d = (int(x) for x in day.split("-"))
        import datetime
        weekday = WEEKDAYS[datetime.date(y, m, d).weekday()]
        title_date = "%d 年 %d 月 %d 日 · %s" % (y, m, d, weekday)
    except Exception:
        title_date = date_label

    out = []
    w = out.append
    w("# 🔥 平台热点速览")
    w("")
    w('<div align="center">')
    w("")
    w("**%s**" % title_date)
    w("")
    w("GitHub · 微博 · 抖音 · 小红书 · AIHOT")
    w("")
    w("</div>")
    w("")
    w("> ⚠️ **保底版**：本文件由 `scripts/fallback_report.py` 从原始抓取数据直接生成，"
      "未包含逐条背景解读；Agent 应在此基础上补全并覆盖。判定交付成功的标准是"
      "**文件存在且大小 > 0**。")
    w("")
    w("---")
    w("")

    # 今日速览
    w("## 📊 今日速览")
    w("")
    w("| 平台 | 榜首热点 | 热度 | 今日关键词 |")
    w("|:---:|:---|:---:|:---:|")
    for plat in PLATFORM_ORDER:
        items = (raw.get("platforms") or {}).get(plat) or []
        if plat == "github":
            rows = github_rows(raw)
            if rows:
                it = rows[0][1]
                name = "[%s](%s)" % (esc(it.get("repo")), it.get("url") or "")
                hot = "总星 %s" % fmt_num(it.get("stars"))
                w("| %s GitHub | %s | %s | — |" % (PLATFORM_ICON[plat], name, hot))
                continue
        elif items:
            it = items[0]
            name = "[%s](%s)" % (esc(truncate(it.get("title"), 40)), it.get("link") or "")
            hot = fmt_hot(it.get("hot_value"))
            w("| %s %s | %s | %s | — |" % (PLATFORM_ICON[plat], PLATFORM_CN[plat], name, hot))
            continue
        missing = "数据暂不可用" if requested(raw, plat) else "本轮未抓取"
        w("| %s %s | %s | — | — |" % (PLATFORM_ICON[plat], PLATFORM_CN[plat], missing))
    w("")
    w("> 数据说明：抓取时间 %s。本文件为脚本保底版，未做跨平台解读；"
      "失败平台按 `meta` 如实标注，未用其他平台数据填充。" % esc(date_label))
    w("")
    w("---")
    w("")

    # 一、GitHub
    w("## 一、GitHub 趋势榜")
    w("")
    rows = github_rows(raw)
    if rows:
        w("| # | 项目 | 语言 | 总星标 | 增长 | 一句话简介 |")
        w("|:---:|:---|:---:|---:|:---:|:---|")
        for rank, it, from_week in rows:
            repo = esc(it.get("repo")) + (" 📅" if from_week else "")
            delta = it.get("delta_week") if from_week else it.get("delta_today")
            w("| %s | [%s](%s) | %s | %s | %s | %s |" % (
                rank, repo, it.get("url") or "", esc(it.get("lang")) or "—",
                fmt_num(it.get("stars")), fmt_delta(delta),
                esc(truncate(it.get("desc"), 60)) or "—"))
        w("")
        w("> 保底版不含项目详解，完整解读由 Agent 补全。")
        w("")
    else:
        out.extend(failure_block("github", raw, date_label))
    w("---")
    w("")

    # 二、三、四
    for sec_no, plat in ((2, "weibo"), (3, "douyin"), (4, "xhs")):
        w("## %s、%s热榜" % ("二三四"[sec_no - 2], PLATFORM_CN[plat]))
        w("")
        items = (raw.get("platforms") or {}).get(plat) or []
        if items:
            w("| # | 话题 | 热度 | 分类 |")
            w("|:---:|:---|:---:|:---:|")
            for i, it in enumerate(items[:10], 1):
                w("| %s | [%s](%s) | %s | — |" % (
                    rank_cell(i), esc(truncate(it.get("title"), 60)),
                    it.get("link") or "", fmt_hot(it.get("hot_value"))))
            w("")
        else:
            out.extend(failure_block(plat, raw, date_label))
        w("---")
        w("")

    # 五、AIHOT
    w("## 五、AI 行业热点(AIHOT)")
    w("")
    items = (raw.get("platforms") or {}).get("aihot") or []
    if items:
        w("> 口径说明：AIHOT 按多源印证度排序，**不是浏览量**；"
          "「印证度」为 `源数 · 信号数`。")
        w("")
        w("| # | 话题 | 印证度 | 首发源 | 分类 |")
        w("|:---:|:---|:---:|:---|:---:|")
        for i, it in enumerate(items[:10], 1):
            cat = CATEGORY_CN.get(it.get("category") or "", "—")
            src = truncate(it.get("source"), 30) or "—"
            w("| %s | [%s](%s) | %s | %s | %s |" % (
                rank_cell(i), esc(truncate(it.get("title"), 60)),
                it.get("link") or "", esc(it.get("hot_value")), esc(src), cat))
        w("")
    else:
        out.extend(failure_block("aihot", raw, date_label))
    w("---")
    w("")

    # 横向观察
    w("## 横向观察")
    w("")
    w("**本保底版未做跨平台解读。** 完整版由 Agent 补齐 3-5 条跨平台洞察后覆盖本文件。")
    w("")

    return "\n".join(out).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="由抓取原始 JSON 生成保底版 Markdown 日报")
    ap.add_argument("raw_json", help="fetch_trends.py 的输出文件")
    ap.add_argument("--out", default="", help="输出 .md 路径（默认 平台热点速览-<日期>.md）")
    ap.add_argument("--force", action="store_true", help="目标已存在时强制覆盖")
    args = ap.parse_args()

    if not os.path.exists(args.raw_json):
        print("[error] 找不到原始数据 %s" % args.raw_json, file=sys.stderr)
        return 2
    try:
        raw = json.load(io.open(args.raw_json, encoding="utf-8-sig"))
    except (ValueError, OSError) as e:
        print("[error] 读取原始数据失败: %s" % e, file=sys.stderr)
        return 2

    generated_at = raw.get("generated_at") or ""
    day = generated_at[:10] if len(generated_at) >= 10 else "unknown"
    out_path = args.out or "平台热点速览-%s.md" % day

    if os.path.exists(out_path) and os.path.getsize(out_path) > 0 and not args.force:
        print("[skip] %s 已存在且非空（未加 --force），不覆盖" % out_path)
        return 0

    text = render(raw)
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("[ok] %s（%d 字节）" % (out_path, os.path.getsize(out_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
