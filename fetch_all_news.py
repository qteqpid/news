#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from daily_lib import ROOT, default_date, expand_path, load_source_configs


DEFAULT_OUTPUT_DIR = ROOT / "all_news"


def json_array_outputs(source: dict[str, Any]) -> list[dict[str, Any]]:
    return [spec for spec in source.get("outputs", []) if spec.get("type") == "json_array"]


def load_items(path: Path) -> list[Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"JSON root is not an array: {path}")
    return payload


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def normalize_item(item: Any, source_name: str) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None

    title = clean_text(item.get("title"))
    summary = clean_text(item.get("summary"))
    url = clean_text(item.get("url") or item.get("link"))
    source = clean_text(item.get("source") or source_name.upper())

    if not title and not summary:
        return None

    return {
        "title": title,
        "summary": summary,
        "url": url,
        "source": source,
    }


def build_all_news(date: str) -> list[Any]:
    merged: list[Any] = []
    for source in load_source_configs():
        source_name = source["name"]
        if source_name == "all_news" or source.get("aggregate") is False:
            continue

        for spec in json_array_outputs(source):
            path = expand_path(spec["path"], date)
            if not path.is_file():
                raise FileNotFoundError(f"Missing source JSON for {source_name}: {path}")
            for item in load_items(path):
                normalized = normalize_item(item, source_name)
                if normalized is not None:
                    merged.append(normalized)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Flatten daily source JSON arrays into all_news/YYYY-MM-DD.json.")
    parser.add_argument("--date", default=default_date())
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    items = build_all_news(args.date)
    if not items:
        raise SystemExit("No source JSON items were found to aggregate.")

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{args.date}.json"
    output_path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"DONE:{args.date}:{len(items)}:{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
