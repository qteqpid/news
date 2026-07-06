#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daily_lib import check_source, default_date, load_source_configs, print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate daily pipeline outputs.")
    parser.add_argument("--date", default=default_date())
    parser.add_argument("--source", action="append")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    statuses = [check_source(source, args.date) for source in load_source_configs(args.source)]
    if args.json:
        print_json(statuses)
    else:
        for status in statuses:
            print(f"{status['name']}: {'valid' if status['complete'] else 'invalid'}")
            for check in status["checks"]:
                if not check["ok"]:
                    print(f"  - {check['path']}: {check['reason']}")
    return 0 if all(status["complete"] for status in statuses) else 1


if __name__ == "__main__":
    raise SystemExit(main())
