---
name: today-hot
description: 抓取 GitHub、微博、抖音、小红书热点 + AIHOT(aihot.news) AI 行业热点,汇总生成带链接和详细说明的中文 Markdown 报告。适用于"今天/本周有什么热点""各平台热榜""GitHub 趋势+国内热搜""AI 圈今天在讨论什么"等请求。
version: "1.1.0"
author: kun-user
license: MIT
metadata:
  openclaw:
    emoji: "🔥"
    files:
      - "scripts/*"
    tags:
      - trends
      - hot-search
      - github
      - weibo
      - douyin
      - xiaohongshu
      - aihot
      - ai-news
      - chinese
      - report
---

# today-hot - 平台热点速览

抓取 **GitHub Trending(今日+周榜)、微博热搜、抖音热榜、小红书热榜、AIHOT(aihot.news) AI 行业热点** 五个数据源,汇总成一份**带可点击链接、详细背景说明、精美 Markdown 排版**的中文报告。

## 什么时候用

- "今天有什么热点"
- "各平台热榜 / 各平台热搜"
- "GitHub 今天趋势 + 国内热搜"
- "帮我看看微博/抖音/小红书在热什么"
- "AI 圈今天在讨论什么 / AI 日报"
- "生成一份热点报告"

## 数据来源

| 平台 | 来源 | 说明 |
|---|---|---|
| GitHub | `github.com/trending` 官方页面 | 日榜 + 周榜补充,含语言、星标、增长 |
| 微博 | `60s.viki.moe/v2/weibo` 公开聚合 | 含热度值、搜索链接 |
| 抖音 | `60s.viki.moe/v2/douyin` 公开聚合 | 含热度值、搜索链接 |
| 小红书 | `60s.viki.moe/v2/rednote` 公开聚合 | 含热度、搜索链接 |
| AIHOT | `aihot.news/api/v1/hot-topics` 官方 API | AI 行业 Top 10,含源数 / 信号数 / story digest |

> 注:GitHub、AIHOT 为官方来源,其余三平台为聚合服务;接口可能临时不可用,此时该平台数据为空,如实报告即可,不要编造。
> AIHOT 规范见 https://aihot.news/openapi-v1.json (匿名只读,可能返回 429/503,脚本已内置重试)。

## 工作流

### 交付优先（硬约束，优先于一切）

**无论抓取结果如何，本轮都必须产出并落盘 Markdown 报告；顺序是「先落盘，再分析」。**

1. 退出码 `3`（部分平台失败）与 `1`（全部平台失败）**都不构成中断理由**，照常生成报告。
2. 判定「交付成功」的唯一标准：**报告文件存在且大小 > 0**，而不是「所有平台都有数据」。
3. **报告落盘之前**，禁止：探测/调研替代数据源、反复重试同一失败平台、修改 `scripts/` 或 `config.json`、等待用户确认。
4. 平台失败时整节标注「数据暂不可用」并附 `meta.<platform>.error` 摘要；严禁用其他平台数据填充，严禁估算或编造热度与链接。
5. 定时/无人值守场景（如每天 20:00）尤其要遵守本节：没有用户可追问，先交付再优化。

### Step 1 - 运行抓取脚本

在**当前工作目录**(通常是用户的项目根目录,报告也输出到这里)执行,脚本用 skill 目录里的绝对路径:

```bash
python3 <skill-dir>/scripts/fetch_trends.py --platform github,weibo,douyin,xhs,aihot --top 10 --out ./trends_raw.json
```

- 需要 Python 3.9+,命令按系统而定:`python3`(macOS/Linux)或 `python`(Windows)。
- 临时文件 `./trends_raw.json` 写在当前目录,**不要写进 skill 安装目录**。
- 纯标准库实现,无第三方依赖。
- 若 `--top N` 未指定,默认每平台 10 条。
- 输出文件 `./trends_raw.json` 包含 `platforms.github.daily / .weekly`、`platforms.weibo`、`platforms.douyin`、`platforms.xhs`、`platforms.aihot`,以及顶层 `meta`(每个平台 `{ok, source, attempts, elapsed_ms, items, error}`)。
- 只补抓 AI 源可用 `--platform aihot`(约 3 秒)。
- **失败无需人工重试或合并 JSON**:微博/抖音/小红书已内置多源回退(主源 429/超时自动切换公共实例),429 走指数退避,AIHOT 独立重试;失败原因写在 `meta.<platform>.error`。
- 需要更大重试预算或换源:`--timeout 40` / `--config config.json`(结构见 `config.example.json`)。
- 退出码:`0` 全部成功、`3` 部分平台失败、`1` 全部失败、`2` 参数错误。

### Step 2 - 解析数据(读取 ./trends_raw.json)

用 Python 或直接读文件解析:

