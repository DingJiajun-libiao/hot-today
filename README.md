# 🔥 today-hot — 平台热点速览

> GitHub、微博、抖音、小红书、AIHOT 五大热点源,一键生成带真实链接和背景解读的中文 Markdown 日报。

`today-hot` 是一个开放格式的 **Agent Skill**:AI Agent 安装后,用一句自然语言就能抓取当天各平台热榜,并按固定排版生成可直接分享的中文报告。

## ✨ 特性

- **五个数据源**:GitHub Trending(日榜 + 周榜)、微博热搜、抖音热榜、小红书热榜、AIHOT AI 行业热点
- **真实可追溯**:每条热点带真实链接;接口失败如实标注,不编造数据与热度
- **纯标准库**:抓取脚本只用 Python 标准库(3.9+),无第三方依赖、无 API Key
- **内置容错**:429 指数退避、多镜像自动回退、AIHOT 重试;单平台失败不影响整份报告
- **交付兜底**:定时/无人值守任务下,即使全部数据源失败,也会先落盘一份如实标注的保底报告(见 `scripts/fallback_report.py`)
- **可定时**:由支持调度的 Agent 每天自动执行,报告落盘到工作目录

## 📦 安装

```bash
# 从 GitHub 安装(把 <owner> 换成仓库所属账号)
npx skills add <owner>/hot-today
```

或手动安装:把本仓库复制到 Agent 的 skills 目录,例如:

| Agent | 目录 |
|---|---|
| 通用(DSH 等) | `~/.agents/skills/today-hot/` |
| Claude Code | `~/.claude/skills/today-hot/` |
| OpenClaw | `~/.openclaw/skills/today-hot/` |
| 项目内安装 | `<项目>/.agents/skills/today-hot/` |

