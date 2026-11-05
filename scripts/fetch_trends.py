#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
today-hot 抓取脚本
抓取 GitHub Trending、微博热搜、抖音热榜、小红书热榜、AIHOT AI 行业热点,输出结构化 JSON。

用法:
    python fetch_trends.py [--platform github,weibo,douyin,xhs,aihot] [--top N] [--out PATH]
                           [--timeout SEC] [--config PATH]

退出码:
    0  所有请求的平台均有数据
    3  部分平台失败(其余平台数据可用)
    1  所有平台均失败
    2  参数错误

依赖: Python 标准库
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Windows 控制台默认 GBK,中文/emoji 直出会 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

RETRYABLE_STATUS = (429, 500, 502, 503, 504)
# 429 退避节奏(秒);5xx/超时用 FLAKY_RETRY_WAIT
BACKOFF_429 = (1.0, 3.0)
FLAKY_RETRY_WAIT = 0.8

# 各平台数据源:首个为主源,其余按顺序回退。
# 主源 60s.viki.moe 近期对 weibo/douyin/rednote 频繁返回 429 或超时,故三个平台共用同一批公共实例。
_COMMON_MIRRORS = [
    "https://60s.mizhoubaobei.top/v2/%s",
    "https://60s.crystelf.top/v2/%s",
    "https://api.elysiayanyu.top/v2/%s",
    "https://60s.zellon.top/v2/%s",
]
DEFAULT_SOURCES = {
    "weibo": ["https://60s.viki.moe/v2/weibo"]
             + [m % "weibo" for m in _COMMON_MIRRORS]
             + ["https://60s.7se.cn/v2/weibo"],
    "douyin": ["https://60s.viki.moe/v2/douyin"]
              + [m % "douyin" for m in _COMMON_MIRRORS]
              + ["https://60s.7se.cn/v2/douyin"],
    # 7se.cn 无 /v2/rednote 接口,不列入回退
    "xhs": ["https://60s.viki.moe/v2/rednote"]
           + [m % "rednote" for m in _COMMON_MIRRORS],
}
# AIHOT(aihot.news)官方匿名只读 API,规范见 https://aihot.news/openapi-v1.json
AIHOT_HOT_API = "https://aihot.news/api/v1/hot-topics"
AIHOT_ITEMS_API = "https://aihot.news/api/v1/items"
AIHOT_STORY_API = "https://aihot.news/api/v1/stories/"

VALID_PLATFORMS = ("github", "weibo", "douyin", "xhs", "aihot")

# 本轮运行中已被判定不可用的源:后续平台不再对它们做退避重试,直接换下一个源
_DEAD_HOSTS = set()


class FetchError(Exception):
    """带 HTTP 状态码的抓取失败,便于按状态码决定是否重试。"""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _host(url):
    return urllib.parse.urlparse(url).netloc


def load_sources(config_path):
    """从 config.json 读取数据源覆盖配置(缺省用内置列表)。

    config.json 结构: {"sources": {"weibo": ["https://.../v2/weibo", ...], ...}}
    """
    sources = dict(DEFAULT_SOURCES)
    if not config_path:
        return sources
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    for platform, urls in (cfg.get("sources") or {}).items():
        if platform in ("weibo", "douyin", "xhs") and urls:
            sources[platform] = list(urls)
    return sources


