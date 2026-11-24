"""Check every shipped Lean proof with an explicitly selected local compiler.

This runner downloads nothing and executes no installer. It preserves proof
sources and writes compiler identity, source hashes, stdout, stderr and status
to a fresh result directory. The checks certify only the Lean statements and
their declared premises, not the Python extractor or an application runtime.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import tempfile


# File-backed capture avoids a PIPE EOF wait when a verifier launches descendants
# that inherit stdout/stderr. It preserves subprocess.run's captured-output API
# while making the log descriptor independent of descendant lifetime.
_ORIGINAL_SUBPROCESS_RUN = subprocess.run

def _run_file_backed(*popenargs, **kwargs):
    capture_output = bool(kwargs.pop("capture_output", False))
    stdout_pipe = capture_output or kwargs.get("stdout") is subprocess.PIPE
    stderr_pipe = capture_output or kwargs.get("stderr") is subprocess.PIPE
    if not stdout_pipe and not stderr_pipe:
        return _ORIGINAL_SUBPROCESS_RUN(*popenargs, **kwargs)
    if capture_output and ("stdout" in kwargs or "stderr" in kwargs):
        raise ValueError("stdout and stderr arguments may not be used with capture_output")
    check = bool(kwargs.pop("check", False))
    text_mode = bool(kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("encoding"))
    encoding = kwargs.get("encoding") or "utf-8"
    errors = kwargs.get("errors") or "replace"
    out_file = tempfile.TemporaryFile(mode="w+b") if stdout_pipe else None
    err_file = tempfile.TemporaryFile(mode="w+b") if stderr_pipe else None
    try:
        if stdout_pipe:
            kwargs["stdout"] = out_file
        if stderr_pipe:
            kwargs["stderr"] = err_file
        result = _ORIGINAL_SUBPROCESS_RUN(*popenargs, check=False, **kwargs)
        if out_file is not None:
            out_file.flush(); out_file.seek(0)
            data = out_file.read()
            result.stdout = data.decode(encoding, errors) if text_mode else data
        if err_file is not None:
            err_file.flush(); err_file.seek(0)
            data = err_file.read()
            result.stderr = data.decode(encoding, errors) if text_mode else data
        if check and result.returncode:
            raise subprocess.CalledProcessError(
                result.returncode, result.args,
                output=getattr(result, "stdout", None),
                stderr=getattr(result, "stderr", None),
            )
        return result
    finally:
        if out_file is not None: out_file.close()
        if err_file is not None: err_file.close()



ARTIFACT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_output(value: str | bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, help="Path to a local Lean executable, or a command on PATH")
    parser.add_argument("--output", type=Path, required=True, help="New or empty directory for complete receipts")
    parser.add_argument("--timeout", type=int, default=60, help="Seconds allowed per proof file")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    resolved = shutil.which(args.compiler)
    if resolved is None:
        parser.error("the selected Lean compiler is not executable")
    compiler = Path(resolved).resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("--output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.pop("LEAN_PATH", None)
    environment.pop("LEAN_SYSROOT", None)
    version = _run_file_backed([str(compiler), "--version"], capture_output=True,
                             text=True, timeout=15, env=environment, check=False)
    (output / "compiler.stdout.log").write_text(version.stdout, encoding="utf-8")
    (output / "compiler.stderr.log").write_text(version.stderr, encoding="utf-8")
    summary = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "compiler": str(compiler),
        "compiler_sha256": sha256(compiler),
        "compiler_version": version.stdout.strip(),
        "compiler_exit_code": version.returncode,
        "scope": "Kernel checking of the shipped conditional Lean statements; no source extractor or application theorem inferred",
        "network_or_installer_used_by_runner": False,
        "proof_sources_modified": False,
        "results": [],
        "all_passed": False,
    }
    summary_path = output / "summary.json"

    def save() -> None:
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    if version.returncode:
        save()
        return 1
    proofs = sorted((ARTIFACT / "proofs").glob("*.lean")) + sorted(
        (ARTIFACT / "source_study" / "proofs").glob("*.lean")
    )
    if not proofs:
        summary["error"] = "No shipped Lean proof files were found"
        save()
        return 1
    save()
    for proof in proofs:
        relative = proof.relative_to(ARTIFACT).as_posix()
        stem = relative.replace("/", "__")[:-5]
        before = sha256(proof)
        command = [str(compiler), str(proof)]
        started = time.perf_counter()
        timed_out = False
        try:
            result = _run_file_backed(command, cwd=ARTIFACT, env=environment,
                                    text=True, capture_output=True, check=False,
                                    timeout=args.timeout)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, code = text_output(error.stdout), text_output(error.stderr), None
            timed_out = True
        after = sha256(proof)
        (output / (stem + ".stdout.log")).write_text(stdout, encoding="utf-8")
        (output / (stem + ".stderr.log")).write_text(stderr, encoding="utf-8")
        sorry_warning = "declaration uses 'sorry'" in stdout + stderr or "sorryAx" in stdout + stderr
        row = {
            "file": relative,
            "proof_sha256": before,
            "command": command,
            "exit_code": code,
            "timed_out": timed_out,
            "timeout_seconds": args.timeout,
            "wall_seconds": time.perf_counter() - started,
            "source_unchanged": before == after,
            "sorry_warning": sorry_warning,
            "passed": code == 0 and not timed_out and before == after and not sorry_warning,
        }
        (output / (stem + ".json")).write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        summary["results"].append(row)
        save()
        print(json.dumps({"file": relative, "exit_code": code, "passed": row["passed"]}), flush=True)
    summary["proof_count"] = len(proofs)
    summary["passed_count"] = sum(row["passed"] for row in summary["results"])
    summary["all_passed"] = summary["passed_count"] == len(proofs)
    save()
    print(json.dumps({"proof_count": len(proofs), "passed_count": summary["passed_count"],
                      "all_passed": summary["all_passed"]}), flush=True)
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
