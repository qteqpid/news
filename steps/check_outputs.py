#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daily_lib import default_date, load_source_configs, print_json, status_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Check daily pipeline source outputs.")
    parser.add_argument("--date", default=default_date())
    parser.add_argument("--source", action="append")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = status_payload(load_source_configs(args.source), args.date)
    if args.json:
        print_json(payload)
    else:
        for source in payload["sources"]:
            print(f"{source['name']}: {'complete' if source['complete'] else 'incomplete'}")
    return 0 if payload["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
