"""Exercise and verify the native credential observation-admission contract.

Collection executes selected IR bodies with real Django ORM/SQLite primitives.
The two controls change one serializer argument in a private IR copy. The frozen
collector is unchanged, and complete application modules are never executed.
The check mode validates retained records without importing or executing Django.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
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


ART = Path(__file__).resolve().parents[1]
if str(ART) not in sys.path:
    sys.path.insert(0, str(ART))
from source_study.replay import source_check, read as source_read, ROOT as SOURCE_ROOT
from source_study.observation_evidence import object_fields, require, typed_equal, validate_credential_evidence

MODES = ("baseline_full", "readonly_integer", "version_boolean")
SOURCE_FILES = (
    "benchmarks/audit_credential_admission.py", "source_study/replay.py",
    "source_study/observation_evidence.py", "source_study/code/credential_flow_ir.py",
    "source_study/code/credential_flow_contexts.py", "source_study/code/credential_flow_native.py",
)
SCOPE = "Selected closed IR bodies with real Django ORM/SQLite primitives; no complete application, service or bubblewrap execution"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_identities():
    return {name: sha(ART / name) for name in SOURCE_FILES}


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "JSON evidence", "duplicate object key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("JSON evidence: nonfinite number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def write_new(path, value, *, compressed=False):
    raw = (json.dumps(value, sort_keys=True, indent=None if compressed else 2, allow_nan=False) + "\n").encode()
    if compressed:
        raw = gzip.compress(raw, mtime=0)
    with Path(path).open("xb") as handle:
        handle.write(raw)


def prepared_input(packet, mode):
    binding = deepcopy(packet["binding"])
    cases = packet["owned_inputs"] if mode == "baseline_full" else packet["owned_inputs"][:1]
    changes = []
    def visit(node):
        if type(node) is not list:
            return
        if len(node) == 4 and node[0] == "call" and node[1] == ["attribute", ["name", "check"], "to_dict"]:
            for keyword in node[3]:
                if ((mode == "readonly_integer" and keyword[0] == "readonly")
                        or (mode == "version_boolean" and keyword[0] == "v")):
                    before = deepcopy(keyword[1])
                    keyword[1] = ["constant", 0 if mode == "readonly_integer" else True]
                    changes.append({"keyword": keyword[0], "before": before, "after": deepcopy(keyword[1])})
        for child in node:
            visit(child)
    if mode != "baseline_full":
        visit(binding["programs"]["get_check"]["body"])
        require(len(changes) == 1, mode, "exactly one controlled serializer keyword must change")
    return binding, cases, changes


def collect(mode):
    packet = source_check()
    binding, cases, changes = prepared_input(packet, mode)
    # Importing the historical collector defines it; measure() initializes the
    # real Django boundary only in this fresh collection subprocess.
    from credential_flow_native import measure
    import django
    import sqlite3
    require(django.get_version() == "6.1.2", "native runtime", "source-pinned Django 6.1.2 required")
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    observations = measure(binding, cases)
    runtime = {"python": sys.version, "implementation": platform.python_implementation(),
               "Django": django.get_version(), "SQLite": sqlite3.sqlite_version,
               "started_utc": started_utc, "finished_utc": datetime.now(timezone.utc).isoformat(),
               "elapsed_seconds": time.monotonic() - started}
    return {"mode": mode, "changes": changes, "observations": observations,
            "runtime": runtime, "source_sha256": source_identities()}


def evaluate(mode, observations, packet):
    from credential_flow_contexts import expected
    _, cases, _ = prepared_input(packet, mode)
    if mode == "baseline_full":
        totals = validate_credential_evidence(observations, cases, expected)
        require(typed_equal(observations, source_read(SOURCE_ROOT / "data/credential-observations.json")),
                mode, "complete freshly executed baseline differs from retained observations")
        admitted, rejection = True, None
    else:
        # Reconstruct the exact intended fault from the independently retained
        # baseline row, including the one fewer IR expression step: reading
        # request.<field> visits two expression nodes, a constant visits one.
        baseline = source_read(SOURCE_ROOT / "data/credential-observations.json")
        wanted_row = deepcopy(baseline["rows"][0])
        keyword = "readonly" if mode == "readonly_integer" else "v"
        wanted_row["serializer_transfers"][0][keyword] = 0 if mode == "readonly_integer" else True
        wanted_row["IR_steps"] -= 1
        totals = Counter(contexts=1, actual_SELECTs=len(wanted_row["sql"]),
                         native_mac_calls=wanted_row["native_mac_calls"],
                         exact_project_identity_transfers=int(wanted_row["exact_resolved_project_identity_transferred"]),
                         serializer_transfers=len(wanted_row["serializer_transfers"]), differences=0)
        totals["status_" + str(wanted_row["observed"]["status"])] = 1
        wanted = {"rows": [wanted_row], "producer_records": [], "totals": dict(totals),
                  "original_application_modules_or_tests_executed": False,
                  "original_serializer_or_write_action_executed": False,
                  "original_deployment_or_randomness_security_certified": False}
        require(typed_equal(observations, wanted), mode, "control changed fields beyond the declared serializer fault and IR-step difference")
        restored = deepcopy(observations)
        restored["rows"][0]["serializer_transfers"][0][keyword] = baseline["rows"][0]["serializer_transfers"][0][keyword]
        validate_credential_evidence(restored, cases, expected)
        try:
            validate_credential_evidence(observations, cases, expected)
        except ValueError as error:
            admitted, rejection = False, str(error)
        else:
            raise ValueError(mode + ": controlled serializer type change was admitted")
        require(rejection.endswith("serializer readonly/version/record transfer differs in value or type"),
                mode, "control failed for an unrelated reason")
    first = observations["rows"][0]
    transfer = first["serializer_transfers"][0]
    return {"cases": len(cases), "original_frozen_collector_reported_agreement": all(row["agrees"] is True for row in observations["rows"]),
            "original_frozen_collector_reported_differences": observations["totals"]["differences"],
            "new_evidence_gate_admitted": admitted, "rejection": rejection,
            "admitted_totals": dict(totals) if admitted else None,
            "actual_SELECT_statements": sum(len(row["sql"]) for row in observations["rows"]),
            "request_readonly_type": type(first["observed"]["readonly"]).__name__,
            "serializer_readonly_type": type(transfer["readonly"]).__name__,
            "request_version_type": type(first["observed"]["version"]).__name__,
            "serializer_version_type": type(transfer["v"]).__name__,
            "full_baseline_equal_to_retained": mode == "baseline_full"}


def validate_runtime(runtime):
    object_fields(runtime, ("python", "implementation", "Django", "SQLite", "started_utc", "finished_utc", "elapsed_seconds"), "runtime")
    for field in ("python", "implementation", "Django", "SQLite", "started_utc", "finished_utc"):
        require(type(runtime[field]) is str and bool(runtime[field]), "runtime." + field, "runtime description required")
    require(runtime["implementation"] == "CPython" and runtime["Django"] == "6.1.2", "runtime", "recorded native framework differs")
    elapsed = runtime["elapsed_seconds"]
    require(type(elapsed) in (float, int) and math.isfinite(elapsed) and elapsed >= 0, "runtime", "invalid recorded elapsed time")
    started, finished = (datetime.fromisoformat(runtime[field]) for field in ("started_utc", "finished_utc"))
    require(started.tzinfo is not None and finished.tzinfo is not None and finished >= started, "runtime", "invalid acquisition interval")


def receipt(mode, payload, observation_path, packet):
    object_fields(payload, ("mode", "changes", "observations", "runtime", "source_sha256"), "collection packet")
    require(typed_equal(payload["mode"], mode), mode, "collection mode differs")
    require(typed_equal(payload["source_sha256"], source_identities()), mode, "collection code identities differ")
    validate_runtime(payload["runtime"])
    _, _, changes = prepared_input(packet, mode)
    require(typed_equal(payload["changes"], changes), mode, "controlled source-expression change differs")
    return {"mode": mode, "scope": SCOPE, "changes": changes, "runtime": payload["runtime"],
            "source_sha256": payload["source_sha256"], **evaluate(mode, payload["observations"], packet),
            "native_Django_ORM_and_SQLite_executed": True, "native_bubblewrap_replay_invoked": False,
            "original_application_modules_executed": False, "new_independent_applications": 0,
            "observation_file": observation_path.name, "observation_sha256": sha(observation_path)}


def summary(receipts, output):
    modes = [row["mode"] for row in receipts]
    return {"scope": SCOPE, "modes": modes, "complete_three_mode_review": modes == list(MODES),
            "actual_native_contexts_executed": sum(row["cases"] for row in receipts),
            "actual_SELECT_statements": sum(row["actual_SELECT_statements"] for row in receipts),
            "baseline_contexts_admitted": sum(row["cases"] for row in receipts if row["new_evidence_gate_admitted"]),
            "type_controls_rejected": sum(not row["new_evidence_gate_admitted"] for row in receipts),
            "original_application_modules_executed": False, "new_independent_applications": 0,
            "source_sha256": source_identities(),
            "output_sha256": {name: sha(output / name) for mode in modes
                              for name in (mode + ".json", mode + ".observations.json.gz")}}


def run(mode, output):
    packet = source_check()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipts = []
    for selected in MODES if mode == "all" else (mode,):
        command = [sys.executable, "-B", "-W", "error", str(Path(__file__).resolve()), "--collect", selected]
        child = _run_file_backed(command, capture_output=True, text=True, timeout=180)
        require(child.returncode == 0 and child.stderr == "", selected,
                "native subprocess failed: " + child.stderr)
        payload = decode(child.stdout)
        path = output / (selected + ".observations.json.gz")
        # Validate before retaining any observation or success receipt.
        evaluate(selected, payload["observations"], packet)
        write_new(path, payload["observations"], compressed=True)
        row = receipt(selected, payload, path, packet)
        write_new(output / (selected + ".json"), row)
        receipts.append(row)
    result = summary(receipts, output)
    write_new(output / "summary.json", result)
    return result


def check(output):
    """Read-only reconciliation; no import of Django or the native collector."""
    django_before = {name for name in sys.modules if name == "django" or name.startswith("django.")}
    packet = source_check()
    output = Path(output).resolve()
    stored_summary = decode((output / "summary.json").read_bytes())
    modes = stored_summary.get("modes")
    require(type(modes) is list and (modes == list(MODES) or (len(modes) == 1 and modes[0] in MODES)),
            "credential review", "one declared mode or the complete ordered three-mode review required")
    wanted_files = {"summary.json", *(name for mode in modes for name in (mode + ".json", mode + ".observations.json.gz"))}
    require({path.name for path in output.iterdir()} == wanted_files, "credential review", "complete result file set required")
    require(all((output / name).is_file() and not (output / name).is_symlink() for name in wanted_files),
            "credential review", "plain evidence files required")
    receipts = []
    original_hashes = {name: sha(output / name) for name in wanted_files}
    for mode in modes:
        record = decode((output / (mode + ".json")).read_bytes())
        observations_path = output / (mode + ".observations.json.gz")
        observations = decode(gzip.decompress(observations_path.read_bytes()))
        payload = {"mode": mode, "changes": record["changes"], "observations": observations,
                   "runtime": record["runtime"], "source_sha256": record["source_sha256"]}
        expected = receipt(mode, payload, observations_path, packet)
        require(typed_equal(record, expected), mode, "retained receipt differs from raw evidence and current admission")
        receipts.append(record)
    require(typed_equal(stored_summary, summary(receipts, output)), "credential review", "summary differs from complete receipts")
    require(typed_equal(original_hashes, {name: sha(output / name) for name in wanted_files}), "credential review", "retained files changed")
    django_after = {name for name in sys.modules if name == "django" or name.startswith("django.")}
    require(django_after == django_before, "read-only check", "unexpected Django import")
    return {"status": "PASS", "modes": modes, "complete_three_mode_review": modes == list(MODES),
            "retained_native_contexts": stored_summary["actual_native_contexts_executed"],
            "baseline_contexts_admitted": stored_summary["baseline_contexts_admitted"],
            "type_controls_rejected": stored_summary["type_controls_rejected"],
            "actual_execution_in_this_check": False, "Django_imported_by_check": False,
            "retained_files_changed": False, "checked_source_files": len(SOURCE_FILES),
            "retained_file_sha256": original_hashes, "verifier_sha256": sha(Path(__file__))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("all", *MODES, "check"), default="all")
    parser.add_argument("--output", type=Path, help="fresh collection directory")
    parser.add_argument("--results", type=Path, default=ART / "results/credential-admission-review", help="retained directory for check mode")
    parser.add_argument("--receipt", type=Path, help="new check receipt outside the retained directory")
    parser.add_argument("--collect", choices=MODES, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.collect is not None:
            print(json.dumps(collect(args.collect), allow_nan=False))
            return 0
        if args.mode == "check":
            require(args.output is None, "check", "use --results for retained evidence")
            if args.receipt is not None:
                require(not args.receipt.exists() and not args.receipt.resolve().is_relative_to(args.results.resolve()),
                        "check receipt", "a new file outside the retained directory is required")
            result = check(args.results)
            if args.receipt is not None:
                args.receipt.parent.mkdir(parents=True, exist_ok=True)
                write_new(args.receipt, result)
        else:
            require(args.output is not None and args.receipt is None, "collection", "--output must name a fresh directory")
            result = run(args.mode, args.output)
    except Exception as error:
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__, "error": str(error)}))
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
