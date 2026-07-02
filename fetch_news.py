#!/usr/bin/env python3
"""
科技新闻每日抓取脚本
来源：AI/互联网/大厂相关 RSS 订阅
输出：~/my_repos/news/ai/YYYY-MM-DD.md
日志：~/my_repos/news/ai/news_log.txt
"""
import feedparser
import datetime
import html
import os
import json
import re
import ssl
import urllib.parse
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
NEWS_DIR = os.path.expanduser("~/my_repos/news/ai")
OUTPUT_FILE = os.path.join(NEWS_DIR, f"{TODAY}.md")
LOG_FILE = os.path.join(NEWS_DIR, "news_log.txt")
GITHUB_RECENT_DAYS = 14

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

def fetch_json(url, headers=None):
    request_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))

def format_date(value):
    if not value:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(value).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    return str(value)[:10]

def canonical_external_id(url):
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")

    github_match = re.match(r"^([^/]+)/([^/]+)", path)
    if host == "github.com" and github_match:
        owner, repo = github_match.groups()
        return f"github:{owner.lower()}/{repo.lower()}"

    if host.endswith("zhihu.com"):
        question_match = re.search(r"(?:^|/)question/(\d+)", path)
        if question_match:
            return f"zhihu:question:{question_match.group(1)}"
        article_match = re.search(r"(?:^|/)p/(\d+)", path)
        if article_match:
            return f"zhihu:article:{article_match.group(1)}"

    normalized_path = re.sub(r"/+$", "", parsed.path)
    return urllib.parse.urlunparse((parsed.scheme.lower(), host, normalized_path, "", "", ""))

def load_seen_external_ids():
    seen = set()
    if not os.path.isdir(NEWS_DIR):
        return seen

    github_pattern = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+")
    zhihu_patterns = [
        re.compile(r"https?://(?:www\.)?zhihu\.com/question/\d+(?:/answer/\d+)?"),
        re.compile(r"https?://zhuanlan\.zhihu\.com/p/\d+"),
    ]

    for filename in os.listdir(NEWS_DIR):
        if not (filename.endswith(".md") or filename.endswith(".json")):
            continue
        if filename.startswith(TODAY):
            continue
        path = os.path.join(NEWS_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue

        for pattern in [github_pattern, *zhihu_patterns]:
            for match in pattern.findall(content):
                external_id = canonical_external_id(match)
                if external_id:
                    seen.add(external_id)
    return seen

def filter_unseen_external_items(items, seen_ids):
    filtered = []
    for item in items:
        external_id = item.get("dedupe_id") or canonical_external_id(item.get("link", ""))
        if not external_id or external_id in seen_ids:
            continue
        seen_ids.add(external_id)
        filtered.append(item)
    return filtered

def fetch_github_popular_repositories():
    since = (datetime.date.today() - datetime.timedelta(days=GITHUB_RECENT_DAYS)).isoformat()
    query = f"created:>={since} stars:>=10"
    params = urllib.parse.urlencode({
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": "25",
    })
    data = fetch_json(
        f"https://api.github.com/search/repositories?{params}",
        headers={"Accept": "application/vnd.github+json"},
    )

    items = []
    for repo in data.get("items", []):
        full_name = repo.get("full_name", "").strip()
        link = repo.get("html_url", "").strip()
        if not full_name or not link:
            continue

        stars = repo.get("stargazers_count", 0)
        language = repo.get("language") or "Unknown"
        description = clean_summary(repo.get("description") or "")
        parts = [
            f"最近 {GITHUB_RECENT_DAYS} 天新建的热门仓库，当前约 {stars} stars，主要语言：{language}。",
        ]
        if description:
            parts.append(description)

        items.append({
            "title": full_name,
            "link": link,
            "summary": " ".join(parts),
            "published": format_date(repo.get("created_at")),
            "dedupe_id": canonical_external_id(link),
        })
    return items[:8]

def zhihu_public_url(target):
    target_type = target.get("type", "")
    target_id = target.get("id")
    question = target.get("question") if isinstance(target.get("question"), dict) else {}
    question_id = question.get("id")

    if question_id and target_type == "answer" and target_id:
        return f"https://www.zhihu.com/question/{question_id}/answer/{target_id}"
    if question_id:
        return f"https://www.zhihu.com/question/{question_id}"
    if target_type == "article" and target_id:
        return f"https://zhuanlan.zhihu.com/p/{target_id}"
    return target.get("url", "")

def fetch_zhihu_hot_posts():
    data = fetch_json(
        "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=30&desktop=true",
        headers={
            "Referer": "https://www.zhihu.com/hot",
            "X-Requested-With": "fetch",
        },
    )

    items = []
    for entry in data.get("data", []):
        target = entry.get("target") if isinstance(entry.get("target"), dict) else {}
        question = target.get("question") if isinstance(target.get("question"), dict) else {}
        title = (question.get("title") or target.get("title") or entry.get("title") or "").strip()
        link = zhihu_public_url(target).strip()
        if not title or not link:
            continue

        detail = clean_summary(entry.get("detail_text") or "")
        excerpt = clean_summary(target.get("excerpt") or target.get("excerpt_new") or "")
        summary_parts = []
        if detail:
            summary_parts.append(detail)
        if excerpt:
            summary_parts.append(excerpt)

        items.append({
            "title": title,
            "link": link,
            "summary": " ".join(summary_parts)[:200],
            "published": format_date(question.get("created") or target.get("created_time")),
            "dedupe_id": canonical_external_id(link),
        })
    return items[:8]

def add_external_sources(results):
    seen_ids = load_seen_external_ids()
    external_sources = [
        ("GitHub 热门项目", fetch_github_popular_repositories),
        ("知乎热门帖子", fetch_zhihu_hot_posts),
    ]
    for source_name, fetcher in external_sources:
        try:
            items = filter_unseen_external_items(fetcher(), seen_ids)
        except Exception:
            items = []
        if items:
            results[source_name] = items

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
    add_external_sources(results)
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
