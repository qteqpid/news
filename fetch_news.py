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
APP_DIR = os.path.expanduser("~/my_repos/news/app")
OUTPUT_FILE = os.path.join(NEWS_DIR, f"{TODAY}.md")
LOG_FILE = os.path.join(NEWS_DIR, "news_log.txt")
GITHUB_RECENT_DAYS = 14
RSSHUB_BASE_URL = os.environ.get("RSSHUB_BASE_URL", "").rstrip("/")
ZHIHU_HOT_RSS_URLS = [
    f"{RSSHUB_BASE_URL}/zhihu/hot" if RSSHUB_BASE_URL else "",
    "https://rsshub.rssforever.com/zhihu/hot",
]

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

def normalize_title_id(title):
    title = clean_summary(str(title or "")).lower()
    title = re.sub(r"https?://\S+", "", title)
    title = re.sub(r"[^\w\u4e00-\u9fff]+", "", title)
    if len(title) < 6:
        return ""
    return f"title:{title[:140]}"

def extract_urls(text):
    if not text:
        return []
    return re.findall(r"https?://[^\s)\]>'\"]+", str(text))

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

    tracking_params = {"f", "from", "ref", "source", "spm", "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term"}
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key.lower() not in tracking_params and not key.lower().startswith("utm_")]
    normalized_query = urllib.parse.urlencode(query, doseq=True)
    normalized_path = re.sub(r"/+$", "", parsed.path)
    return urllib.parse.urlunparse((parsed.scheme.lower(), host, normalized_path, "", normalized_query, ""))

def item_dedupe_keys(title="", link=""):
    keys = set()
    links = extract_urls(link) or ([link] if link else [])
    title_id = normalize_title_id(title)
    for candidate in links:
        external_id = canonical_external_id(candidate)
        if external_id:
            keys.add(external_id)
    if title_id:
        keys.add(title_id)
    return keys

def add_history_keys_from_json(value, seen):
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

def add_history_keys_from_markdown(content, seen):
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

def load_seen_item_keys(history_dir, current_date=TODAY):
    seen = set()
    if not os.path.isdir(history_dir):
        return seen

    for filename in os.listdir(history_dir):
        if not (filename.endswith(".md") or filename.endswith(".json")):
            continue
        if filename.startswith(current_date):
            continue
        path = os.path.join(history_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
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

def load_seen_news_item_keys(current_date=TODAY):
    return load_seen_item_keys(NEWS_DIR, current_date)

def load_seen_app_item_keys(current_date=TODAY):
    return load_seen_item_keys(APP_DIR, current_date)

def load_seen_external_ids():
    return load_seen_news_item_keys()

def filter_unseen_items(items, seen_keys):
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

def filter_unseen_external_items(items, seen_ids):
    return filter_unseen_items(items, seen_ids)

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
        description = clean_summary(repo.get("description") or "")
        parts = [f"[Stars: {stars}]"]
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
    api_url = target.get("url", "")
    question = target.get("question") if isinstance(target.get("question"), dict) else {}
    question_id = question.get("id")

    if question_id and target_type == "answer" and target_id:
        return f"https://www.zhihu.com/question/{question_id}/answer/{target_id}"
    if question_id:
        return f"https://www.zhihu.com/question/{question_id}"
    if target_type == "question" and target_id:
        return f"https://www.zhihu.com/question/{target_id}"
    if target_type == "article" and target_id:
        return f"https://zhuanlan.zhihu.com/p/{target_id}"
    api_question_match = re.search(r"/questions/(\d+)", api_url)
    if api_question_match:
        return f"https://www.zhihu.com/question/{api_question_match.group(1)}"
    return target.get("url", "")

def fetch_zhihu_hot_posts():
    try:
        data = fetch_json(
            "https://api.zhihu.com/topstory/hot-lists/total?limit=30&reverse_order=0",
            headers={
                "Referer": "https://www.zhihu.com/hot",
                "X-Requested-With": "fetch",
            },
        )
    except Exception:
        return fetch_zhihu_hot_posts_from_rss()

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

def fetch_zhihu_hot_posts_from_rss():
    for url in [candidate for candidate in ZHIHU_HOT_RSS_URLS if candidate]:
        feed = fetch_feed(url)
        items = []
        for entry in feed.get("entries", [])[:30]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue
            items.append({
                "title": title,
                "link": link,
                "summary": clean_summary(entry.get("summary", ""))[:200],
                "published": entry.get("published", "")[:16],
                "dedupe_id": canonical_external_id(link),
            })
        if items:
            return items[:8]
    return []

def add_external_sources(results, seen_keys):
    external_sources = [
        ("Github", fetch_github_popular_repositories),
        ("Zhihu", fetch_zhihu_hot_posts),
    ]
    for source_name, fetcher in external_sources:
        try:
            items = filter_unseen_items(fetcher(), seen_keys)
        except Exception:
            items = []
        if items:
            results[source_name] = items

def fetch_all():
    results = {}
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
        except Exception as e:
            results[source_name] = [{"title": f"抓取失败: {e}", "link": "", "summary": "", "published": ""}]
    add_external_sources(results, seen_keys)
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
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "--seen-keys":
        scope = sys.argv[2] if len(sys.argv) >= 3 else "news"
        if scope == "app":
            keys = load_seen_app_item_keys()
        elif scope in ("news", "ai"):
            keys = load_seen_news_item_keys()
        else:
            raise SystemExit("usage: fetch_news.py --seen-keys [news|app]")
        print(json.dumps(sorted(keys), ensure_ascii=False, indent=2))
        raise SystemExit(0)

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
