#!/usr/bin/env python3
from __future__ import annotations

import datetime
import html
import json
import re
import ssl
import urllib.parse
import urllib.request


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def clean_summary(summary: str) -> str:
    summary = re.sub(r"<[^>]+>", "", str(summary or ""))
    summary = html.unescape(summary)
    summary = re.sub(r"\s+", " ", summary).strip()
    summary = re.sub(r"#欢迎关注爱范儿官方微信公众号：.*$", "", summary).strip()
    summary = re.sub(r"(查看全文|阅读全文)\s*$", "", summary).strip()
    return summary


def fetch_feed(url: str):
    import feedparser

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urllib.request.urlopen(req, timeout=15, context=_ssl_ctx)
        data = resp.read()
        return feedparser.parse(data)
    except Exception as error:
        return {"entries": [], "_fetch_error": str(error)}


def fetch_json(url: str, headers: dict[str, str] | None = None):
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def format_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(value).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    return str(value)[:10]


def normalize_title_id(title: str) -> str:
    title = clean_summary(str(title or "")).lower()
    title = re.sub(r"https?://\S+", "", title)
    title = re.sub(r"[^\w\u4e00-\u9fff]+", "", title)
    if len(title) < 6:
        return ""
    return f"title:{title[:140]}"


def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"https?://[^\s)\]>'\"]+", str(text))


def canonical_external_id(url: str) -> str:
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

    tracking_params = {
        "f",
        "from",
        "ref",
        "source",
        "spm",
        "utm_campaign",
        "utm_content",
        "utm_medium",
        "utm_source",
        "utm_term",
    }
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [
        (key, value)
        for key, value in query
        if key.lower() not in tracking_params and not key.lower().startswith("utm_")
    ]
    normalized_query = urllib.parse.urlencode(query, doseq=True)
    normalized_path = re.sub(r"/+$", "", parsed.path)
    return urllib.parse.urlunparse((parsed.scheme.lower(), host, normalized_path, "", normalized_query, ""))


def item_dedupe_keys(title: str = "", link: str = "") -> set[str]:
    keys: set[str] = set()
    links = extract_urls(link) or ([link] if link else [])
    title_id = normalize_title_id(title)
    for candidate in links:
        external_id = canonical_external_id(candidate)
        if external_id:
            keys.add(external_id)
    if title_id:
        keys.add(title_id)
    return keys
