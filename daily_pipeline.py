#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from daily_lib import (
    ROOT,
    check_source,
    default_date,
    load_source_configs,
    print_json,
    render_prompt,
    run_command,
    should_skip_step,
    status_payload,
)


MODEL_STEP_EXIT = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the independent daily news/app/reddit pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("status", "run", "hook-context", "list-sources"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--date", default=default_date())
        subparser.add_argument("--source", action="append", help="Limit to one source; can be repeated")
        subparser.add_argument("--json", action="store_true")
        subparser.add_argument("--force", action="store_true", help="Run steps even when source outputs are complete")

    return parser.parse_args()


def cmd_list_sources(args: argparse.Namespace) -> int:
    sources = load_source_configs(args.source)
    names = [source["name"] for source in sources]
    if args.json:
        print_json(names)
    else:
        for name in names:
            print(name)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    sources = load_source_configs(args.source)
    payload = status_payload(sources, args.date)
    if args.json:
        print_json(payload)
    else:
        for source in payload["sources"]:
            state = "complete" if source["complete"] else "incomplete"
            print(f"{source['name']}: {state}")
            for check in source["checks"]:
                if not check["ok"]:
                    print(f"  - {check['path']}: {check['reason']}")
    return 0 if payload["complete"] else 1


def cmd_hook_context(args: argparse.Namespace) -> int:
    sources = load_source_configs(args.source)
    payload = status_payload(sources, args.date)
    if payload["complete"]:
        return 0

    missing = []
    for source in payload["sources"]:
        if source["complete"]:
            continue
        bad = [check["path"] for check in source["checks"] if not check["ok"]]
        missing.append(f"{source['name']} ({', '.join(bad)})")

    message = (
        f"Daily report pipeline for {args.date} is incomplete: "
        + "; ".join(missing)
        + ". Before handling the user's next request, run `python3 ~/my_repos/news/daily_pipeline.py run`. "
        + "The pipeline owns source checks, fetch steps, validation, and skip behavior. "
        + "If it prints MODEL_STEP, follow the emitted prompt exactly, then rerun the same pipeline command. "
        + "Do not commit or push because scheduled sync handles publication."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": message,
                }
            },
            ensure_ascii=False,
        )
    )
    return 0


def run_source(config: dict, date: str, force: bool) -> tuple[bool, bool]:
    status = check_source(config, date)
    if status["complete"] and not force:
        print(f"SKIP:{config['name']}:complete")
        return True, False

    for step in config.get("steps", []):
        if should_skip_step(step, date):
            print(f"SKIP:{config['name']}:{step['name']}")
            continue

        step_type = step.get("type", "command")
        if step_type == "command":
            print(f"RUN:{config['name']}:{step['name']}")
            code = run_command(step["command"], date)
            if code != 0:
                print(f"FAIL:{config['name']}:{step['name']}:{code}")
                return False, False
            continue

        if step_type == "model_prompt":
            print(f"MODEL_STEP:{config['name']}:{step['name']}")
            print(render_prompt(config, step, date))
            return False, True

        print(f"FAIL:{config['name']}:{step['name']}:unknown step type {step_type}")
        return False, False

    final_status = check_source(config, date)
    if final_status["complete"]:
        print(f"DONE:{config['name']}")
        return True, False

    print(f"INCOMPLETE:{config['name']}")
    for check in final_status["checks"]:
        if not check["ok"]:
            print(f"  - {check['path']}: {check['reason']}")
    return False, False


def cmd_run(args: argparse.Namespace) -> int:
    sources = load_source_configs(args.source)
    saw_model_step = False
    ok = True
    for config in sources:
        source_ok, needs_model = run_source(config, args.date, args.force)
        ok = ok and source_ok
        saw_model_step = saw_model_step or needs_model
        if needs_model:
            break
    if saw_model_step:
        return MODEL_STEP_EXIT
    return 0 if ok else 1


def main() -> int:
    args = parse_args()
    if args.command == "list-sources":
        return cmd_list_sources(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "hook-context":
        return cmd_hook_context(args)
    if args.command == "run":
        return cmd_run(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
