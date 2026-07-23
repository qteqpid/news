#!/usr/bin/env python3
"""
科技新闻每日抓取脚本
来源：AI/互联网/大厂相关 RSS 订阅
输出：~/my_repos/news/ai/YYYY-MM-DD.md
日志：~/my_repos/news/ai/news_log.txt
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys

from fetch_common import clean_summary, extract_urls, fetch_feed, item_dedupe_keys


TODAY = datetime.date.today().isoformat()
NEWS_DIR = os.path.expanduser("~/my_repos/news/ai")
APP_DIR = os.path.expanduser("~/my_repos/news/app")
OUTPUT_FILE = os.path.join(NEWS_DIR, f"{TODAY}.md")
LOG_FILE = os.path.join(NEWS_DIR, "news_log.txt")

FEEDS = [
    ("OpenAI News", "https://openai.com/news/rss.xml"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    ("Google AI Blog", "https://blog.google/innovation-and-ai/technology/ai/rss/"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("arXiv cs.CL", "https://rss.arxiv.org/rss/cs.CL"),
    ("arXiv cs.AI", "https://rss.arxiv.org/rss/cs.AI"),
    ("arXiv cs.LG", "https://rss.arxiv.org/rss/cs.LG"),
    ("AI News - The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("MIT Tech Review - AI", "https://www.technologyreview.com/feed/"),
    ("Ars Technica - AI", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("36氪", "https://36kr.com/feed"),
    ("少数派", "https://sspai.com/feed"),
    ("量子位", "https://www.qbitai.com/feed"),
    ("雷峰网", "https://www.leiphone.com/feed"),
    ("钛媒体", "https://www.tmtpost.com/rss.xml"),
    ("IT之家", "https://www.ithome.com/rss/"),
    ("Solidot", "https://www.solidot.org/index.rss"),
    ("爱范儿", "https://www.ifanr.com/feed"),
]

KEYWORDS = [
    "AI",
    "人工智能",
    "LLM",
    "large language model",
    "language model",
    "GPT",
    "Claude",
    "Gemini",
    "OpenAI",
    "Anthropic",
    "Google",
    "Apple",
    "Microsoft",
    "Meta",
    "Tesla",
    "Amazon",
    "NVIDIA",
    "大模型",
    "机器学习",
    "deep learning",
    "neural",
    "transformer",
    "agent",
    "reasoning",
    "inference",
    "benchmark",
    "AGI",
    "互联网",
    "科技",
    "tech",
    "startup",
    "融资",
    "IPO",
]


def is_relevant(title: str, summary: str = "") -> bool:
    text = (title + " " + summary).lower()
    return any(keyword.lower() in text for keyword in KEYWORDS)


def add_history_keys_from_json(value, seen: set[str]) -> None:
    if isinstance(value, dict):
        link = value.get("url") or value.get("link") or ""
        title = value.get("title") or ""
        if link:
            seen.update(item_dedupe_keys("", link))
        if title and any(key in value for key in ("summary", "source", "source_signal", "pain", "mvp", "url", "link")):
            seen.update(item_dedupe_keys(title, link))
        for child in value.values():
            add_history_keys_from_json(child, seen)
    elif isinstance(value, list):
        for child in value:
            add_history_keys_from_json(child, seen)


def add_history_keys_from_markdown(content: str, seen: set[str]) -> None:
    linked_title_pattern = re.compile(r"\*\*\[([^\]]+)\]\((https?://[^)]+)\)\*\*")
    bold_title_pattern = re.compile(r"^-\s+\*\*([^*]+)\*\*[：:]", re.MULTILINE)
    app_idea_pattern = re.compile(r"^###\s+\d+\.\s+(.+)$", re.MULTILINE)

    for title, link in linked_title_pattern.findall(content):
        seen.update(item_dedupe_keys(title, link))
    for title in bold_title_pattern.findall(content):
        seen.update(item_dedupe_keys(title, ""))
    for title in app_idea_pattern.findall(content):
        seen.update(item_dedupe_keys(title, ""))
    for link in extract_urls(content):
        seen.update(item_dedupe_keys("", link))


def load_seen_item_keys(history_dir: str, current_date: str = TODAY) -> set[str]:
    seen: set[str] = set()
    if not os.path.isdir(history_dir):
        return seen

    for filename in os.listdir(history_dir):
        if not (filename.endswith(".md") or filename.endswith(".json")):
            continue
        if filename.startswith(current_date):
            continue
        path = os.path.join(history_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as file:
                content = file.read()
        except OSError:
            continue

        if filename.endswith(".json"):
            try:
                add_history_keys_from_json(json.loads(content), seen)
            except json.JSONDecodeError:
                add_history_keys_from_markdown(content, seen)
        else:
            add_history_keys_from_markdown(content, seen)
    return seen


def load_seen_news_item_keys(current_date: str = TODAY) -> set[str]:
    return load_seen_item_keys(NEWS_DIR, current_date)


def load_seen_app_item_keys(current_date: str = TODAY) -> set[str]:
    return load_seen_item_keys(APP_DIR, current_date)


def filter_unseen_items(items: list[dict[str, str]], seen_keys: set[str]) -> list[dict[str, str]]:
    filtered = []
    for item in items:
        keys = item_dedupe_keys(item.get("title", ""), item.get("link", ""))
        if item.get("dedupe_id"):
            keys.add(item["dedupe_id"])
        if not keys or keys & seen_keys:
            continue
        seen_keys.update(keys)
        filtered.append(item)
    return filtered


def fetch_all() -> dict[str, list[dict[str, str]]]:
    results: dict[str, list[dict[str, str]]] = {}
    seen_keys = load_seen_news_item_keys()
    for source_name, url in FEEDS:
        try:
            feed = fetch_feed(url)
            items = []
            for entry in feed.entries[:30]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                summary = clean_summary(entry.get("summary", ""))[:200]
                published = entry.get("published", "")[:16]
                if is_relevant(title, summary):
                    candidate = {
                        "title": title,
                        "link": link,
                        "summary": summary.strip(),
                        "published": published,
                    }
                    items.extend(filter_unseen_items([candidate], seen_keys))
            if items:
                results[source_name] = items[:8]
        except Exception as error:
            results[source_name] = [{"title": f"抓取失败: {error}", "link": "", "summary": "", "published": ""}]
    return results


def write_report(results: dict[str, list[dict[str, str]]]) -> int:
    total = sum(len(items) for items in results.values())
    lines = [
        f"# 科技新闻日报 {TODAY}",
        f"> 共抓取 {total} 条相关新闻\n",
    ]
    for source, items in results.items():
        if not items:
            continue
        lines.append(f"\n## {source}\n")
        for item in items:
            lines.append(f"- **[{item['title']}]({item['link']})**")
            if item["summary"]:
                lines.append(f"  {item['summary'][:120]}...")
    content = "\n".join(lines)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        file.write(content)
    return total


def log_done(total: int) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(f"{TODAY} done ({total} items)\n")


def ensure_feedparser() -> None:
    try:
        import feedparser  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "feedparser", "-q"])


def main(argv: list[str]) -> int:
    if len(argv) >= 1 and argv[0] == "--seen-keys":
        scope = argv[1] if len(argv) >= 2 else "news"
        if scope == "app":
            keys = load_seen_app_item_keys()
        elif scope in ("news", "ai"):
            keys = load_seen_news_item_keys()
        else:
            raise SystemExit("usage: fetch_news.py --seen-keys [news|app]")
        print(json.dumps(sorted(keys), ensure_ascii=False, indent=2))
        return 0

    ensure_feedparser()
    results = fetch_all()
    total = write_report(results)
    log_done(total)
    print(f"DONE:{TODAY}:{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
