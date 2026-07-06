#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import urllib.parse

from fetch_common import canonical_external_id, clean_summary, fetch_json, format_date


DEFAULT_RECENT_DAYS = 14
DEFAULT_MIN_STARS = 10
DEFAULT_LIMIT = 8
DEFAULT_OUTPUT_DIR = Path("~/my_repos/news/github").expanduser()


def fetch_github_popular_repositories(
    recent_days: int = DEFAULT_RECENT_DAYS,
    min_stars: int = DEFAULT_MIN_STARS,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, str]]:
    since = (datetime.date.today() - datetime.timedelta(days=recent_days)).isoformat()
    query = f"created:>={since} stars:>={min_stars}"
    params = urllib.parse.urlencode(
        {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": "25",
        }
    )
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

        items.append(
            {
                "title": full_name,
                "link": link,
                "summary": " ".join(parts),
                "published": format_date(repo.get("created_at")),
                "dedupe_id": canonical_external_id(link),
            }
        )
    return items[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch popular recent GitHub repositories as news items.")
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--recent-days", type=int, default=DEFAULT_RECENT_DAYS)
    parser.add_argument("--min-stars", type=int, default=DEFAULT_MIN_STARS)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--stdout", action="store_true", help="Print JSON instead of writing github/YYYY-MM-DD.json")
    args = parser.parse_args()

    items = fetch_github_popular_repositories(
        recent_days=args.recent_days,
        min_stars=args.min_stars,
        limit=args.limit,
    )
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