- **先看 `meta` 判断可用性**:每个平台带 `{"ok", "source", "attempts", "elapsed_ms", "items", "error"}`。`ok=false` 的平台在报告里如实标注「该平台数据暂不可用(附 error 摘要)」,不得用其他平台数据填充。
- **GitHub**:`daily` 前 10 为今日榜;若不足 10,用 `weekly` 补充至 10,并在条目上标注 `📅 周榜`。
- **微博/抖音/小红书**:直接取 `top 10`,字段 `title`、`hot_value`、`link`。
- **AIHOT**:直接取官方 Top 10。字段 `title`、`hot_value`(形如 `4 源 · 30 信号`,由 `source_count`/`signal_count` 生成)、`link`(aihot 条目页)、`extra`(原文链接)、`source`(首发媒体)、`summary`(story 的人工 digest,2-4 句可直接用作背景说明)、`category`、`score`、`story`。
  - AIHOT 没有传统"热度值",**严禁臆造浏览量或分数**;报告热度列写 `4 源 · 30 信号` 这类真实多源印证度,并在章节说明里解释口径。
  - `summary` 为空说明该条 story 未返回 digest,此时只据标题写已知事实,不补充细节;必要时可 `curl https://aihot.news/api/v1/items?q=<关键词>&limit=5` 补查。

**为每个热点补充背景说明**(重要):依据标题、项目 README(可 `curl raw.githubusercontent.com/{repo}/main/README.md` 获取)、公开信息,写 2-4 句解读:是什么 + 为什么上榜/为什么热。

### Step 3 - 生成 Markdown 报告（先保底落盘，再补全）

**第一步：立即用脚本落盘一份保底报告**（保证磁盘上先有交付物）：

```bash
python3 <skill-dir>/scripts/fallback_report.py ./trends_raw.json --out ./平台热点速览-YYYY-MM-DD.md
```

- 它只用 raw JSON 的真实数据生成「今日速览 + 五平台榜单」，失败平台如实标注「数据暂不可用」并附错误摘要；
- 目标文件已存在且 >0 时默认跳过，不会覆盖已完成的完整报告（需要重写加 `--force`）。

**第二步：按下方「输出规范」补全**，覆盖同一个文件：

```
./平台热点速览-YYYY-MM-DD.md
```

（保存到当前工作目录；用户明确要求其他目录时按用户要求）

- 若连 `./trends_raw.json` 都不存在（脚本崩溃等极端情况），直接手写一份仅含五个平台「数据暂不可用」的最小报告并落盘。
- 只交付 Markdown，不做 HTML 渲染或网页预览（该能力已移除）。

### Step 4 - 校验、清理与汇报

1. **先校验交付物**(`文件存在且大小 > 0`),不通过则立刻补写:
   - Windows PowerShell:`if ((Get-Item .\平台热点速览-YYYY-MM-DD.md).Length -gt 0) { "OK" }`
   - macOS/Linux:`test -s ./平台热点速览-YYYY-MM-DD.md && echo OK`
2. 删除临时文件 `./trends_raw.json`(Windows PowerShell:`Remove-Item .\trends_raw.json`;macOS/Linux:`rm -f ./trends_raw.json`)。
3. 向用户汇报:文件路径 + 一句话总结各平台榜首(失败平台写明失败)。

## 输出规范

### 排版模板(已验证)

```markdown
# 🔥 平台热点速览

<div align="center">

**YYYY 年 M 月 D 日 · 星期X**

GitHub · 微博 · 抖音 · 小红书 · AIHOT

</div>

---

## 📑 目录

- [今日速览](#今日速览)
- [跨平台热点](#跨平台热点)
- [一、GitHub 趋势榜](#一github-趋势榜)
- [二、微博热搜](#二微博热搜)
- [三、抖音热榜](#三抖音热榜)
- [四、小红书热榜](#四小红书热榜)
- [五、AI 行业热点(AIHOT)](#五ai-行业热点aihot)
- [横向观察](#横向观察)

---

## 📊 今日速览

| 平台 | 榜首热点 | 热度 | 今日关键词 |
|:---:|:---|:---:|:---:|
| 🐙 GitHub | [public-apis](https://github.com/public-apis/public-apis)(+1,588 ★) | 总星 46.2 万 | AI 工具链 |
| 📱 微博 | [纪念江泽民同志诞辰100周年大会](链接) | 117 万 | 时政与民生 |
| 🎬 抖音 | [国乒瑞典大满贯2冠1亚收官](链接) | 1,153 万 | 体育 |
| 📕 小红书 | [用万能旅行拍照姿势美美出片](链接) | 920.8 万 | 暑期出行 |
| 🤖 AIHOT | [DeepSeek开源Super-agent双层架构原型](链接) | 4 源 · 30 信号 | AI 架构开源 |
```

然后各平台一节:

