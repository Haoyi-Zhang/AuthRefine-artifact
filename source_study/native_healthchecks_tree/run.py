"""Acquire, diagnose and replay the complete bounded native request language."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

from source_study.native_healthchecks import run as retained
from . import encoding, specification as spec
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


ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT.parents[1]


def stratum(case):
    return case["format"] + "-api-" + str(case["api_version"]) + "-" + case["initial_status"]


def key(case):
    return (case["arm"], case["format"], case["api_version"], case["initial_status"])


def native_call(source, output, arm, *, replay_plan=None, one=None):
    optimize = ["-" + "O" * sys.flags.optimize] if sys.flags.optimize else []
    command = [sys.executable, *optimize, "-B", "-m", __package__ + ".native",
               "--source", str(source), "--output", str(output), "--arm", arm]
    if replay_plan is not None:
        command += ["--replay-plan", str(replay_plan)]
    if one:
        command += ["--one", *map(str, one)]
    environment = os.environ.copy()
    environment.update(PYTHONPATH=str(ARTIFACT) + os.pathsep + environment.get("PYTHONPATH", ""),
                       PYTHONDONTWRITEBYTECODE="1")
    start = time.perf_counter()
    result = _run_file_backed(command, capture_output=True, text=True, env=environment)
    receipt = dict(command=command, elapsed_seconds=time.perf_counter() - start,
                   returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    if result.returncode:
        raise RuntimeError("native history acquisition failed:\n" + result.stdout + result.stderr)
    print(result.stdout.strip(), flush=True)
    return receipt


def acquire(output):
    if output.exists():
        raise ValueError("native tree acquisition requires a fresh output directory")
    bounds = encoding.bound_probe()
    dependencies = retained.dependency_record()
    output.mkdir(parents=True)
    spec.write(output / "encoding-bound-check.json", bounds)
    spec.write(output / "native-dependencies.json", dependencies)
    spec.write(output / "source-controls.json", retained.prepare_sources(output / "source-controls"))
    spec.write(output / "language.json", spec.language_manifest())
    runs = []
    for arm in spec.ARMS:
        runs.append(native_call(output / "source-controls" / arm, output / "native" / arm, arm))
    spec.write(output / "acquisition.json", dict(runs=runs, source_imports_replaced=False,
        source_observations_acquired_before_diagnosis=True, original_37_operation_study_modified=False))


def cases(output):
    observed = set()
    for arm in spec.ARMS:
        receipt = spec.read(output / "native" / arm / "collection.json")
        if (receipt["arm"] != arm or receipt["source_imports_replaced"] is not False or
                receipt["complete_sqlite_checkpoints"] is not True or receipt["cookie_state_preserved"] is not True):
            raise ValueError("native collection provenance differs")
        for item in receipt["cases"]:
            directory = output / "native" / arm / item["directory"]
            case = spec.read(directory / "observations.json.gz")
            if (key(case) in observed or case["arm"] != arm or case["replay_word"] is not None or item["word"] is not None or
                    not spec.typed_equal((case["format"], case["api_version"], case["initial_status"]),
                                         (item["format"], item["api_version"], item["initial_status"])) or
                    type(item["edges"]) is not int or item["edges"] != len(case["records"]) or item["directory"] != stratum(case)):
                raise ValueError("duplicated or mislabelled native tree")
            observed.add(key(case))
            yield directory, case
    expected = {(arm, fmt, api, status) for arm in spec.ARMS for fmt in spec.FORMATS
                for api in spec.API_VERSIONS for status in spec.INITIAL_STATUSES}
    if observed != expected:
        raise ValueError("native tree acquisition grid is incomplete")


def diagnose(output):
    from .audit import validate_acquisition
    validate_acquisition(output)
    index = []
    for directory, case in cases(output):
        results = encoding.diagnose(case)
        profile = Path("profiles") / case["arm"] / (stratum(case) + ".json.gz")
        spec.write(output / profile, results)
        index.append(dict(arm=case["arm"], format=case["format"], api_version=case["api_version"],
                          initial_status=case["initial_status"], profile=str(profile),
                          source_record=str((directory / "observations.json.gz").relative_to(output))))
    spec.write(output / "profiles.json", index)


def replay(output):
    index = spec.read(output / "profiles.json")
    plans = {arm: [] for arm in spec.ARMS}
    for row in index:
        profiles = spec.read(output / row["profile"])
        by_word = {}
        for result in profiles:
            for failure in result["first_bad_prefixes"]:
                by_word.setdefault(tuple(failure["word"]), []).append(result["mode"])
        for word, modes in sorted(by_word.items(), key=lambda item: (len(item[0]), item[0])):
            plans[row["arm"]].append(dict(format=row["format"], api_version=row["api_version"],
                initial_status=row["initial_status"], word=list(word), modes=sorted(modes),
                directory="word-" + str(len(plans[row["arm"]])).zfill(4), main_profile=row["profile"],
                main_record=row["source_record"]))
    receipts = []
    for arm, plan in plans.items():
        spec.write(output / "replay-plans" / (arm + ".json"), plan)
        if plan:
            receipt = native_call(output / "source-controls" / arm, output / "native-replay" / arm, arm,
                                  replay_plan=output / "replay-plans" / (arm + ".json"))
            receipts.append(dict(arm=arm, receipt=receipt))
    spec.write(output / "native-replay.json", receipts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("acquire", "diagnose", "replay", "verify", "all"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.command in ("acquire", "all"):
        acquire(output)
    if args.command in ("diagnose", "all"):
        diagnose(output)
    if args.command in ("replay", "all"):
        replay(output)
    from .audit import verify
    if args.command == "all":
        summary = verify(output)
        spec.write(output / "summary.json", summary)
        print(spec.canonical(summary))
    elif args.command == "verify":
        summary = verify(output)
        if not spec.typed_equal(summary, spec.read(output / "summary.json")):
            raise ValueError("retained bounded-tree summary differs from recomputed evidence")
        print(spec.canonical(summary))


if __name__ == "__main__":
    main()
