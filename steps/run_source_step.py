#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daily_lib import default_date, render_prompt, run_command, should_skip_step, source_by_name


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one configured source step.")
    parser.add_argument("source")
    parser.add_argument("step")
    parser.add_argument("--date", default=default_date())
    args = parser.parse_args()

    source = source_by_name(args.source)
    matches = [step for step in source.get("steps", []) if step.get("name") == args.step]
    if not matches:
        raise SystemExit(f"Unknown step for {args.source}: {args.step}")
    step = matches[0]

    if should_skip_step(step, args.date):
        print(f"SKIP:{args.source}:{args.step}")
        return 0

    if step.get("type", "command") == "command":
        return run_command(step["command"], args.date)
    if step.get("type") == "model_prompt":
        print(render_prompt(source, step, args.date))
        return 2
    raise SystemExit(f"Unknown step type: {step.get('type')}")


if __name__ == "__main__":
    raise SystemExit(main())
