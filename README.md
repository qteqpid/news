# News Pipeline

[中文](#中文) · [English](#english)

Daily news and app-idea automation for the `ai_news` iOS app. The project keeps each data source independent, validates each source output separately, and generates one final flat JSON feed under `all_news/`.

## 中文

`news` 是一个每日数据流水线项目，用来抓取和整理 AI/科技新闻、GitHub 热门项目、知乎热榜、Reddit app idea 信号，以及模型整理的 App idea。每个数据源都是独立 source：如果某个 source 已完成，重新跑流程时会跳过它，只执行缺失的部分。

### 快速开始

查看所有 source：

```bash
python3 daily_pipeline.py list-sources
```

查看今天各 source 是否完成：

```bash
python3 daily_pipeline.py status
```

执行完整流程：

```bash
python3 daily_pipeline.py run
```

执行指定日期：

```bash
python3 daily_pipeline.py run --date 2026-07-07
```

只执行某个 source：

```bash
python3 daily_pipeline.py run --date 2026-07-07 --source reddit
```

### 当前 source

Pipeline 当前顺序由 `sources/*.json` 里的 `order` 决定：

| Source | 输出 | 负责脚本/方式 | 定位 |
| --- | --- | --- | --- |
| `github` | `github/YYYY-MM-DD.json` | `fetch_github.py` | GitHub 近期热门项目 |
| `zhihu` | `zhihu/YYYY-MM-DD.json` | `fetch_zhihu.py` | 知乎热榜 |
| `ai` | `ai/YYYY-MM-DD.md`、`ai/YYYY-MM-DD.json` | `fetch_news.py` + model step | RSS/AI 科技新闻 |
| `app` | `app/YYYY-MM-DD.md`、`app/YYYY-MM-DD.json` | model step | App idea 灵感整理 |
| `reddit` | `reddit/YYYY-MM-DD.json` | `fetch_reddit.py` | Reddit app idea 信号 |
| `all_news` | `all_news/YYYY-MM-DD.json` | `fetch_all_news.py` | iOS app 最终读取的聚合 JSON |

### iOS App 输出格式

`all_news/YYYY-MM-DD.json` 是最终给 `ai_news` iOS app 读取的文件。它是一个平铺 JSON array，每个 item 字段完全一致：

```json
[
  {
    "title": "Title",
    "summary": "Short summary",
    "url": "https://example.com",
    "source": "SOURCE"
  }
]
```

`fetch_all_news.py` 会读取当天各子 source 的 JSON array，并规范化成上面的四字段格式：

- `link` 会转换成 `url`
- 缺失的 `source` 会补成 source 名的大写形式，如 `GITHUB`、`ZHIHU`
- 额外字段会被丢弃，确保 iOS 端只看到 `title`、`summary`、`url`、`source`

### 项目结构

```text
news/
  daily_pipeline.py       # 主流程入口：status/run/hook-context/list-sources
  daily_lib.py            # pipeline 公共库：加载 source、校验输出、执行 step
  fetch_common.py         # 抓取脚本公共工具：HTTP、RSS、清洗、去重 key
  fetch_news.py           # RSS/AI 科技新闻
  fetch_github.py         # GitHub source
  fetch_zhihu.py          # Zhihu source
  fetch_reddit.py         # Reddit source bridge
  fetch_all_news.py       # 最终平铺聚合
  git_auto_sync.sh        # 定时 git 同步

  sources/                # 每个 source 的 pipeline 配置
  steps/                  # 检查、执行、验证辅助脚本

  ai/                     # AI/RSS 新闻输出
  app/                    # App idea 输出
  github/                 # GitHub 输出
  zhihu/                  # Zhihu 输出
  reddit/                 # Reddit 输出
  all_news/               # iOS app 最终 JSON 输出
```

### 扩展新 source

新增数据源时，优先新增独立脚本和独立配置：

1. 新增输出目录，例如 `xiaohongshu/`
2. 新增抓取脚本，例如 `fetch_xiaohongshu.py`
3. 新增 `sources/xiaohongshu.json`
4. 如果要进入 iOS 最终 feed，确保输出是 JSON array，`fetch_all_news.py` 会在最后汇总

主流程 `daily_pipeline.py` 通常不需要改。

### 验证

检查所有输出：

```bash
python3 steps/check_outputs.py --json
```

验证所有输出 schema：

```bash
python3 steps/validate_outputs.py --json
```

验证最终 iOS feed：

```bash
python3 steps/validate_outputs.py --source all_news --json
```

### 自动化

Codex SessionStart hook 直接调用：

```bash
python3 ~/my_repos/news/daily_pipeline.py hook-context
```

本项目不再使用 `check_and_fetch.sh` 中转脚本。仓库同步由 `git_auto_sync.sh` 负责。

## English

`news` is a daily data pipeline for collecting and preparing AI/technology news, popular GitHub repositories, Zhihu hot topics, Reddit app-idea signals, and model-organized app ideas. Each data source is an independent pipeline source. If one source has already completed for a date, rerunning the pipeline skips it and continues with only the missing parts.

### Quick Start

List sources:

```bash
python3 daily_pipeline.py list-sources
```

Check today's status:

```bash
python3 daily_pipeline.py status
```

Run the full pipeline:

```bash
python3 daily_pipeline.py run
```

Run a specific date:

```bash
python3 daily_pipeline.py run --date 2026-07-07
```

Run a single source:

```bash
python3 daily_pipeline.py run --date 2026-07-07 --source reddit
```

### Sources

The source order is controlled by `order` in `sources/*.json`:

| Source | Output | Script / Method | Purpose |
| --- | --- | --- | --- |
| `github` | `github/YYYY-MM-DD.json` | `fetch_github.py` | Popular recent GitHub repositories |
| `zhihu` | `zhihu/YYYY-MM-DD.json` | `fetch_zhihu.py` | Zhihu hot topics |
| `ai` | `ai/YYYY-MM-DD.md`, `ai/YYYY-MM-DD.json` | `fetch_news.py` + model step | RSS-based AI and technology news |
| `app` | `app/YYYY-MM-DD.md`, `app/YYYY-MM-DD.json` | model step | App idea generation |
| `reddit` | `reddit/YYYY-MM-DD.json` | `fetch_reddit.py` | Reddit app-idea signals |
| `all_news` | `all_news/YYYY-MM-DD.json` | `fetch_all_news.py` | Final JSON feed for the iOS app |

### iOS App Feed

`all_news/YYYY-MM-DD.json` is the final file consumed by the `ai_news` iOS app. It is a flat JSON array with exactly four string fields per item:

```json
[
  {
    "title": "Title",
    "summary": "Short summary",
    "url": "https://example.com",
    "source": "SOURCE"
  }
]
```

`fetch_all_news.py` reads each source JSON array for the target date and normalizes every item into this schema:

- `link` is converted to `url`
- missing `source` values are filled with the uppercase source name, such as `GITHUB` or `ZHIHU`
- extra fields are dropped so the iOS app only receives `title`, `summary`, `url`, and `source`

### Project Structure

```text
news/
  daily_pipeline.py       # Main pipeline entry: status/run/hook-context/list-sources
  daily_lib.py            # Shared pipeline helpers
  fetch_common.py         # Shared fetch helpers
  fetch_news.py           # RSS/AI technology news
  fetch_github.py         # GitHub source
  fetch_zhihu.py          # Zhihu source
  fetch_reddit.py         # Reddit source bridge
  fetch_all_news.py       # Final flat aggregation
  git_auto_sync.sh        # Scheduled git sync

  sources/                # Per-source pipeline configs
  steps/                  # Check, run, and validation helpers

  ai/                     # AI/RSS news outputs
  app/                    # App idea outputs
  github/                 # GitHub outputs
  zhihu/                  # Zhihu outputs
  reddit/                 # Reddit outputs
  all_news/               # Final iOS app JSON output
```

### Adding a Source

To add a new data source:

1. Add an output directory, for example `xiaohongshu/`
2. Add a fetch script, for example `fetch_xiaohongshu.py`
3. Add `sources/xiaohongshu.json`
4. If it should appear in the final iOS feed, output a JSON array; `fetch_all_news.py` will aggregate it at the end

The main `daily_pipeline.py` usually does not need changes.

### Validation

Check all outputs:

```bash
python3 steps/check_outputs.py --json
```

Validate schemas:

```bash
python3 steps/validate_outputs.py --json
```

Validate the final iOS feed:

```bash
python3 steps/validate_outputs.py --source all_news --json
```

### Automation

The Codex SessionStart hook calls the pipeline directly:

```bash
python3 ~/my_repos/news/daily_pipeline.py hook-context
```

The old `check_and_fetch.sh` wrapper is no longer used. Repository syncing is handled by `git_auto_sync.sh`.
