#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SOURCES_DIR = ROOT / "sources"


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    reason: str
    path: str


def expand_path(template: str, date: str, root: Path = ROOT) -> Path:
    rendered = template.format(date=date, root=str(root), home=str(Path.home()))
    return Path(rendered).expanduser()


def load_source_configs(sources: list[str] | None = None, root: Path = ROOT) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    selected = set(sources or [])
    for path in sorted((root / "sources").glob("*.json")):
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
        config["_config_path"] = str(path)
        if selected and config.get("name") not in selected:
            continue
        configs.append(config)
    return sorted(configs, key=lambda config: (int(config.get("order", 100)), config.get("name", "")))


def check_artifact(spec: dict[str, Any], date: str, root: Path = ROOT) -> CheckResult:
    path = expand_path(spec["path"], date, root)
    display = str(path)
    if not path.exists():
        return CheckResult(False, "missing", display)
    if not path.is_file():
        return CheckResult(False, "not a file", display)

    min_bytes = int(spec.get("min_bytes", 1))
    size = path.stat().st_size
    if size < min_bytes:
        return CheckResult(False, f"too small ({size} bytes)", display)

    kind = spec.get("type", "file")
    if kind == "json_array":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            return CheckResult(False, f"invalid json: {error}", display)
        if not isinstance(payload, list):
            return CheckResult(False, "json root is not an array", display)
        min_items = spec.get("min_items")
        if min_items is not None and len(payload) < int(min_items):
            return CheckResult(False, f"too few items ({len(payload)})", display)
        allowed_keys = spec.get("allowed_keys")
        if allowed_keys is not None:
            allowed = set(allowed_keys)
            for index, item in enumerate(payload):
                if not isinstance(item, dict):
                    return CheckResult(False, f"item {index} is not an object", display)
                keys = set(item.keys())
                if keys != allowed:
                    return CheckResult(False, f"item {index} keys {sorted(keys)} != {sorted(allowed)}", display)

    return CheckResult(True, "ok", display)


def check_source(config: dict[str, Any], date: str, root: Path = ROOT) -> dict[str, Any]:
    artifacts = [*config.get("outputs", []), *config.get("freshness", [])]
    checks = [check_artifact(spec, date, root) for spec in artifacts]
    complete = all(check.ok for check in checks)
    return {
        "name": config["name"],
        "complete": complete,
        "checks": [check.__dict__ for check in checks],
    }


def format_command(command: list[str], date: str, root: Path = ROOT) -> list[str]:
    return [part.format(date=date, root=str(root), home=str(Path.home())) for part in command]


def run_command(command: list[str], date: str, root: Path = ROOT) -> int:
    formatted = format_command(command, date, root)
    result = subprocess.run(formatted, cwd=str(root), text=True, check=False)
    return result.returncode


def should_skip_step(step: dict[str, Any], date: str, root: Path = ROOT) -> bool:
    for spec in step.get("skip_if", []):
        if not check_artifact(spec, date, root).ok:
            return False
    return bool(step.get("skip_if"))


def render_prompt(config: dict[str, Any], step: dict[str, Any], date: str, root: Path = ROOT) -> str:
    prompt = step.get("prompt", "")
    return prompt.format(date=date, root=str(root), home=str(Path.home()), source=config["name"])


def status_payload(sources: list[dict[str, Any]], date: str, root: Path = ROOT) -> dict[str, Any]:
    statuses = [check_source(config, date, root) for config in sources]
    return {
        "date": date,
        "complete": all(status["complete"] for status in statuses),
        "sources": statuses,
    }


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def source_by_name(name: str, root: Path = ROOT) -> dict[str, Any]:
    matches = load_source_configs([name], root)
    if not matches:
        raise SystemExit(f"Unknown source: {name}")
    return matches[0]


def default_date() -> str:
    import datetime as dt

    return dt.date.today().isoformat()


def main_import_guard() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
