#!/usr/bin/env python3
"""Run the self-contained checks intended for an artifact reviewer.

The entry point writes durable logs and a machine-readable receipt even when a
step fails or times out. Child processes run in their own process group so a
timeout cannot leave descendants alive or keep a capture pipe open.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_step(*, name: str, command: list[str], cwd: Path, output: Path, timeout: int) -> dict[str, Any]:
    """Run one step with file-backed logs and process-group cleanup."""
    logs = output / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path = logs / f"{name}.stdout.txt"
    stderr_path = logs / f"{name}.stderr.txt"
    started = time.monotonic()
    timed_out = False
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            returncode = 124
    return {
        "name": name,
        "command": command,
        "cwd": str(cwd),
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_seconds": timeout,
        "seconds": time.monotonic() - started,
        "stdout": str(stdout_path.relative_to(output)),
        "stderr": str(stderr_path.relative_to(output)),
        "ok": returncode == 0 and not timed_out,
    }


def prepare_output(requested: Path | None) -> Path:
    """Create a fresh evidence directory and reject accidental reuse."""
    if requested is None:
        return Path(tempfile.mkdtemp(prefix="authrefine-review-")).resolve()
    output = requested.resolve()
    output.mkdir(parents=True, exist_ok=False)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--scope",
        choices=("core", "extended"),
        default="core",
        help="core runs the contribution-critical profile; extended also runs the portable matrix, campaign, depth audit, and reference audit",
    )
    parser.add_argument("--timeout", type=int, default=3600, help="maximum seconds for each top-level review step")
    parser.add_argument("--step-timeout", type=int, default=600, help="maximum seconds for each subprocess launched by evaluate.py")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent
    try:
        output = prepare_output(args.output)
    except FileExistsError:
        raise SystemExit("choose a fresh output directory; review evidence is never overwritten")

    receipt: dict[str, Any] = {
        "schema": "authrefine-review-v2",
        "scope": args.scope,
        "started_utc": utc_now(),
        "artifact": str(root),
        "steps": [],
        "status": "RUNNING",
    }

    steps: list[tuple[str, list[str], Path]] = [
        (
            "core",
            [
                sys.executable,
                "-B",
                "evaluate.py",
                "--profile",
                "core",
                "--output",
                str(output / "core"),
                "--step-timeout",
                str(args.step_timeout),
                "--full-timeout",
                str(args.timeout),
            ],
            root,
        )
    ]
    if args.scope == "extended":
        steps.extend(
            [
                (
                    "portable",
                    [
                        sys.executable,
                        "-B",
                        "evaluate.py",
                        "--profile",
                        "portable",
                        "--output",
                        str(output / "portable"),
                        "--step-timeout",
                        str(args.step_timeout),
                        "--full-timeout",
                        str(args.timeout),
                    ],
                    root,
                ),
                ("campaign", [sys.executable, "-B", "run_campaign.py", "--output", str(output / "campaign")], root),
                ("research-depth", [sys.executable, "-B", "verify_research_depth.py", "--output", str(output / "research-depth.json")], root),
                ("references", [sys.executable, "-B", "verify.py"], root / "references"),
            ]
        )

    for name, command, cwd in steps:
        row = run_step(name=name, command=command, cwd=cwd, output=output, timeout=args.timeout)
        receipt["steps"].append(row)
        if not row["ok"]:
            break

    passed = len(receipt["steps"]) == len(steps) and all(row["ok"] for row in receipt["steps"])
    receipt["status"] = "PASS" if passed else "FAIL"
    receipt["pass"] = passed
    receipt["finished_utc"] = utc_now()
    receipt["exit_code"] = 0 if passed else 1
    write_json(output / "review.json", receipt)
    print(json.dumps({"scope": args.scope, "status": receipt["status"], "receipt": str(output / "review.json")}, sort_keys=True))
    return receipt["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
