#!/usr/bin/env python3
"""
Run the Reddit app-idea miner from the news repo and write app-ready JSON.

Output:
  ~/my_repos/news/reddit/YYYY-MM-DD.json

The JSON intentionally matches the flat shape used by news/ai:
  [{"title": "...", "summary": "...", "url": "...", "source": "REDDIT"}]
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any


NEWS_ROOT = Path(__file__).resolve().parent
DEFAULT_REDDIT_DIR = NEWS_ROOT / "reddit"
DEFAULT_MINER_ROOT = Path(
    os.environ.get("REDDIT_APP_IDEA_MINER_DIR", "~/my_repos/reddit-app-idea-miner")
).expanduser()


def clean_text(value: str, max_len: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if max_len and len(text) > max_len:
        return f"{text[: max_len - 1]}..."
    return text


def normalize_title(value: str) -> str:
    text = clean_text(value).lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)[:160]


def load_miner(miner_root: Path) -> ModuleType:
    script = miner_root / "scripts" / "analyze.py"
    if not script.exists():
        raise FileNotFoundError(f"Cannot find Reddit miner analyzer: {script}")

    scripts_dir = str(script.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    spec = importlib.util.spec_from_file_location("reddit_app_idea_miner_analyze", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Reddit miner analyzer: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def existing_json_exports(miner_root: Path, date: str) -> list[Path]:
    exports_dir = miner_root / "exports"
    if not exports_dir.is_dir():
        return []

    preferred = exports_dir / f"reddit-route-export-{date}.json"
    candidates: list[Path] = []
    if preferred.exists():
        candidates.append(preferred)

    dated = sorted(
        exports_dir.glob(f"*{date}*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    latest = sorted(
        exports_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for path in [*dated, *latest]:
        if path not in candidates:
            candidates.append(path)

    return [path for path in candidates if path.is_file() and path.stat().st_size > 2]


def load_seen_keys(output_dir: Path, current_date: str) -> set[str]:
    seen: set[str] = set()
    if not output_dir.is_dir():
        return seen

    for path in output_dir.glob("*.json"):
        if path.name.startswith(current_date):
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
            url = clean_text(item.get("url", ""))
            title_key = normalize_title(item.get("title", ""))
            if url:
                seen.add(f"url:{url}")
            if title_key:
                seen.add(f"title:{title_key}")
    return seen


def signal_keys(signal: Any) -> set[str]:
    post = signal.post
    keys: set[str] = set()
    url = clean_text(post.reddit_url)
    title_key = normalize_title(post.title)
    if url:
        keys.add(f"url:{url}")
    if title_key:
        keys.add(f"title:{title_key}")
    return keys


def format_summary(signal: Any) -> str:
    post = signal.post
    matched = "、".join(signal.matched_signals)
    source = f"r/{post.subreddit}"
    engagement = f"{post.score} upvotes、{post.num_comments} comments"
    excerpt = clean_text(post.selftext or post.title, 240)
    parts = [
        f"{excerpt}，{engagement}",
        f"，类型：{signal.signal_type}，评分：{signal.opportunity_score}/10。",
    ]
    return clean_text(" ".join(parts), 420)


def to_flat_items(signals: list[Any], max_items: int, seen_keys: set[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for signal in signals:
        keys = signal_keys(signal)
        if keys and keys & seen_keys:
            continue
        seen_keys.update(keys)
        items.append(
            {
                "title": clean_text(signal.post.title),
                "summary": format_summary(signal),
                "url": clean_text(signal.post.reddit_url),
                "source": "REDDIT",
            }
        )
        if len(items) >= max_items:
            break
    return items


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate news/reddit/YYYY-MM-DD.json from reddit-app-idea-miner signals."
    )
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Output date, defaults to today")
    parser.add_argument("--miner-root", default=str(DEFAULT_MINER_ROOT), help="Path to reddit-app-idea-miner")
    parser.add_argument("--output-dir", default=str(DEFAULT_REDDIT_DIR), help="Directory for flat Reddit JSON")
    parser.add_argument("--browser-export", nargs="+", help="Use one or more miner browser-export JSON files")
    parser.add_argument(
        "--no-export-fallback",
        action="store_true",
        help="Do not auto-use the latest miner export",
    )
    parser.add_argument("--sample", action="store_true", help="Use miner sample posts; no network")
    parser.add_argument("--max-items", type=int, default=30, help="Maximum flat JSON items to write")
    parser.add_argument("--min-score", type=float, help="Minimum miner opportunity score")
    parser.add_argument("--quiet", action="store_true", help="Suppress miner progress logs")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    miner_root = Path(args.miner_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    miner = load_miner(miner_root)
    miner.LOGGER = miner.RunLogger(echo=not args.quiet)
    config = miner.load_config(miner_root / "config" / "miner_config.json")

    browser_exports = [Path(path).expanduser() for path in args.browser_export or []]
    if not args.sample and not browser_exports and not args.no_export_fallback:
        browser_exports = existing_json_exports(miner_root, args.date)[:1]

    if not args.sample and not browser_exports:
        export_path = miner_root / "exports" / f"reddit-route-export-{args.date}.json"
        raise SystemExit(
            "No Reddit browser export found. fetch_reddit.py only reads browser exports; "
            "it does not call the Reddit JSON API directly.\n"
            "First collect with a real browser, then run this script again:\n"
            f"  cd {miner_root}\n"
            f"  python3 scripts/collect_routes.py --browser chrome --hydrate-details --output {export_path}\n"
            f"  python3 {Path(__file__).resolve()}\n"
        )

    miner_args = SimpleNamespace(
        sample=args.sample,
        browser_export=[str(path) for path in browser_exports] or None,
        quiet=args.quiet,
    )

    posts, errors = miner.collect_posts(config, miner_args, miner_root)
    min_score = float(args.min_score if args.min_score is not None else config.get("min_score", 4.5))
    signals = [
        signal
        for signal in miner.analyze_posts(miner.dedupe_posts(posts))
        if signal.opportunity_score >= min_score
    ]

    seen_keys = load_seen_keys(output_dir, args.date)
    items = to_flat_items(signals, args.max_items, seen_keys)
    output_path = output_dir / f"{args.date}.json"
    output_path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if errors:
        print(f"WARN:{len(errors)} reddit fetch errors; generated from available posts.", file=sys.stderr)
    if browser_exports:
        print(f"USED_EXPORT:{browser_exports[0]}")
    print(f"DONE:{args.date}:{len(items)}:{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
