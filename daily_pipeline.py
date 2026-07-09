#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import socket
import sys
from pathlib import Path
from typing import Any

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
BUSY_EXIT = 3
RUN_MARKER_DIR = ROOT / ".runtime"
RUN_MARKER_PATH = RUN_MARKER_DIR / "daily_pipeline_run.json"
RUN_LOG_PATH = ROOT / "news_log.txt"
MODEL_STEP_STALE_SECONDS = 8 * 60 * 60


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def parse_timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def process_is_alive(pid: object) -> bool:
    try:
        parsed_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if parsed_pid <= 0:
        return False
    try:
        os.kill(parsed_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def marker_age_seconds(marker: dict[str, Any]) -> float | None:
    timestamp = parse_timestamp(marker.get("updated_at") or marker.get("started_at"))
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - timestamp).total_seconds()


def read_run_marker() -> dict[str, Any] | None:
    try:
        return json.loads(RUN_MARKER_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None


def write_run_marker(marker: dict[str, Any], *, create: bool = False) -> bool:
    RUN_MARKER_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(marker, ensure_ascii=False, indent=2) + "\n"
    if create:
        try:
            fd = os.open(RUN_MARKER_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(payload)
        return True

    temp_path = RUN_MARKER_PATH.with_suffix(".tmp")
    temp_path.write_text(payload, encoding="utf-8")
    temp_path.replace(RUN_MARKER_PATH)
    return True


def clear_run_marker() -> None:
    try:
        RUN_MARKER_PATH.unlink()
    except FileNotFoundError:
        pass


def is_active_marker(marker: dict[str, Any]) -> bool:
    state = marker.get("state")
    if state == "running":
        return process_is_alive(marker.get("pid"))
    if state == "waiting_for_model_step":
        age = marker_age_seconds(marker)
        return age is None or age < MODEL_STEP_STALE_SECONDS
    return False


def current_active_marker() -> dict[str, Any] | None:
    marker = read_run_marker()
    if marker is None:
        return None
    if is_active_marker(marker):
        return marker
    append_run_log("pipeline-marker-stale", marker)
    clear_run_marker()
    return None


def source_names(args: argparse.Namespace) -> list[str]:
    return list(args.source or ["*"])


def new_run_marker(args: argparse.Namespace, state: str) -> dict[str, Any]:
    now = utc_now()
    return {
        "state": state,
        "date": args.date,
        "sources": source_names(args),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "started_at": now,
        "updated_at": now,
    }


def format_marker(marker: dict[str, Any]) -> str:
    sources = ",".join(str(source) for source in marker.get("sources") or ["*"])
    return (
        f"date={marker.get('date', '?')} sources={sources} "
        f"state={marker.get('state', '?')} pid={marker.get('pid', '?')} "
        f"updated_at={marker.get('updated_at', marker.get('started_at', '?'))}"
    )


def append_run_log(event: str, marker: dict[str, Any]) -> None:
    date = marker.get("date") or dt.date.today().isoformat()
    try:
        with RUN_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(f"{date} {event} {format_marker(marker)}\n")
    except OSError:
        pass


def acquire_run_marker(args: argparse.Namespace) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    existing = current_active_marker()
    if existing and existing.get("state") == "running" and not args.force:
        return None, existing

    marker = new_run_marker(args, "running")
    if existing and existing.get("state") == "waiting_for_model_step":
        write_run_marker(marker)
        append_run_log("pipeline-resume-after-model-step", marker)
        return marker, None

    if write_run_marker(marker, create=True):
        append_run_log("pipeline-start", marker)
        return marker, None

    existing = current_active_marker()
    if existing and existing.get("state") == "running" and not args.force:
        return None, existing
    write_run_marker(marker)
    append_run_log("pipeline-start", marker)
    return marker, None


def mark_waiting_for_model_step(marker: dict[str, Any], source: str, step: str) -> None:
    marker.update(
        {
            "state": "waiting_for_model_step",
            "model_source": source,
            "model_step": step,
            "updated_at": utc_now(),
        }
    )
    write_run_marker(marker)
    append_run_log("pipeline-waiting-for-model-step", marker)



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
    active_marker = current_active_marker()
    if active_marker:
        payload["active_run"] = active_marker
    if args.json:
        print_json(payload)
    else:
        if active_marker:
            print(f"active-run: {format_marker(active_marker)}")
        for source in payload["sources"]:
            state = "complete" if source["complete"] else "incomplete"
            print(f"{source['name']}: {state}")
            for check in source["checks"]:
                if not check["ok"]:
                    print(f"  - {check['path']}: {check['reason']}")
    return 0 if payload["complete"] else 1


def cmd_hook_context(args: argparse.Namespace) -> int:
    active_marker = current_active_marker()
    if active_marker:
        state = active_marker.get("state")
        if state == "waiting_for_model_step":
            state_text = "waiting for the model organization step to finish"
        else:
            state_text = "already running"
        message = (
            f"Daily report pipeline is {state_text}: {format_marker(active_marker)}. "
            f"Do not start another fetch in this session. Wait for the active run to finish, or inspect "
            f"`{RUN_MARKER_PATH}` if you need to verify whether the marker is stale."
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

    source_args = "".join(f" --source {shlex.quote(source)}" for source in args.source or [])
    run_command_text = f"python3 ~/my_repos/news/daily_pipeline.py run --date {shlex.quote(args.date)}{source_args}"
    message = (
        f"Daily report pipeline for {args.date} is incomplete: "
        + "; ".join(missing)
        + f". Before handling the user's next request, run `{run_command_text}`. "
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


def run_source(config: dict, date: str, force: bool) -> tuple[bool, bool, tuple[str, str] | None]:
    status = check_source(config, date)
    if status["complete"] and not force:
        print(f"SKIP:{config['name']}:complete")
        return True, False, None

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
                return False, False, None
            continue

        if step_type == "model_prompt":
            print(f"MODEL_STEP:{config['name']}:{step['name']}")
            print(render_prompt(config, step, date))
            return False, True, (config["name"], step["name"])

        print(f"FAIL:{config['name']}:{step['name']}:unknown step type {step_type}")
        return False, False, None

    final_status = check_source(config, date)
    if final_status["complete"]:
        print(f"DONE:{config['name']}")
        return True, False, None

    print(f"INCOMPLETE:{config['name']}")
    for check in final_status["checks"]:
        if not check["ok"]:
            print(f"  - {check['path']}: {check['reason']}")
    return False, False, None


def cmd_run(args: argparse.Namespace) -> int:
    marker, busy_marker = acquire_run_marker(args)
    if busy_marker:
        print(f"BUSY:daily_pipeline:{format_marker(busy_marker)}")
        return BUSY_EXIT
    if marker is None:
        print("BUSY:daily_pipeline:unknown")
        return BUSY_EXIT

    saw_model_step = False
    ok = True
    exit_code = 1
    try:
        sources = load_source_configs(args.source)
        for config in sources:
            source_ok, needs_model, model_step = run_source(config, args.date, args.force)
            ok = ok and source_ok
            saw_model_step = saw_model_step or needs_model
            if needs_model:
                if model_step:
                    mark_waiting_for_model_step(marker, model_step[0], model_step[1])
                break
        if saw_model_step:
            exit_code = MODEL_STEP_EXIT
            return exit_code
        exit_code = 0 if ok else 1
        return exit_code
    finally:
        if not saw_model_step:
            marker["state"] = "finished" if exit_code == 0 else "failed"
            marker["exit_code"] = exit_code
            marker["updated_at"] = utc_now()
            append_run_log("pipeline-finish", marker)
            clear_run_marker()


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