该格式被 Claude Code、Cursor、Codex、OpenClaw、TRAE 等 80+ 款 Agent 支持(见 [skills.sh](https://skills.sh))。

## 🚀 使用

对 Agent 说:

- 「今天有什么热点?」
- 「各平台热榜」
- 「GitHub 趋势 + 国内热搜」
- 「AI 圈今天在讨论什么」

Agent 会先运行抓取脚本,立即用 `fallback_report.py` 落一份保底报告到 `平台热点速览-YYYY-MM-DD.md`(当前工作目录),再按模板补全详解并覆盖它。

也可以只运行抓取脚本获取结构化 JSON:

```bash
python3 <skill-dir>/scripts/fetch_trends.py \
  --platform github,weibo,douyin,xhs,aihot \
  --top 10 \
  --out ./trends_raw.json
```

Windows 下把 `python3` 换成 `python`。

**保底报告**(定时任务先落盘、后补全):

```bash
python3 <skill-dir>/scripts/fallback_report.py ./trends_raw.json \
  --out ./平台热点速览-2026-11-05.md
```

只用原始数据生成「今日速览 + 五平台榜单」,失败平台标注 `meta` 错误摘要;目标文件已存在且非空时默认跳过(`--force` 强制重写)。Agent 随后按输出规范补全详解并覆盖同一文件。

## 📱 手机版与微信推送(可选)

报告可以再转成适合手机阅读的纯文本,并(可选)主动投递到微信:

```bash
# 1) 生成手机版(默认输出到 .md 同目录)
python3 <skill-dir>/scripts/to_mobile_text.py 平台热点速览-2026-11-05.md --limit 1800

# 2) 推送到微信(需要 DSH + @xmanrui/dsh-im 插件环境)
python3 <skill-dir>/scripts/push_wechat.py 平台热点速览-2026-11-05.mobile.txt
```

- `to_mobile_text.py`:手机版只保留热点名——GitHub 每条三行(项目名 / 语言·今日增长 / 一句话简介),
  微博/抖音/小红书/AIHOT 仅标题;不含任何链接与详解正文,按「──── 段 N/M ────」分段,适配手机/微信阅读。
- `push_wechat.py`:调用插件本机投递接口 `POST http://127.0.0.1:<port>/api/dsh-im/delivery/messages`;
  机器人 / 投递目标从 `wechat-target.json`(`botId` / `targetId` / `port`,已在 `.gitignore` 中)
  或 `--bot` / `--target` / 环境变量 `DSH_IM_BOT_ID` 读取。
  退出码:`0` 全部送达 / `3` 部分段失败 / `1` 全部失败 / `2` 缺少配置。
- 推送失败不阻断交付:报告照常生成,只记录成功/失败段数。

> `push_wechat.py` 依赖 DSH-IM 插件的本机接口,不是通用能力;纯 Agent Skill 场景可忽略。

## 📄 报告样例

```markdown
## 📊 今日速览

| 平台 | 榜首热点 | 热度 | 今日关键词 |
|:---:|:---|:---:|:---:|
| 🐙 GitHub | [public-apis](https://github.com/public-apis/public-apis)(+1,588 ★) | 总星 46.2 万 | AI 工具链 |
| 📱 微博 | [示例话题](https://s.weibo.com/...) | 117 万 | 时政与民生 |
| 🎬 抖音 | [示例话题](https://www.douyin.com/...) | 1,153 万 | 体育 |
| 📕 小红书 | [示例话题](https://www.xiaohongshu.com/...) | 920.8 万 | 暑期出行 |
| 🤖 AIHOT | [示例话题](https://aihot.news/items/...) | 4 源 · 30 信号 | AI 架构开源 |
```

完整报告包含:今日速览表,五个平台各 Top 10 榜单 + 每条热点的 2-4 句背景解读,以及跨平台「横向观察」。

## 📚 数据来源

| 平台 | 来源 | 说明 |
|---|---|---|
| GitHub | `github.com/trending` 官方页面 | 页面解析,日榜 + 周榜补充 |
| 微博 | `60s.viki.moe/v2/weibo` 等公共聚合 | 第三方服务,多镜像回退 |
| 抖音 | `60s.viki.moe/v2/douyin` 等公共聚合 | 第三方服务,多镜像回退 |
| 小红书 | `60s.viki.moe/v2/rednote` 等公共聚合 | 第三方服务,多镜像回退 |
| AIHOT | `aihot.news/api/v1/hot-topics` 官方 API | 匿名只读,含 story digest |

> ⚠️ 微博/抖音/小红书为第三方公共聚合服务,并非官方接口,可能限流或失效;GitHub 为页面解析,改版后可能需要更新解析逻辑。数据版权归各平台所有。

## ⚙️ 配置

| 参数 | 默认 | 说明 |
|---|---|---|
| `--platform` | 全部五平台 | 逗号分隔,如 `github,aihot` |
| `--top` | 10 | 每平台条数 |
| `--out` | 打印到 stdout | 输出 JSON 路径 |
| `--timeout` | 25 | 单次请求超时(秒) |
| `--config` | 内置数据源 | 数据源覆盖配置,参考 `config.example.json` |

退出码:`0` 全部成功、`3` 部分平台失败、`1` 全部失败、`2` 参数错误。

## ⏰ 定时执行

支持定时任务的 Agent(如 DSH)可以每天固定时间触发,例如每天 20:00:

> 加载 today-hot skill,运行抓取脚本,生成 `平台热点速览-YYYY-MM-DD.md` 到当前工作目录。

报告文件会按天落盘,可作为每日热点归档。

### 交付保证

定时/无人值守场景没有用户可追问,因此本 skill 采用「交付优先」(详见 `SKILL.md`):

1. 抓取退出码 `3`(部分失败)/ `1`(全部失败)**都不是中断理由**;
2. 抓完立即用 `fallback_report.py` 落盘一份保底报告,保证磁盘上先有交付物;
3. 判定成功 = **文件存在且大小 > 0**,而不是「所有平台都有数据」;
4. 报告落盘之前不探测替代源、不反复重试、不改脚本;失败平台在报告里如实标注 `meta` 错误摘要。

## ⚠️ 免责声明

- 本项目仅供学习与研究,请遵守各平台服务条款与当地法律法规。
- 数据来自公开接口,不保证及时性与准确性;接口失效时报告会如实标注。
- 本项目为纯 Markdown 报告生成工具,不做 HTML 渲染,不存储任何用户数据。

## 🧪 已知限制

- 微博/抖音/小红书的第三方镜像列表硬编码在脚本中,失效时可自行更新或通过 `config.json` 覆盖。
- GitHub 直连失败时脚本会尝试备用 IP + SNI 回退(内置少量固定 IP,长期可能失效)。
- AIHOT 的「热度」是多源印证度(源数 · 信号数),不是浏览量。

## 🤝 贡献

欢迎 Issue 和 PR。如果某个数据源失效,提交带 `meta` 错误信息的 Issue 即可,方便快速修复。

## 📄 许可证

[MIT](LICENSE)