```markdown
## 一、GitHub 趋势榜

| # | 项目 | 语言 | 总星标 | 增长 | 一句话简介 |
|:---:|:---|:---:|---:|:---:|:---|
| 🥇 | [public-apis/public-apis](链接) | Python | 461,878 | 🔺 +1,588 | 全网免费公共 API 大全 |
| 🥈 | ... | ... | ... | ... | ... |

### 📖 项目详解

**1. public-apis/public-apis** — 今日 +1,588 ★ · 总星 461,878

【项目内容】...【上榜看点】...
```

榜单表格(微博/抖音/小红书):`| # | 话题 | 热度 | 分类 |`,话题名包成链接。

AIHOT 用另一种表头(多一列信源):

```markdown
## 五、AI 行业热点(AIHOT)

| # | 话题 | 印证度 | 首发源 | 分类 |
|:---:|:---|:---:|:---|:---:|
| 🥇 | [DeepSeek开源Super-agent双层架构原型](https://aihot.news/items/xxx) | 4 源 · 30 信号 | IT之家·人工智能 | 论文 |
| 🥈 | ... | ... | ... | ... |

### 📖 热点详解

**1. DeepSeek开源Super-agent双层架构原型** — 4 源 · 30 信号

是什么 + 为什么重要,可用 `summary` 摘要打底改写,并注明原文出处链接。
```

> AIHOT 是 AI 行业动态聚合站,榜单按多源印证度排序而非浏览量。“热度”列采用官方 `源数 · 信号数`:前者是报道该事的独立媒体数,后者是该话题下的线索条数。

AIHOT 的 category 取值:`ai-models`(模型)、`ai-products`(产品)、`industry`(产业)、`paper`(论文)、`tip`(教程)、`opinion`(观点),报告里翻成中文。

详细解读:每条用**粗体标题行**(`**N. 标题** — 热度/星标`)开头:

- 标题行后**空一行**,再写 2-4 句正文
- **条目与条目之间空两行**(即上一段末尾到下一个标题行之间保留两个空行),让每条热点在源码与阅读器里都清晰分开。横向观察的 3-5 条同样适用

**不要使用 `<details>`/`<summary>` HTML 折叠标签**,以免在部分 Markdown 查看器中显示为多余文本。

### 铁律

1. **不要编造数据** - 只使用脚本返回的真实数据;接口失败则该平台如实标注"获取失败"。
2. **链接必须真实** - 使用脚本返回的 link 字段;GitHub 项目链接 = `https://github.com/{repo}`。
3. **每平台只取前 10**。
4. **GitHub 周榜补充项**要在表格/详解中标注 `📅`。
5. **报告文件名**:`平台热点速览-YYYY-MM-DD.md`,存到当前工作目录。标题统一用 `# 🔥 平台热点速览`——不再出现"四平台"字样。历史上以 `四平台热点速览-` 开头的旧报告保留原名不动。
6. **详解内容**要有"是什么"和"为什么热"两部分,基于真实 README/标题推断,不写空话。
7. **横向观察**章节写 3-5 条跨平台洞察(如体育霸榜、影视联动、职业焦虑共振、AI 双线叙事)。
8. **AIHOT 口径**: `hot_value` 是多源印证度而非浏览量,不得换算成"万";分类用官方 category 译名;`summary` 为空时不得补充未经确认的细节。
9. **间距**: 热点解读条目之间空**两行**,标题行与正文之间空**一行**;生成后自查 `\n\n\n**N. ` 分隔数 = 条目总数。

## 常见问题

- **接口超时/429/5xx**:脚本自动处理——429 退避(1s/3s)后换源,5xx/超时重试一次后换源,某源在本轮内失效后不再重复等待。无需人工重试或手工合并 JSON;报告依据 `meta.<platform>` 标注可用性与原因。
- **所有源都失败**:看 `meta.<platform>.error` 的 `tried` 列表;必要时用 `--config config.json` 换一批数据源。**注意:换源属于"报告落盘之后"的可选优化,不允许为换源推迟或放弃本轮交付。**
- **定时/无人值守任务**:没有用户可追问,必须先跑 `fallback_report.py` 落盘再补全;全部平台失败也要交出文件,并在报告里写清失败原因。
- **AIHOT 部分条目缺少 category/score**:说明该条不在 `/items?window=7d` 前 100 条内,属正常现象,表格分类留空即可,不影响出报告。
- **用户要更多/更少**:默认 10 条,可通过 `--top N` 调整,报告同步调整(AIHOT 官方榜上限即 10 条)。
- **用户要网页/HTML**:本 skill 只产出 Markdown,不提供渲染;如需网页,交给用户的查看器或自行用任意 Markdown 工具转换。

## 交付

- 最终交付 = Markdown 文件路径 + 平台榜首一句话总结。
- 若用户要求"直接发给我",用发送文件的方式交付。
