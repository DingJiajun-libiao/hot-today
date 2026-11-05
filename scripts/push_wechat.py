#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把手机版日报主动推送到微信（走 DSH-IM 插件的本机主动投递接口）。

接口: POST http://127.0.0.1:<port>/api/dsh-im/delivery/messages
     body: {"botId": "...", "targetId": "...", "text": "...", "format": "plain"}
     文档: @xmanrui/dsh-im/PROACTIVE_DELIVERY.md
     注意: 本机接口无鉴权，仅监听 127.0.0.1；targetId 必须在插件设置页预先创建。

用法:
    python scripts/push_wechat.py 平台热点速览-2026-11-05.mobile.txt
    python scripts/push_wechat.py <txt> --target daily-report --port 60023

退出码:
    0 全部成功 / 3 部分段失败 / 2 参数或配置缺失 / 1 全部失败
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# Windows 控制台默认 GBK,中文/emoji 直出会 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_PORT = 60023
# 机器人 ID 属于本机环境配置，不入库：依次取 --bot / wechat-target.json / 环境变量
DEFAULT_BOT_ID = os.environ.get("DSH_IM_BOT_ID", "")
# 微信主动投递的分段预算（见 PROACTIVE_DELIVERY.md「投递语义与限制」）
WECHAT_SEGMENT_BUDGET = 1800
CONFIG_NAME = "wechat-target.json"


def load_config(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def split_parts(text):
    """按 '──── 段 N/M ────' 切段；没有分隔行则整体作为一段。"""
    lines = text.splitlines()
    parts, buf = [], []
    for ln in lines:
        if re.fullmatch(r"\s*─+\s*段\s*\d+\s*/\s*\d+\s*─+\s*", ln):
            if buf:
                parts.append("\n".join(buf).strip())
            buf = []
            continue
        buf.append(ln)
    if buf:
        parts.append("\n".join(buf).strip())
    return [p for p in parts if p]


def enforce_budget(parts, budget):
    """把超过平台预算的段按行再切，避免被截断。"""
    out = []
    for p in parts:
        if len(p) <= budget:
            out.append(p)
            continue
        cur = []
        size = 0
        for ln in p.splitlines():
            add = len(ln) + 1
            if cur and size + add > budget:
                out.append("\n".join(cur))
                cur, size = [], 0
            cur.append(ln)
            size += add
        if cur:
            out.append("\n".join(cur))
    return out


def send(host, port, bot_id, target_id, text, timeout=30):
    url = f"http://{host}:{port}/api/dsh-im/delivery/messages"
    body = json.dumps(
        {"botId": bot_id, "targetId": target_id, "text": text, "format": "plain"},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", "ignore")
            return True, payload
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.read().decode('utf-8', 'ignore')[:300]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("txt", help="mobile.txt 路径")
    ap.add_argument("--target", default=None, help="投递目标 targetId")
    ap.add_argument("--bot", default=None, help="botId")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", CONFIG_NAME))
    target = args.target or cfg.get("targetId") or os.environ.get("DSH_IM_TARGET_ID")
    bot = args.bot or cfg.get("botId") or DEFAULT_BOT_ID
    port = args.port or cfg.get("port") or DEFAULT_PORT

    if not target:
        print(f"[error] 缺少 targetId：请先在 DSH-IM 设置页创建投递目标，"
              f"或写入 {CONFIG_NAME} / 传 --target", file=sys.stderr)
        return 2
    if not bot:
        print(f"[error] 缺少 botId：请在 DSH-IM 设置页复制机器人 ID，"
              f"或写入 {CONFIG_NAME} / 传 --bot / 设置环境变量 DSH_IM_BOT_ID", file=sys.stderr)
        return 2
    if not os.path.exists(args.txt):
        print(f"[error] 找不到 {args.txt}", file=sys.stderr)
        return 2

    text = open(args.txt, encoding="utf-8").read()
    parts = enforce_budget(split_parts(text), WECHAT_SEGMENT_BUDGET)
    if not parts:
        print("[error] 内容为空", file=sys.stderr)
        return 2

    print(f"[info] {len(parts)} 段，共 {sum(len(p) for p in parts)} 字符；目标 {target}@{bot}")
    if args.dry_run:
        for i, p in enumerate(parts, 1):
            print(f"--- 段 {i} ({len(p)} 字符) ---\n{p[:120]}...")
        return 0

    ok = 0
    fail = 0
    for i, p in enumerate(parts, 1):
        success, detail = send(args.host, port, bot, target, p)
        if success:
            ok += 1
            print(f"[ok] 段 {i}/{len(parts)} 已发送 {detail}")
        else:
            fail += 1
            print(f"[fail] 段 {i}/{len(parts)}: {detail}", file=sys.stderr)
            if "unknown-target" in detail:
                print("[hint] targetId 不存在：请先在 DSH-IM 设置页创建投递目标", file=sys.stderr)
                break
        if i < len(parts):
            time.sleep(1.5)  # 避免触发平台频控

    print(f"[summary] 成功 {ok} / 失败 {fail}（共 {len(parts)} 段）")
    if fail == 0:
        return 0
    return 1 if ok == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
