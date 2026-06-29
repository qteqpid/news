#!/usr/bin/env python3
"""
科技新闻每日抓取脚本
来源：AI/互联网/大厂相关 RSS 订阅
输出：~/Plan/news/YYYY-MM-DD.md
日志：~/Plan/news/news_log.txt
"""
import feedparser
import datetime
import html
import os
import json
import re
import ssl
import urllib.request

# feedparser doesn't use urllib.request.urlopen directly, so we pre-fetch the
# raw bytes and pass them in — this lets us set SSL context + User-Agent.
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

def fetch_feed(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15, context=_ssl_ctx)
        data = resp.read()
        return feedparser.parse(data)
    except Exception as e:
        return {"entries": [], "_fetch_error": str(e)}

TODAY = datetime.date.today().isoformat()
NEWS_DIR = os.path.expanduser("~/Plan/news")
OUTPUT_FILE = os.path.join(NEWS_DIR, f"{TODAY}.md")
LOG_FILE = os.path.join(NEWS_DIR, "news_log.txt")

FEEDS = [
    # AI 专项
    ("AI News - The Verge",       "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("MIT Tech Review - AI",      "https://www.technologyreview.com/feed/"),
    ("Ars Technica - AI",         "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    # 大厂科技
    ("TechCrunch",                "https://techcrunch.com/feed/"),
    ("The Verge",                 "https://www.theverge.com/rss/index.xml"),
    # 中文科技
    ("36氪",                      "https://36kr.com/feed"),
    ("少数派",                    "https://sspai.com/feed"),
    ("量子位",                    "https://www.qbitai.com/feed"),
    ("雷峰网",                    "https://www.leiphone.com/feed"),
    ("钛媒体",                    "https://www.tmtpost.com/rss.xml"),
    ("IT之家",                    "https://www.ithome.com/rss/"),
    ("Solidot",                   "https://www.solidot.org/index.rss"),
    ("爱范儿",                    "https://www.ifanr.com/feed"),
]

KEYWORDS = [
    "AI", "人工智能", "LLM", "GPT", "Claude", "Gemini", "OpenAI", "Anthropic",
    "Google", "Apple", "Microsoft", "Meta", "Tesla", "Amazon", "NVIDIA",
    "大模型", "机器学习", "deep learning", "neural", "AGI",
    "互联网", "科技", "tech", "startup", "融资", "IPO",
]

def is_relevant(title, summary=""):
    text = (title + " " + summary).lower()
    return any(kw.lower() in text for kw in KEYWORDS)

def clean_summary(summary):
    summary = re.sub(r'<[^>]+>', '', summary)
    summary = html.unescape(summary)
    summary = re.sub(r'\s+', ' ', summary).strip()
    summary = re.sub(r'#欢迎关注爱范儿官方微信公众号：.*$', '', summary).strip()
    summary = re.sub(r'(查看全文|阅读全文)\s*$', '', summary).strip()
    return summary

def fetch_all():
    results = {}
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
                    items.append({
                        "title": title,
                        "link": link,
                        "summary": summary.strip(),
                        "published": published,
                    })
            if items:
                results[source_name] = items[:8]
        except Exception as e:
            results[source_name] = [{"title": f"抓取失败: {e}", "link": "", "summary": "", "published": ""}]
    return results

def write_report(results):
    total = sum(len(v) for v in results.values())
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
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    return total

def log_done(total):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{TODAY} done ({total} items)\n")

if __name__ == "__main__":
    # Check if feedparser is available
    try:
        import feedparser
    except ImportError:
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "feedparser", "-q"])
        import feedparser

    results = fetch_all()
    total = write_report(results)
    log_done(total)
    print(f"DONE:{TODAY}:{total}")
