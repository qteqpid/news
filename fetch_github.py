#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.parse
import urllib.request

from fetch_common import USER_AGENT, canonical_external_id, clean_summary


DEFAULT_SINCE = "weekly"
DEFAULT_LIMIT = 20
DEFAULT_OUTPUT_DIR = Path("~/my_repos/news/github").expanduser()


class GitHubTrendingParser(HTMLParser):
    def __init__(self, published: str) -> None:
        super().__init__(convert_charrefs=True)
        self.published = published
        self.items: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.collecting_description = False
        self.collecting_language = False
        self.collecting_stars = False
        self.collecting_stars_today = False
        self.in_repo_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        css_class = attr.get("class", "")

        if tag == "article" and "Box-row" in css_class:
            self.current = {
                "title": "",
                "link": "",
                "description": "",
                "language": "",
                "stars": "",
                "stars_today": "",
            }
            return

        if self.current is None:
            return

        if tag == "h2":
            self.in_repo_heading = True

        if tag == "a":
            href = attr.get("href", "").strip()
            repo_match = repo_href_match(href)
            if self.in_repo_heading and repo_match and not self.current["title"]:
                full_name = "/".join(repo_match)
                self.current["title"] = full_name
                self.current["link"] = f"https://github.com/{full_name}"
            elif href.endswith("/stargazers"):
                self.collecting_stars = True

        if tag == "p" and "color-fg-muted" in css_class:
            self.collecting_description = True

        if tag == "span" and attr.get("itemprop") == "programmingLanguage":
            self.collecting_language = True

        if tag == "span" and "float-sm-right" in css_class:
            self.collecting_stars_today = True

    def handle_data(self, data: str) -> None:
        if self.current is None:
            return

        text = clean_summary(data)
        if not text:
            return

        if self.collecting_description:
            self.current["description"] = clean_summary(f"{self.current['description']} {text}")
        elif self.collecting_language:
            self.current["language"] = clean_summary(f"{self.current['language']} {text}")
        elif self.collecting_stars:
            self.current["stars"] = clean_summary(f"{self.current['stars']} {text}")
        elif self.collecting_stars_today:
            self.current["stars_today"] = clean_summary(f"{self.current['stars_today']} {text}")

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return

        if tag == "p":
            self.collecting_description = False
        elif tag == "h2":
            self.in_repo_heading = False
        elif tag == "span":
            self.collecting_language = False
            self.collecting_stars_today = False
        elif tag == "a":
            self.collecting_stars = False
        elif tag == "article":
            item = trending_item(self.current, self.published)
            if item:
                self.items.append(item)
            self.current = None
            self.collecting_description = False
            self.collecting_language = False
            self.collecting_stars = False
            self.collecting_stars_today = False
            self.in_repo_heading = False


def repo_href_match(href: str) -> tuple[str, str] | None:
    match = re_match_repo_path(urllib.parse.urlparse(href).path)
    if not match:
        return None
    return match


def re_match_repo_path(path: str) -> tuple[str, str] | None:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) != 2:
        return None
    owner, repo = parts
    return owner, repo


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def trending_item(raw: dict[str, str], published: str) -> dict[str, str] | None:
    title = raw.get("title", "").strip()
    link = raw.get("link", "").strip()
    if not title or not link:
        return None

    parts = []
    stars = clean_summary(raw.get("stars", ""))
    if stars:
        parts.append(f"[Stars: {stars}]")
    stars_today = clean_summary(raw.get("stars_today", ""))
    if stars_today:
        parts.append(f"[{stars_today}]")
    language = clean_summary(raw.get("language", ""))
    if language:
        parts.append(f"[Language: {language}]")
    description = clean_summary(raw.get("description", ""))
    if description:
        parts.append(description)

    return {
        "title": title,
        "link": link,
        "summary": " ".join(parts),
        "published": published,
        "dedupe_id": canonical_external_id(link),
    }


def load_seen_github_ids(output_dir: Path, current_date: str) -> set[str]:
    seen: set[str] = set()
    if not output_dir.is_dir():
        return seen

    for path in output_dir.glob("*.json"):
        if path.name == f"{current_date}.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            dedupe_id = str(item.get("dedupe_id") or "").strip()
            link = str(item.get("link") or item.get("url") or "").strip()
            if dedupe_id:
                seen.add(dedupe_id)
            if link:
                seen.add(canonical_external_id(link))
    return seen


def filter_unseen_repositories(items: list[dict[str, str]], seen_ids: set[str]) -> list[dict[str, str]]:
    filtered = []
    for item in items:
        dedupe_id = item.get("dedupe_id", "")
        if dedupe_id and dedupe_id in seen_ids:
            continue
        if dedupe_id:
            seen_ids.add(dedupe_id)
        filtered.append(item)
    return filtered


def fetch_github_trending_repositories(
    since: str = DEFAULT_SINCE,
    limit: int = DEFAULT_LIMIT,
    published: str | None = None,
) -> list[dict[str, str]]:
    params = urllib.parse.urlencode({"since": since})
    html = fetch_text(f"https://github.com/trending?{params}")
    parser = GitHubTrendingParser(published=published or datetime.date.today().isoformat())
    parser.feed(html)
    return parser.items[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch GitHub Trending repositories as news items.")
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--since", choices=("daily", "weekly", "monthly"), default=DEFAULT_SINCE)
    parser.add_argument("--stdout", action="store_true", help="Print JSON instead of writing github/YYYY-MM-DD.json")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    seen_ids = load_seen_github_ids(output_dir, args.date)
    trending_items = fetch_github_trending_repositories(
        since=args.since,
        limit=args.limit,
        published=args.date,
    )
    items = filter_unseen_repositories(trending_items, seen_ids)
    payload = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    if args.stdout:
        print(payload, end="")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{args.date}.json"
        output_path.write_text(payload, encoding="utf-8")
        print(f"DONE:{args.date}:{len(items)}:{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
