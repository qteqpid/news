#!/usr/bin/env python3
"""
Run the Reddit app-idea miner from the news repo and write app-ready JSON.

Output:
  ~/my_repos/news/reddit/YYYY-MM-DD.json

The JSON intentionally matches the flat shape used by news/ai:
  [{"title": "...", "summary": "...", "url": "...", "source": "Reddit - Apps"}]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any


NEWS_ROOT = Path(__file__).resolve().parent
DEFAULT_REDDIT_DIR = NEWS_ROOT / "reddit"
DEFAULT_DETAIL_CACHE_DIR = NEWS_ROOT / "reddit_detail_cache"
DEFAULT_MINER_ROOT = Path(
    os.environ.get("REDDIT_APP_IDEA_MINER_DIR", "~/my_repos/reddit-app-idea-miner")
).expanduser()
DEFAULT_DAILY_ROUTES = "config/routes_daily.json"
DEFAULT_SOURCE_FLOWS: dict[str, dict[str, Any]] = {
    "Reddit - APP": {"scoring": "opportunity", "hydrate_details": False},
    "Reddit - Tech": {"scoring": "engagement_freshness", "hydrate_details": False},
    "Reddit - Knowledge": {"scoring": "engagement_freshness", "hydrate_details": False},
    "Reddit - News": {"scoring": "engagement_freshness", "hydrate_details": False},
}


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


def load_route_collector(miner_root: Path) -> ModuleType:
    script = miner_root / "scripts" / "collect_routes.py"
    if not script.exists():
        raise FileNotFoundError(f"Cannot find Reddit route collector: {script}")

    scripts_dir = str(script.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    spec = importlib.util.spec_from_file_location("reddit_app_idea_miner_collect_routes", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Reddit route collector: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def dated_json_exports(miner_root: Path, date: str) -> list[Path]:
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
    for path in dated:
        if path not in candidates:
            candidates.append(path)

    return [path for path in candidates if path.is_file() and path.stat().st_size > 2]


def collect_fresh_export(
    miner_root: Path,
    date: str,
    browser: str,
    hydrate_details: bool,
    routes: str | None,
    page_wait: float,
    scrolls: int,
    scroll_delay: float,
    route_delay: float,
    max_detail_posts: int,
    detail_wait: float,
    wait_jitter: float,
    rate_limit_wait: float,
    rate_limit_retries: int,
) -> Path:
    export_path = miner_root / "exports" / f"reddit-route-export-{date}.json"
    command = [
        sys.executable,
        str(miner_root / "scripts" / "collect_routes.py"),
        "--browser",
        browser,
        "--output",
        str(export_path),
        "--page-wait",
        str(page_wait),
        "--scrolls",
        str(scrolls),
        "--scroll-delay",
        str(scroll_delay),
        "--route-delay",
        str(route_delay),
        "--max-detail-posts",
        str(max_detail_posts),
        "--detail-wait",
        str(detail_wait),
        "--wait-jitter",
        str(wait_jitter),
        "--rate-limit-wait",
        str(rate_limit_wait),
        "--rate-limit-retries",
        str(rate_limit_retries),
    ]
    if routes:
        command.extend(["--routes", str((miner_root / routes).resolve() if not Path(routes).is_absolute() else Path(routes))])
    if hydrate_details:
        command.append("--hydrate-details")

    result = subprocess.run(command, cwd=str(miner_root), text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    if not export_path.is_file() or export_path.stat().st_size <= 2:
        raise SystemExit(f"Fresh Reddit browser export was not created or is empty: {export_path}")
    return export_path


def load_browser_export_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("posts"), list):
        return payload
    if isinstance(payload, list):
        return {
            "exportedAt": "",
            "pageUrl": "legacy-browser-export-list",
            "count": len(payload),
            "routes": [],
            "detailHydration": {"enabled": False},
            "posts": payload,
        }
    raise ValueError(f"{path} does not contain a browser export payload")


def detail_cache_key(post: dict[str, Any]) -> str:
    key = clean_text(str(post.get("id") or ""))
    if not key:
        key = clean_text(str(post.get("url") or post.get("permalink") or ""))
    if not key:
        key = clean_text(str(post.get("title") or ""))
    slug = normalize_title(key)
    if slug:
        return slug[:80]
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return digest[:24]


def detail_cache_path(cache_dir: Path, post: dict[str, Any]) -> Path:
    return cache_dir / f"{detail_cache_key(post)}.json"


def apply_cached_detail(post: dict[str, Any], cache_dir: Path) -> bool:
    path = detail_cache_path(cache_dir, post)
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False

    old_selftext = str(post.get("selftext") or "")
    cached_selftext = str(payload.get("selftext") or "")
    if cached_selftext and len(cached_selftext) >= len(old_selftext):
        post["selftext"] = cached_selftext
        post["selftext_source"] = payload.get("selftext_source") or "detail-cache"
        post["selftext_length"] = len(cached_selftext)
    for key in ("id", "title", "subreddit", "permalink", "url"):
        value = payload.get(key)
        if value and not post.get(key):
            post[key] = value
    post["detail_cache_path"] = str(path)
    post["detail_cached_at"] = payload.get("detail_fetched_at") or payload.get("cached_at") or ""
    return bool(cached_selftext)


def write_cached_detail(post: dict[str, Any], cache_dir: Path) -> bool:
    selftext = str(post.get("selftext") or "")
    if not selftext:
        return False
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = detail_cache_path(cache_dir, post)
    payload = {
        "id": post.get("id") or "",
        "title": post.get("title") or "",
        "subreddit": post.get("subreddit") or "",
        "permalink": post.get("permalink") or "",
        "url": post.get("url") or "",
        "selftext": selftext,
        "selftext_source": post.get("selftext_source") or "detail",
        "selftext_length": len(selftext),
        "detail_fetched_at": post.get("detail_fetched_at") or "",
        "cached_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def post_match_keys_from_values(*values: str) -> set[str]:
    keys: set[str] = set()
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        keys.add(text)
        normalized = normalize_title(text)
        if normalized:
            keys.add(f"title:{normalized}")
    return keys


def raw_post_match_keys(post: dict[str, Any]) -> set[str]:
    return post_match_keys_from_values(
        str(post.get("id") or ""),
        str(post.get("url") or ""),
        str(post.get("permalink") or ""),
        str(post.get("title") or ""),
    )


def signal_match_keys(signal: Any) -> set[str]:
    post = signal.post
    return post_match_keys_from_values(
        str(post.id or ""),
        str(post.url or ""),
        str(post.permalink or ""),
        str(post.reddit_url or ""),
        str(post.title or ""),
    )


def hydrate_ranked_export_details(
    export_path: Path,
    signals: list[Any],
    miner_root: Path,
    browser: str,
    max_detail_posts: int,
    detail_wait: float,
    wait_jitter: float,
    rate_limit_wait: float,
    rate_limit_retries: int,
    detail_cache_dir: Path,
) -> bool:
    if max_detail_posts <= 0:
        return False

    payload = load_browser_export_payload(export_path)
    existing_hydration = payload.get("detailHydration")
    if isinstance(existing_hydration, dict) and existing_hydration.get("mode") == "coarse_ranked":
        return False

    posts = [post for post in payload.get("posts", []) if isinstance(post, dict)]
    raw_by_key: dict[str, dict[str, Any]] = {}
    for post in posts:
        for key in raw_post_match_keys(post):
            raw_by_key.setdefault(key, post)

    selected: dict[str, dict[str, Any]] = {}
    cache_hits = 0
    for signal in signals:
        if len(selected) >= max_detail_posts:
            break
        raw_post = None
        for key in signal_match_keys(signal):
            raw_post = raw_by_key.get(key)
            if raw_post is not None:
                break
        if raw_post is None:
            continue
        if apply_cached_detail(raw_post, detail_cache_dir):
            cache_hits += 1
            continue
        selected[str(raw_post.get("id") or raw_post.get("url") or raw_post.get("title"))] = raw_post

    if not selected and cache_hits == 0:
        return False

    if selected:
        collector = load_route_collector(miner_root)
        detail_js_source = collector.DETAIL_EXTRACT_JS.read_text(encoding="utf-8").strip()
        detail_results = collector.hydrate_details(
            browser,
            selected,
            detail_js_source,
            len(selected),
            detail_wait,
            wait_jitter,
            rate_limit_wait,
            rate_limit_retries,
        )
        cache_writes = sum(1 for post in selected.values() if write_cached_detail(post, detail_cache_dir))
    else:
        detail_results = {"enabled": True, "attempted": 0, "hydrated": 0, "with_selftext": 0, "errors": []}
        cache_writes = 0
    if isinstance(detail_results, dict):
        detail_results["mode"] = "coarse_ranked"
        detail_results["coarseSelected"] = len(selected)
        detail_results["cacheHits"] = cache_hits
        detail_results["cacheWrites"] = cache_writes
        detail_results["cacheDir"] = str(detail_cache_dir)
    payload["detailHydration"] = detail_results
    payload["count"] = len(posts)
    export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


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
    return post_output_keys(post)


def post_output_keys(post: Any) -> set[str]:
    keys: set[str] = set()
    url = clean_text(post.reddit_url)
    title_key = normalize_title(post.title)
    if url:
        keys.add(f"url:{url}")
    if title_key:
        keys.add(f"title:{title_key}")
    return keys


def filter_seen_posts(posts: list[Any], seen_keys: set[str]) -> list[Any]:
    if not seen_keys:
        return posts
    return [post for post in posts if not (post_output_keys(post) & seen_keys)]


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


def created_label(created_utc: float) -> str:
    if not created_utc:
        return "created time unavailable"
    created = dt.datetime.fromtimestamp(created_utc, tz=dt.timezone.utc)
    return created.strftime("%Y-%m-%d")


def non_app_rank_score(signal: Any) -> float:
    post = signal.post
    engagement = math.log1p(max(post.score, 0)) * 1.0 + math.log1p(max(post.num_comments, 0)) * 1.4
    freshness = 0.0
    if post.created_utc:
        now = dt.datetime.now(dt.timezone.utc)
        created = dt.datetime.fromtimestamp(post.created_utc, tz=dt.timezone.utc)
        age_days = max((now - created).total_seconds() / 86400, 0.0)
        freshness = max(0.0, 7.0 - age_days) / 7.0
    return round(engagement + freshness, 3)


def format_non_app_summary(signal: Any) -> str:
    post = signal.post
    excerpt = clean_text(post.selftext or post.title, 260)
    engagement = f"{post.score} upvotes、{post.num_comments} comments"
    created = created_label(float(post.created_utc or 0))
    return clean_text(
        f"{excerpt}，{engagement}，created: {created}，rank score: {non_app_rank_score(signal):.2f}。",
        420,
    )


def source_limits(config: dict[str, Any]) -> dict[str, int]:
    raw_limits = config.get("source_limits", {})
    if not isinstance(raw_limits, dict):
        return {}

    limits: dict[str, int] = {}
    for source, raw_limit in raw_limits.items():
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            continue
        limits[str(source)] = max(limit, 0)
    return limits


def resolve_signal_source(signal: Any, config: dict[str, Any], miner: ModuleType) -> str:
    resolver = getattr(miner, "resolve_source_label", None)
    if callable(resolver):
        return str(resolver(signal.post, config))
    return "Reddit"


def display_source_label(source: str) -> str:
    labels = {
        "Reddit - APP": "Reddit - Apps",
    }
    return labels.get(source, source)


def source_flow(config: dict[str, Any], source: str) -> dict[str, Any]:
    flow = dict(DEFAULT_SOURCE_FLOWS.get(source, {"scoring": "opportunity", "hydrate_details": False}))
    raw_flows = config.get("source_flows", {})
    if isinstance(raw_flows, dict) and isinstance(raw_flows.get(source), dict):
        flow.update(raw_flows[source])
    return flow


def source_scoring(config: dict[str, Any], source: str) -> str:
    return str(source_flow(config, source).get("scoring") or "opportunity")


def source_hydrates_details(config: dict[str, Any], source: str) -> bool:
    return bool(source_flow(config, source).get("hydrate_details"))


def source_min_score(config: dict[str, Any], source: str, default_min_score: float) -> float:
    raw_score = source_flow(config, source).get("min_score", default_min_score)
    try:
        return float(raw_score)
    except (TypeError, ValueError):
        return default_min_score


def rank_score(signal: Any, config: dict[str, Any], source: str) -> float:
    if source_scoring(config, source) == "engagement_freshness":
        return non_app_rank_score(signal)
    return float(signal.opportunity_score)


def signal_passes_score_filter(signal: Any, config: dict[str, Any], source: str, default_min_score: float) -> bool:
    if source_scoring(config, source) != "opportunity":
        return True
    return float(signal.opportunity_score) >= source_min_score(config, source, default_min_score)


def signal_needs_detail_hydration(signal: Any, config: dict[str, Any], miner: ModuleType, default_min_score: float) -> bool:
    source = resolve_signal_source(signal, config, miner)
    if not source_hydrates_details(config, source):
        return False
    return signal_passes_score_filter(signal, config, source, default_min_score)


def signal_summary(signal: Any, config: dict[str, Any], source: str) -> str:
    if source_scoring(config, source) == "engagement_freshness":
        return format_non_app_summary(signal)
    return format_summary(signal)


def to_flat_items(
    signals: list[Any],
    seen_keys: set[str],
    config: dict[str, Any],
    miner: ModuleType,
    min_score: float,
    max_items: int = 0,
) -> list[dict[str, str]]:
    limits = source_limits(config)
    counts: dict[str, int] = {}
    items: list[dict[str, str]] = []

    def sort_key(signal: Any) -> tuple[float, float, int, int]:
        source = resolve_signal_source(signal, config, miner)
        return (
            rank_score(signal, config, source),
            float(signal.post.created_utc or 0),
            int(signal.post.score or 0),
            int(signal.post.num_comments or 0),
        )

    for signal in sorted(signals, key=sort_key, reverse=True):
        source = resolve_signal_source(signal, config, miner)
        if not signal_passes_score_filter(signal, config, source, min_score):
            continue

        limit = limits.get(source)
        if limit is not None and counts.get(source, 0) >= limit:
            continue

        keys = signal_keys(signal)
        if keys and keys & seen_keys:
            continue
        seen_keys.update(keys)

        items.append(
            {
                "title": clean_text(signal.post.title),
                "summary": signal_summary(signal, config, source),
                "url": clean_text(signal.post.reddit_url),
                "source": display_source_label(source),
            }
        )
        counts[source] = counts.get(source, 0) + 1

        if max_items > 0 and len(items) >= max_items:
            break
    return items


def collect_and_score(
    miner: ModuleType,
    config: dict[str, Any],
    miner_root: Path,
    browser_exports: list[Path],
    sample: bool,
    quiet: bool,
    seen_keys: set[str] | None = None,
) -> tuple[list[Any], list[str]]:
    miner_args = SimpleNamespace(
        sample=sample,
        browser_export=[str(path) for path in browser_exports] or None,
        quiet=quiet,
    )
    posts, errors = miner.collect_posts(config, miner_args, miner_root)
    posts = miner.dedupe_posts(posts)
    posts = filter_seen_posts(posts, seen_keys or set())
    return miner.analyze_posts(posts), errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate news/reddit/YYYY-MM-DD.json from reddit-app-idea-miner signals."
    )
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Output date, defaults to today")
    parser.add_argument("--miner-root", default=str(DEFAULT_MINER_ROOT), help="Path to reddit-app-idea-miner")
    parser.add_argument("--output-dir", default=str(DEFAULT_REDDIT_DIR), help="Directory for flat Reddit JSON")
    parser.add_argument("--detail-cache-dir", default=str(DEFAULT_DETAIL_CACHE_DIR), help="Directory for cached Reddit post details")
    parser.add_argument("--browser-export", nargs="+", help="Use one or more miner browser-export JSON files")
    parser.add_argument(
        "--no-export-fallback",
        action="store_true",
        help="Do not auto-collect a fresh dated browser export when today's export is missing",
    )
    parser.add_argument("--collect-browser", choices=("safari", "chrome"), default="chrome")
    parser.add_argument(
        "--collector-routes",
        default=DEFAULT_DAILY_ROUTES,
        help="Routes file for fresh browser collection, relative to the miner root unless absolute",
    )
    parser.add_argument("--collector-page-wait", type=float, default=8.0)
    parser.add_argument("--collector-scrolls", type=int, default=2)
    parser.add_argument("--collector-scroll-delay", type=float, default=3.5)
    parser.add_argument("--collector-route-delay", type=float, default=10.0)
    parser.add_argument("--collector-max-detail-posts", type=int, default=80)
    parser.add_argument("--collector-detail-wait", type=float, default=7.0)
    parser.add_argument("--collector-wait-jitter", type=float, default=0.25)
    parser.add_argument("--collector-rate-limit-wait", type=float, default=600.0)
    parser.add_argument("--collector-rate-limit-retries", type=int, default=1)
    parser.add_argument(
        "--no-hydrate-details",
        action="store_true",
        help="Collect route pages without opening post detail pages",
    )
    parser.add_argument("--sample", action="store_true", help="Use miner sample posts; no network")
    parser.add_argument("--max-items", type=int, default=0, help="Maximum flat JSON items to write; 0 disables the global cap")
    parser.add_argument("--min-score", type=float, help="Minimum miner opportunity score")
    parser.add_argument("--quiet", action="store_true", help="Suppress miner progress logs")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    miner_root = Path(args.miner_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    detail_cache_dir = Path(args.detail_cache_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    miner = load_miner(miner_root)
    miner.LOGGER = miner.RunLogger(echo=not args.quiet)
    config = miner.load_config(miner_root / "config" / "miner_config.json")

    browser_exports = [Path(path).expanduser() for path in args.browser_export or []]
    if not args.sample and not browser_exports and not args.no_export_fallback:
        browser_exports = dated_json_exports(miner_root, args.date)[:1]
        if not browser_exports:
            browser_exports = [
                collect_fresh_export(
                    miner_root=miner_root,
                    date=args.date,
                    browser=args.collect_browser,
                    hydrate_details=False,
                    routes=args.collector_routes,
                    page_wait=args.collector_page_wait,
                    scrolls=args.collector_scrolls,
                    scroll_delay=args.collector_scroll_delay,
                    route_delay=args.collector_route_delay,
                    max_detail_posts=args.collector_max_detail_posts,
                    detail_wait=args.collector_detail_wait,
                    wait_jitter=args.collector_wait_jitter,
                    rate_limit_wait=args.collector_rate_limit_wait,
                    rate_limit_retries=args.collector_rate_limit_retries,
                )
            ]

    if not args.sample and not browser_exports:
        export_path = miner_root / "exports" / f"reddit-route-export-{args.date}.json"
        raise SystemExit(
            f"No Reddit browser export found for {args.date}. fetch_reddit.py no longer reuses stale exports; "
            "it must analyze a fresh dated browser export for each day.\n"
            "Collect with a conservative daily browser sweep, then run this script again:\n"
            f"  cd {miner_root}\n"
            f"  python3 scripts/collect_routes.py --browser chrome --routes {DEFAULT_DAILY_ROUTES} --page-wait 8 --scrolls 2 --scroll-delay 3.5 --route-delay 10 --rate-limit-wait 600 --rate-limit-retries 1 --output {export_path}\n"
            f"  python3 {Path(__file__).resolve()}\n"
        )

    min_score = float(args.min_score if args.min_score is not None else config.get("min_score", 4.5))
    seen_keys = load_seen_keys(output_dir, args.date)
    signals, errors = collect_and_score(
        miner=miner,
        config=config,
        miner_root=miner_root,
        browser_exports=browser_exports,
        sample=args.sample,
        quiet=args.quiet,
        seen_keys=seen_keys,
    )

    should_hydrate = (
        not args.sample
        and not args.no_hydrate_details
        and bool(browser_exports)
    )
    if should_hydrate:
        hydrated = hydrate_ranked_export_details(
            export_path=browser_exports[0],
            signals=[
                signal
                for signal in signals
                if signal_needs_detail_hydration(signal, config, miner, min_score)
            ],
            miner_root=miner_root,
            browser=args.collect_browser,
            max_detail_posts=args.collector_max_detail_posts,
            detail_wait=args.collector_detail_wait,
            wait_jitter=args.collector_wait_jitter,
            rate_limit_wait=args.collector_rate_limit_wait,
            rate_limit_retries=args.collector_rate_limit_retries,
            detail_cache_dir=detail_cache_dir,
        )
        if hydrated:
            signals, final_errors = collect_and_score(
                miner=miner,
                config=config,
                miner_root=miner_root,
                browser_exports=browser_exports,
                sample=args.sample,
                quiet=args.quiet,
                seen_keys=seen_keys,
            )
            errors = [*errors, *final_errors]

    items = to_flat_items(
        signals=signals,
        seen_keys=seen_keys,
        config=config,
        miner=miner,
        min_score=min_score,
        max_items=args.max_items,
    )
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