def http_get(url, timeout=25):
    """单次请求;对 GitHub 直连失败时回退到备用 IP + SNI(解决 DNS 主 IP 不可达)。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise FetchError("HTTP %d" % e.code, status=e.code)
    except Exception as e:
        host = urllib.parse.urlparse(url).hostname
        if host != "github.com":
            raise FetchError("%s: %s" % (type(e).__name__, e))
        return _http_get_github_via_ip(url, timeout)


def fetch_text(url, timeout=25):
    """按状态码决定重试策略:429 指数退避,5xx/超时单次重试,其余 4xx 直接换源。

    同一轮内已判定失效的源(_DEAD_HOSTS)只再试一次,不再退避,避免各平台重复等待。
    """
    host = _host(url)
    attempts = 1 if host in _DEAD_HOSTS else len(BACKOFF_429) + 1
    last = None
    for attempt in range(attempts):
        try:
            return http_get(url, timeout=timeout)
        except FetchError as e:
            last = e
            retryable = e.status == 429 or e.status is None or e.status in RETRYABLE_STATUS
            if not retryable:
                raise
            if attempt + 1 >= attempts:
                _DEAD_HOSTS.add(host)
                raise
            wait = (BACKOFF_429[min(attempt, len(BACKOFF_429) - 1)]
                    if e.status == 429 else FLAKY_RETRY_WAIT)
            print("[warn] %s %s, retry in %.1fs" % (host, e, wait), file=sys.stderr)
            time.sleep(wait)
    raise last


def _http_get_github_via_ip(url, timeout=25):
    """通过备用 IP + SNI 抓取 github.com,避免 DNS 主 IP 不可达导致超时。"""
    import socket
    import ssl
    from urllib.parse import urlparse

    u = urlparse(url)
    path = u.path + (("?" + u.query) if u.query else "")
    ips = ["140.82.112.4", "140.82.113.4", "140.82.114.4", "20.201.28.151"]
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    last_err = None
    for ip in ips:
        try:
            s = socket.create_connection((ip, 443), timeout=timeout)
            ss = ctx.wrap_socket(s, server_hostname="github.com")
            req = ("GET %s HTTP/1.1\r\nHost: github.com\r\nUser-Agent: %s\r\n"
                   "Accept: text/html\r\nConnection: close\r\n\r\n" % (path, UA))
            ss.sendall(req.encode("utf-8"))
            data = b""
            while True:
                chunk = ss.recv(65536)
                if not chunk:
                    break
                data += chunk
            ss.close()
            head, _, body = data.partition(b"\r\n\r\n")
            status_line = head.split(b"\r\n")[0].decode("utf-8", "replace")
            if " 200 " in status_line:
                return body.decode("utf-8", errors="replace")
            if " 30" in status_line:  # 301/302 重定向
                for line in head.split(b"\r\n"):
                    if line.lower().startswith(b"location:"):
                        loc = line.split(b":", 1)[1].strip().decode("utf-8", "replace")
                        target = loc if loc.startswith("http") else "https://github.com" + loc
                        return http_get(target, timeout)
        except Exception as e:
            last_err = e
    raise FetchError("github via ip failed: %s" % (last_err or "unknown"))


def _meta(ok, source="", attempts=0, elapsed_ms=0, items=0, error=None):
    return {
        "ok": ok,
        "source": source,
        "attempts": attempts,
        "elapsed_ms": elapsed_ms,
        "items": items,
        "error": error,
    }


def fetch_60s(platform, urls, top, timeout=25):
    """微博/抖音/小红书:按数据源列表逐个回退,返回 (items, meta)。"""
    started = time.time()
    tried, last_err = [], None
    for attempt, url in enumerate(urls, 1):
        tried.append(_host(url))
        try:
            data = json.loads(fetch_text(url, timeout=timeout))
            items = data.get("data") or []
            if not items:
                raise FetchError("empty data")
        except FetchError as e:
            last_err = str(e)
            print("[warn] %s %s failed: %s" % (platform, _host(url), e), file=sys.stderr)
            continue
        out = []
        for it in items[:top]:
            out.append({
                "rank": len(out) + 1,
                "title": it.get("title", ""),
                "hot_value": it.get("hot_value") or it.get("hot") or it.get("score") or "",
                "link": it.get("link", ""),
                "extra": it.get("cover") or "",
            })
        if attempt > 1:
            print("[info] %s via fallback: %s" % (platform, _host(url)), file=sys.stderr)
        return out, _meta(True, _host(url), attempt, int((time.time() - started) * 1000), len(out))
    print("[warn] %s all sources failed: %s" % (platform, last_err), file=sys.stderr)
    return [], _meta(False, "", len(urls), int((time.time() - started) * 1000), 0,
                     "%s (tried: %s)" % (last_err, ", ".join(tried)))


def fetch_aihot(top, timeout=25):
    """AIHOT AI 行业热点:官方 Top 10 榜 + 每条 story 的 digest 摘要,返回 (items, meta)。"""
    started = time.time()
    try:
        hot = json.loads(fetch_text(AIHOT_HOT_API, timeout=timeout)).get("items") or []
    except (FetchError, ValueError) as e:
        print("[warn] aihot %s failed: %s" % (AIHOT_HOT_API, e), file=sys.stderr)
        return [], _meta(False, _host(AIHOT_HOT_API), 1,
                         int((time.time() - started) * 1000), 0, str(e))
    if not hot:
        print("[warn] aihot hot-topics returned empty data", file=sys.stderr)
        return [], _meta(False, _host(AIHOT_HOT_API), 1,
                         int((time.time() - started) * 1000), 0, "empty data")

    meta = {}
    try:
        page = json.loads(fetch_text(
            "%s?window=7d&mode=all&limit=100" % AIHOT_ITEMS_API, timeout=timeout))
        for it in page.get("items") or []:
            meta[it.get("id")] = it
    except (FetchError, ValueError) as e:
        print("[warn] aihot items enrich failed: %s" % e, file=sys.stderr)

    out = []
    for entry in hot[:top]:
        links = entry.get("links") or {}
        info = meta.get(entry.get("id") or "") or {}
        digest, report_count = "", 0
        story_url = links.get("story") or ""
        public_id = story_url.rstrip("/").rsplit("/", 1)[-1] if story_url else ""
        if public_id:
            try:
                story = json.loads(fetch_text(
                    AIHOT_STORY_API + public_id, timeout=timeout)).get("story") or {}
                digest = story.get("digest") or ""
                report_count = story.get("reportCount") or 0
            except (FetchError, ValueError) as e:
                print("[warn] aihot story %s failed: %s" % (public_id, e), file=sys.stderr)
            time.sleep(0.15)
        out.append({
            "rank": entry.get("rank") or len(out) + 1,
            "title": entry.get("title", ""),
            "hot_value": "%d 源 · %d 信号" % (entry.get("sourceCount") or 0,
                                            entry.get("signalCount") or 0),
            "link": links.get("aihot", ""),
            "extra": links.get("original", ""),
            "source": (entry.get("source") or {}).get("name", ""),
            "source_count": entry.get("sourceCount") or 0,
            "signal_count": entry.get("signalCount") or 0,
            "report_count": report_count,
            "published_at": entry.get("latestAt", ""),
            "category": info.get("category") or "",
            "score": info.get("score"),
            "story": story_url,
            "summary": digest or info.get("summary") or "",
            "brief": info.get("summary") or "",
        })
    return out, _meta(True, _host(AIHOT_HOT_API), 1,
                      int((time.time() - started) * 1000), len(out))


def fetch_github(top, timeout=30):
    """GitHub Trending 页面解析(日榜 + 周榜补充),返回 (daily, weekly, meta)。"""
    started = time.time()
    daily, weekly, errors = [], [], []
    for since, bucket in (("daily", daily), ("weekly", weekly)):
        try:
            html = fetch_text("https://github.com/trending?since=%s" % since, timeout=timeout)
        except FetchError as e:
            print("[warn] github %s fetch failed: %s" % (since, e), file=sys.stderr)
            errors.append("%s: %s" % (since, e))
            continue
        seen = set()
        for row in html.split("<article")[1:]:
            m = re.search(r'href="/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"', row)
            if not m:
                continue
            repo = m.group(1)
            if repo in seen or repo.count("/") != 1 or repo.startswith("sponsors/"):
                continue
            seen.add(repo)
            dm = re.search(r'<p class="col-9[^"]*">\s*(.*?)\s*</p>', row, re.S)
            desc = re.sub(r"<[^>]+>", "", dm.group(1)).strip() if dm else ""
            lm = re.search(r'itemprop="programmingLanguage">([^<]+)<', row)
            lang = lm.group(1).strip() if lm else ""
            sm = re.search(r'href="/%s/stargazers".*?([\d,]+)\s*</a>' % re.escape(repo), row, re.S)
            stars = sm.group(1).replace(",", "") if sm else ""
            tm = re.search(r"([\d,]+)\s+stars (today|this week)", row)
            delta = tm.group(1).replace(",", "") if tm else ""
            unit = "today" if since == "daily" else "week"
            bucket.append({
                "repo": repo,
                "lang": lang,
                "stars": stars,
                "delta_%s" % unit: delta,
                "desc": desc,
                "url": "https://github.com/%s" % repo,
                "period": unit,
            })
    elapsed = int((time.time() - started) * 1000)
    ok = bool(daily or weekly)
    return daily, weekly, _meta(ok, "github.com", 2, elapsed, len(daily) + len(weekly),
                                None if ok else "; ".join(errors) or "empty data")


def main():
    ap = argparse.ArgumentParser(description="抓取 GitHub/微博/抖音/小红书/AIHOT 热点")
    ap.add_argument("--platform", default=",".join(VALID_PLATFORMS))
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--out", default="")
    ap.add_argument("--timeout", type=float, default=25, help="单次请求超时(秒)")
    ap.add_argument("--config", default="", help="config.json 路径,可覆盖各平台数据源列表")
    args = ap.parse_args()

    platforms = [p.strip() for p in args.platform.split(",") if p.strip()]
    invalid = [p for p in platforms if p not in VALID_PLATFORMS]
    if invalid or not platforms:
        ap.error("未知平台 %s,可选: %s" % (",".join(invalid) or "(空)",
                                       ",".join(VALID_PLATFORMS)))

    sources = load_sources(args.config)
    result = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "platforms": {}, "meta": {}}

    if "github" in platforms:
        daily, weekly, meta = fetch_github(args.top, timeout=args.timeout)
        daily_top = daily[: args.top]
        weekly_top = weekly[: max(0, args.top - len(daily_top))]
        result["platforms"]["github"] = {"daily": daily_top, "weekly": weekly_top}
        meta["items"] = len(daily_top) + len(weekly_top)
        result["meta"]["github"] = meta
    if "weibo" in platforms:
        result["platforms"]["weibo"], result["meta"]["weibo"] = fetch_60s(
            "weibo", sources["weibo"], args.top, timeout=args.timeout)
    if "douyin" in platforms:
        result["platforms"]["douyin"], result["meta"]["douyin"] = fetch_60s(
            "douyin", sources["douyin"], args.top, timeout=args.timeout)
    if "xhs" in platforms:
        result["platforms"]["xhs"], result["meta"]["xhs"] = fetch_60s(
            "xhs", sources["xhs"], args.top, timeout=args.timeout)
    if "aihot" in platforms:
        result["platforms"]["aihot"], result["meta"]["aihot"] = fetch_aihot(
            args.top, timeout=args.timeout)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("saved -> %s" % args.out, file=sys.stderr)
    else:
        print(text)

    summary = []
    for p in platforms:
        m = result["meta"][p]
        summary.append("%s %s(%s,%d条,%dms)" % (
            p, "ok" if m["ok"] else "FAIL", m["source"] or "-", m["items"], m["elapsed_ms"]))
    print("[summary] " + " | ".join(summary), file=sys.stderr)

    ok_count = sum(1 for p in platforms if result["meta"][p]["ok"])
    if ok_count == len(platforms):
        return 0
    return 3 if ok_count else 1


if __name__ == "__main__":
    sys.exit(main())
