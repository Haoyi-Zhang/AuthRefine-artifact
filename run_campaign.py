#!/usr/bin/env python3
"""Recompute the self-contained scientific campaign into a fresh directory.

This entry deliberately excludes optional framework/native tests.  It rebuilds
all finite-model scientific records used by the main campaign and asks the
existing summarizer to compare their scientific fields with the retained
baseline.  Integration environments remain separate evaluation profiles.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def run(command: list[str], *, output: Path, name: str, timeout: int, env: dict[str, str]) -> dict:
    logs = output / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path = logs / f"{name}.stdout.txt"
    stderr_path = logs / f"{name}.stderr.txt"
    started = time.monotonic()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            completed = subprocess.run(
                command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                timeout=timeout, check=False,
            )
            returncode = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            returncode = 124
            timed_out = True
    return {
        "name": name,
        "command": command,
        "returncode": returncode,
        "timed_out": timed_out,
        "seconds": time.monotonic() - started,
        "stdout": str(stdout_path.relative_to(output)),
        "stderr": str(stderr_path.relative_to(output)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=ROOT / "results")
    parser.add_argument("--step-timeout", type=int, default=300)
    args = parser.parse_args()
    output = args.output.resolve()
    baseline = args.baseline.resolve()
    if output.exists():
        parser.error("output must be a fresh path")
    if args.step_timeout <= 0:
        parser.error("step timeout must be positive")
    output.mkdir(parents=True)
    env = dict(os.environ)
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "TZ": "UTC",
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
    })
    started = datetime.now(timezone.utc).isoformat()
    steps: list[dict] = []

    commands = [
        ("reference", [sys.executable, "-B", "src/reference_check.py", "--output", str(output / "reference_verification.json")]),
        ("pilot", [sys.executable, "-B", "src/experiments.py", "pilot", "--output", str(output / "pilot")]),
        ("theory", [sys.executable, "-B", "src/theory_checks.py", "--output", str(output / "theory.json")]),
        ("extensions", [sys.executable, "-B", "src/extension_checks.py", "--output", str(output / "extensions.json")]),
        ("adversarial", [sys.executable, "-B", "src/adversarial_checks.py", "--output", str(output / "adversarial.json")]),
        ("exhaustive", [sys.executable, "-B", "src/exhaustive_audit.py", "--output", str(output / "exhaustive.json")]),
    ]
    for start in range(0, 10000, 2500):
        commands.append((
            f"sequence-{start:05d}",
            [sys.executable, "-B", "src/experiments.py", "sequence", "--start", str(start), "--chunks", "10", "--output", str(output)],
        ))

    for name, command in commands:
        step = run(command, output=output, name=name, timeout=args.step_timeout, env=env)
        steps.append(step)
        if step["returncode"] != 0:
            receipt = {
                "schema": 1, "status": "FAIL", "started_utc": started,
                "finished_utc": datetime.now(timezone.utc).isoformat(),
                "baseline": "results", "steps": steps,
                "reason": f"{name} returned {step['returncode']}",
            }
            (output / "campaign.json").write_text(json.dumps(receipt, indent=2) + "\n")
            return 1

    summary_step = run(
        [sys.executable, "-B", "src/summarize.py", str(output), "--baseline", str(baseline)],
        output=output, name="summarize", timeout=args.step_timeout, env=env,
    )
    steps.append(summary_step)
    if summary_step["returncode"] == 0:
        summary = json.loads((output / summary_step["stdout"]).read_text())
    else:
        summary = None
    scientific_match = bool(summary and summary.get("all_internal_comparisons_agree"))
    # The summarizer emits a baseline comparison map when --baseline is used.
    comparison = (summary or {}).get("baseline_comparison", {})
    if comparison:
        scientific_match = scientific_match and all(comparison.values())
    status = "PASS" if summary_step["returncode"] == 0 and scientific_match else "FAIL"
    receipt = {
        "schema": 1,
        "status": status,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "baseline": "results",
        "scope": "Self-contained finite-model campaign; optional framework, native, timing, and proof profiles are separate.",
        "steps": steps,
        "summary": summary,
    }
    (output / "campaign.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({
        "status": status,
        "primary_cases": (summary or {}).get("primary_cases"),
        "counted_obligations": (summary or {}).get("counted_obligations"),
        "scientific_match": scientific_match,
    }, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
