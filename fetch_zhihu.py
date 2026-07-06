#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
from pathlib import Path

from fetch_common import canonical_external_id, clean_summary, fetch_feed, fetch_json, format_date


DEFAULT_LIMIT = 8
DEFAULT_OUTPUT_DIR = Path("~/my_repos/news/zhihu").expanduser()
RSSHUB_BASE_URL = os.environ.get("RSSHUB_BASE_URL", "").rstrip("/")
ZHIHU_HOT_RSS_URLS = [
    f"{RSSHUB_BASE_URL}/zhihu/hot" if RSSHUB_BASE_URL else "",
    "https://rsshub.rssforever.com/zhihu/hot",
]


def zhihu_public_url(target: dict) -> str:
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


def fetch_zhihu_hot_posts(limit: int = DEFAULT_LIMIT) -> list[dict[str, str]]:
    try:
        data = fetch_json(
            "https://api.zhihu.com/topstory/hot-lists/total?limit=30&reverse_order=0",
            headers={
                "Referer": "https://www.zhihu.com/hot",
                "X-Requested-With": "fetch",
            },
        )
    except Exception:
        return fetch_zhihu_hot_posts_from_rss(limit=limit)

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

        items.append(
            {
                "title": title,
                "link": link,
                "summary": " ".join(summary_parts)[:200],
                "published": format_date(question.get("created") or target.get("created_time")),
                "dedupe_id": canonical_external_id(link),
            }
        )
    return items[:limit]


def fetch_zhihu_hot_posts_from_rss(limit: int = DEFAULT_LIMIT) -> list[dict[str, str]]:
    for url in [candidate for candidate in ZHIHU_HOT_RSS_URLS if candidate]:
        feed = fetch_feed(url)
        items = []
        for entry in feed.get("entries", [])[:30]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "link": link,
                    "summary": clean_summary(entry.get("summary", ""))[:200],
                    "published": entry.get("published", "")[:16],
                    "dedupe_id": canonical_external_id(link),
                }
            )
        if items:
            return items[:limit]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Zhihu hot posts as news items.")
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--stdout", action="store_true", help="Print JSON instead of writing zhihu/YYYY-MM-DD.json")
    args = parser.parse_args()

    items = fetch_zhihu_hot_posts(limit=args.limit)
    payload = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    if args.stdout:
        print(payload, end="")
    else:
        output_dir = Path(args.output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{args.date}.json"
        output_path.write_text(payload, encoding="utf-8")
        print(f"DONE:{args.date}:{len(items)}:{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
