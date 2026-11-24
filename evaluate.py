#!/usr/bin/env python3
"""Run AuthRefine's review-facing core, portable, or full artifact profile.

The output directory must not exist.  Each subprocess receives separate
file-backed stdout/stderr logs, a timeout, and its own process group.  This
prevents descendants from holding a capture pipe open and makes every reported
status traceable to a concrete command and log file.

Exit status:
  0  selected profile passed
  1  a mandatory executed check failed
  2  the full profile is unavailable because its exact environment is absent
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

from test_profiles import (
    CORE_EVIDENCE,
    CORE_MODES,
    CORE_TEST_MODULES,
    PORTABLE_TEST_MODULES,
    FRAMEWORK_REQUIREMENTS,
    FRAMEWORK_TEST_MODULES,
    FULL_REQUIREMENTS,
    QUERY_REQUIREMENTS,
    QUERY_TEST_MODULES,
    FULL_TOOLS,
)

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
TEST_RE = re.compile(r"Ran\s+(\d+)\s+tests?\s+in")
SKIP_RE = re.compile(r"skipped=(\d+)")
EXPECTED_FIGURES = {
    "authrefine-overview.pdf", "session-lifecycle.pdf", "credential-handoff.pdf",
    "semantic-square.pdf", "diagnostic-trace.pdf", "analysis-workflow.pdf",
    "family-diagnosis-cost.pdf", "source-interface-coverage.pdf",
    "evaluation-design.pdf", "source-screening.pdf", "adaptation-handling.pdf",
    "frontend-batch-cost.pdf", "credential-algorithm-cost.pdf", "width.pdf",
    "session-correspondence.pdf", "symbolic-comparison.pdf",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "step"


def run_command(
    *,
    name: str,
    command: list[str],
    output: Path,
    timeout: int,
    env: dict[str, str],
    cwd: Path = ROOT,
) -> dict[str, Any]:
    """Execute one command with durable logs and process-group timeout."""
    logs = output / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    slug = safe_name(name)
    print(f"[evaluate] start {name}", file=sys.stderr, flush=True)
    stdout_path = logs / f"{slug}.stdout.txt"
    stderr_path = logs / f"{slug}.stderr.txt"
    started = time.monotonic()
    timed_out = False
    returncode: int
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
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
    print(f"[evaluate] end {name}: rc={returncode} seconds={time.monotonic() - started:.3f}", file=sys.stderr, flush=True)
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
        "stdout_sha256": sha256(stdout_path),
        "stderr_sha256": sha256(stderr_path),
    }


def parse_unittest(step: dict[str, Any], output: Path) -> dict[str, Any]:
    text = "\n".join(
        (output / step[key]).read_text(encoding="utf-8", errors="replace")
        for key in ("stdout", "stderr")
    )
    matches = TEST_RE.findall(text)
    tests = int(matches[-1]) if matches else None
    skips = int(SKIP_RE.findall(text)[-1]) if SKIP_RE.findall(text) else 0
    ok = step["returncode"] == 0 and tests is not None and "OK" in text
    return {
        **step,
        "tests": tests,
        "explicit_skips": skips,
        "passed_tests": tests - skips if ok and tests is not None else None,
        "parsed_ok": ok,
    }


def core_environment() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "TZ": "UTC",
            "PYTHONPATH": os.pathsep.join(
                (str(ROOT / "tests"), str(ROOT / "src"), str(ROOT))
            ),
        }
    )
    return env


def run_tests(output: Path, timeout: int, modules: tuple[str, ...]) -> dict[str, Any]:
    modes: list[dict[str, Any]] = []
    env_base = core_environment()
    for mode in CORE_MODES:
        module_rows: list[dict[str, Any]] = []
        for module in modules:
            command = [
                sys.executable,
                "-B",
                *mode["python_flags"],
                "-m",
                "unittest",
                module,
            ]
            env = dict(env_base)
            if mode["name"] == "strict":
                env["PYTHONWARNINGS"] = "error"
            step = run_command(
                name=f"tests-{mode['name']}-{module}",
                command=command,
                output=output,
                timeout=timeout,
                env=env,
            )
            module_rows.append(parse_unittest(step, output))
        totals = {
            "tests": sum(row["tests"] or 0 for row in module_rows),
            "passed_tests": sum(row["passed_tests"] or 0 for row in module_rows),
            "explicit_skips": sum(row["explicit_skips"] for row in module_rows),
        }
        modes.append(
            {
                "name": mode["name"],
                "python_flags": list(mode["python_flags"]),
                "ok": all(row["parsed_ok"] for row in module_rows),
                **totals,
                "modules": module_rows,
            }
        )
    return {
        "ok": all(mode["ok"] for mode in modes),
        "isolation": "one interpreter per unittest module",
        "modes": modes,
    }


def run_evidence(output: Path, timeout: int) -> dict[str, Any]:
    env = core_environment()
    rows: list[dict[str, Any]] = []
    evidence_dir = output / "evidence"
    evidence_dir.mkdir()
    for spec in CORE_EVIDENCE:
        command = [sys.executable, "-B", *spec["arguments"]]
        if "output_argument" in spec:
            receipt = evidence_dir / spec["output_file"]
            command.extend((spec["output_argument"], str(receipt)))
        step = run_command(
            name=f"evidence-{spec['name']}",
            command=command,
            output=output,
            timeout=timeout,
            env=env,
        )
        rows.append(
            {
                **step,
                "description": spec["description"],
                "ok": step["returncode"] == 0,
            }
        )
    return {"ok": all(row["ok"] for row in rows), "checks": rows}


def validate_example(path: Path) -> dict[str, Any]:
    values = {name: json.loads((path / f"{name}.json").read_text()) for name in ("indexed", "scan", "caller")}
    expected_identity = {
        "credential-for-row-a": "credential-a",
        "credential-for-row-b": "credential-b",
    }
    expected_swap = {
        "credential-for-row-a": "credential-b",
        "credential-for-row-b": "credential-a",
    }
    expected_word = [
        ["client", "row-a", "remove"],
        ["client", "credential-a", "lookup"],
    ]
    observations: dict[str, Any] = {}
    for name, value in values.items():
        profiles = value["profiles"]
        matching = [row for row in profiles if row["equivalent"]]
        failing = [row for row in profiles if not row["equivalent"]]
        word = [step["request"] for step in failing[0]["trace"]] if len(failing) == 1 else None
        ok = (
            value["bindings"] == 2
            and value["matching_bindings"] == 1
            and value["failing_bindings"] == 1
            and value["shortest_failure"] == 2
            and len(matching) == 1
            and len(failing) == 1
            and matching[0]["binding"] == expected_identity
            and failing[0]["binding"] == expected_swap
            and word == expected_word
            and failing[0]["trace"][-1]["compared_equal"] is False
        )
        observations[name] = {"ok": ok, "word": word, "matching": matching[0]["binding"] if matching else None}
    # Compare the complete diagnostic semantics while deliberately excluding
    # engine/protocol bookkeeping.  Protocol-indexed replay rows add state IDs
    # that are not part of the public diagnostic certificate; retaining them in
    # this comparison would reject semantically identical outputs.
    trace_fields = (
        "request", "binding", "source", "target",
        "decision_equal", "state_equal", "compared_equal",
    )
    profile_fields = (
        "binding", "equivalent", "length", "indices",
        "target_state", "request",
    )

    def canonical_profile(row: dict[str, Any]) -> dict[str, Any]:
        result = {field: row.get(field) for field in profile_fields}
        trace = row.get("trace")
        result["trace"] = (
            None
            if trace is None
            else [{field: step.get(field) for field in trace_fields} for step in trace]
        )
        return result

    def canonical(value: dict[str, Any]) -> dict[str, Any]:
        return {
            "classification": value["classification"],
            "bindings": value["bindings"],
            "matching_bindings": value["matching_bindings"],
            "failing_bindings": value["failing_bindings"],
            "shortest_failure": value["shortest_failure"],
            "strata": value["strata"],
            "profiles": [canonical_profile(row) for row in value["profiles"]],
        }

    semantic_equal = canonical(values["indexed"]) == canonical(values["scan"]) == canonical(values["caller"])
    return {
        "ok": all(row["ok"] for row in observations.values()) and semantic_equal,
        "engines": observations,
        "semantic_profiles_equal": semantic_equal,
        "shortest_counterexample": expected_word,
    }


def run_example(output: Path, timeout: int) -> dict[str, Any]:
    env = core_environment()
    base = output / "motivating-example"
    inputs = base / "inputs"
    base.mkdir()
    commands = (
        (
            "example-export",
            [sys.executable, "-B", "source_study/stateful_sequence/export_profile_inputs.py", "--output", str(inputs)],
        ),
        (
            "example-indexed",
            [sys.executable, "-B", "src/profile.py", str(inputs / "policy.json"), str(inputs / "machine.json"), str(base / "indexed.json"), "--family", str(inputs / "family.json")],
        ),
        (
            "example-scan",
            [sys.executable, "-B", "src/profile.py", str(inputs / "policy.json"), str(inputs / "machine.json"), str(base / "scan.json"), "--family", str(inputs / "family.json"), "--engine", "scan"],
        ),
        (
            "example-caller",
            [sys.executable, "-B", "src/profile.py", str(inputs / "policy.json"), str(inputs / "machine.json"), str(base / "caller.json"), "--family", str(inputs / "family.json"), "--engine", "protocol-indexed", "--protocol", str(inputs / "protocol.json")],
        ),
        (
            "example-control",
            [sys.executable, "-B", "src/profile.py", str(inputs / "policy.json"), str(inputs / "control-machine.json"), str(base / "control.json"), "--family", str(inputs / "family.json")],
        ),
    )
    rows = []
    for name, command in commands:
        step = run_command(name=name, command=command, output=output, timeout=timeout, env=env)
        rows.append({**step, "ok": step["returncode"] == 0})
        if step["returncode"] != 0:
            return {"ok": False, "commands": rows, "validation": None}
    validation = validate_example(base)
    control = json.loads((base / "control.json").read_text())
    control_ok = (
        control["bindings"] == 2
        and control["matching_bindings"] == 0
        and control["failing_bindings"] == 2
        and control["shortest_failure"] == 1
    )
    validation["omitted_delete_control"] = {
        "ok": control_ok,
        "matching_bindings": control["matching_bindings"],
        "failing_bindings": control["failing_bindings"],
        "shortest_failure": control["shortest_failure"],
    }
    write_json(base / "validation.json", validation)
    return {"ok": validation["ok"] and control_ok, "commands": rows, "validation": validation}


def run_figures(output: Path, timeout: int) -> dict[str, Any]:
    env = core_environment()
    target = output / "figures"
    step = run_command(
        name="figures-regenerate",
        command=[sys.executable, "-B", "figures/build_paper_figures.py", "--output-directory", str(target)],
        output=output,
        timeout=timeout,
        env=env,
    )
    if step["returncode"] != 0:
        return {"ok": False, "command": step, "count": 0, "matches": []}
    actual = {path.name for path in target.glob("*.pdf")}
    # Compare with the manuscript figures when ../paper/ sits next to this
    # repository; otherwise use the SHA-256 digests of those same manuscript
    # files recorded in figures/manuscript-figures.sha256.json.
    paper_figures = PROJECT / "paper" / "figures"
    reference = "manuscript" if paper_figures.is_dir() else "recorded-sha256"
    recorded = json.loads((ROOT / "figures" / "manuscript-figures.sha256.json").read_text(encoding="utf-8"))["sha256"]
    rows = []
    for name in sorted(EXPECTED_FIGURES | actual):
        generated = target / name
        manuscript = paper_figures / name
        if reference == "manuscript":
            expected = sha256(manuscript) if manuscript.is_file() else None
        else:
            expected = recorded.get(name)
        generated_sha = sha256(generated) if generated.is_file() else None
        rows.append(
            {
                "name": name,
                "generated": generated.is_file(),
                "manuscript": manuscript.is_file(),
                "generated_sha256": generated_sha,
                "manuscript_sha256": expected,
                "byte_identical": generated_sha is not None and generated_sha == expected,
            }
        )
    ok = actual == EXPECTED_FIGURES and all(row["byte_identical"] for row in rows)
    return {"ok": ok, "command": step, "count": len(actual), "reference": reference, "matches": rows}


def requirement_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "==" not in line:
            rows.append({"requirement": line, "expected": None, "actual": None, "ok": False, "error": "exact pin required"})
            continue
        name, expected = line.split("==", 1)
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        rows.append({"requirement": line, "distribution": name, "expected": expected, "actual": actual, "ok": actual == expected})
    return rows


def full_preflight() -> dict[str, Any]:
    requirements = requirement_rows(ROOT / FULL_REQUIREMENTS)
    tools = []
    for spec in FULL_TOOLS:
        found = {name: shutil.which(name) for name in spec["executables"]}
        tools.append({**spec, "found": found, "ok": all(found.values())})
    return {
        "ok": all(row["ok"] for row in requirements) and all(row["ok"] for row in tools),
        "requirements_file": FULL_REQUIREMENTS,
        "requirements": requirements,
        "tools": tools,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("core", "portable", "framework", "query", "proofs", "full"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--step-timeout", type=int, default=600)
    parser.add_argument("--full-timeout", type=int, default=1800)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("choose a fresh output directory; evidence is never overwritten")
    if ROOT.resolve().is_relative_to(output):
        parser.error("output cannot be the artifact directory or one of its ancestors")

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "profile": args.profile,
        "started_utc": utc_now(),
        "artifact": str(ROOT),
        "python": sys.version,
        "platform": platform.platform(),
        "status": "RUNNING",
    }
    exit_code = 1
    try:
        if args.profile == "core":
            receipt["tests"] = run_tests(output, args.step_timeout, CORE_TEST_MODULES)
            receipt["evidence"] = run_evidence(output, args.step_timeout)
            receipt["motivating_example"] = run_example(output, args.step_timeout)
            receipt["figures"] = run_figures(output, args.step_timeout)
            passed = all(receipt[name]["ok"] for name in ("tests", "evidence", "motivating_example", "figures"))
            receipt["status"] = "PASS" if passed else "FAIL"
            exit_code = 0 if passed else 1
        elif args.profile == "portable":
            receipt["tests"] = run_tests(output, args.step_timeout, PORTABLE_TEST_MODULES)
            passed = receipt["tests"]["ok"]
            receipt["status"] = "PASS" if passed else "FAIL"
            exit_code = 0 if passed else 1
        elif args.profile in ("framework", "query"):
            requirements_file = FRAMEWORK_REQUIREMENTS if args.profile == "framework" else QUERY_REQUIREMENTS
            modules = FRAMEWORK_TEST_MODULES if args.profile == "framework" else QUERY_TEST_MODULES
            requirements = requirement_rows(ROOT / requirements_file)
            receipt["preflight"] = {
                "requirements_file": requirements_file,
                "requirements": requirements,
                "ok": all(row["ok"] for row in requirements),
            }
            if not receipt["preflight"]["ok"]:
                receipt["status"] = "UNAVAILABLE"
                receipt["reason"] = "the exact isolated Python environment is absent or mismatched"
                exit_code = 2
            else:
                receipt["tests"] = run_tests(output, args.step_timeout, modules)
                passed = receipt["tests"]["ok"]
                receipt["status"] = "PASS" if passed else "FAIL"
                exit_code = 0 if passed else 1
        elif args.profile == "proofs":
            compiler = shutil.which("lean")
            receipt["preflight"] = {"compiler": compiler, "ok": compiler is not None}
            if compiler is None:
                receipt["status"] = "UNAVAILABLE"
                receipt["reason"] = "Lean is not installed on PATH"
                exit_code = 2
            else:
                step = run_command(
                    name="lean-proofs",
                    command=[sys.executable, "-B", "proofs/check_lean.py", "--compiler", compiler, "--output", str(output / "proofs")],
                    output=output,
                    timeout=args.full_timeout,
                    env=core_environment(),
                )
                receipt["proofs"] = step
                receipt["status"] = "PASS" if step["returncode"] == 0 else "FAIL"
                exit_code = 0 if step["returncode"] == 0 else 1
        else:
            receipt["preflight"] = full_preflight()
            if not receipt["preflight"]["ok"]:
                receipt["status"] = "UNAVAILABLE"
                receipt["reason"] = "exact optional framework/native environment is absent or mismatched"
                exit_code = 2
            else:
                step = run_command(
                    name="full-release-verifier",
                    command=[sys.executable, "-B", "verify_release.py", "--output", str(output / "full-release")],
                    output=output,
                    timeout=args.full_timeout,
                    env=core_environment(),
                )
                receipt["full_verifier"] = step
                receipt["status"] = "PASS" if step["returncode"] == 0 else "FAIL"
                exit_code = 0 if step["returncode"] == 0 else 1
    except Exception as exc:
        receipt["status"] = "ERROR"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        exit_code = 1
    finally:
        receipt["finished_utc"] = utc_now()
        receipt["exit_code"] = exit_code
        write_json(output / "evaluation.json", receipt)
    print(json.dumps({"profile": args.profile, "status": receipt["status"], "receipt": str(output / "evaluation.json")}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
