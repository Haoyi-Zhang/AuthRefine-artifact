"""Acquire complete-module executions, diagnose fixed configurations and replay."""
import argparse
import base64
import csv
import difflib
import gzip
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from . import contracts, outcomes, production
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


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with path.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
                with io.TextIOWrapper(zipped, encoding="utf-8") as text:
                    json.dump(value, text, sort_keys=True, separators=(",", ":"), allow_nan=False)
    else:
        path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def dependency_record():
    result = []
    for line in (ROOT / "requirements.lock").read_text().splitlines():
        name, version = line.split("==")
        dist = importlib.metadata.distribution(name)
        if dist.version != version: raise ValueError("native dependency differs: " + name)
        verified = []
        for row in csv.reader(io.StringIO(dist.read_text("RECORD") or "")):
            relative, digest, size = row
            if not digest: continue
            algorithm, encoded = digest.split("=", 1)
            raw = dist.locate_file(relative).read_bytes()
            wanted = base64.urlsafe_b64encode(hashlib.new(algorithm, raw).digest()).decode().rstrip("=")
            if wanted != encoded or (size and len(raw) != int(size)):
                raise ValueError("native distribution integrity differs: " + name + ":" + relative)
            verified.append(dict(path=relative, digest=digest, bytes=len(raw)))
        if not verified: raise ValueError("native distribution has no verifiable files: " + name)
        result.append(dict(name=name, version=version, verified_files=verified))
    return result


def source_identity():
    evidence = read(ROOT / "source-evidence.json")
    for row in evidence["files"]:
        raw = (ROOT / "source" / row["path"]).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if actual != row["upstream_git_blob"] or len(raw) != row["upstream_bytes"]:
            raise ValueError("upstream source bytes differ: " + row["path"])
    return evidence


def controls():
    return {
        "omit_readonly_context": ("hc/api/views.py", "check.to_dict(readonly=request.readonly, v=request.v)", "check.to_dict(v=request.v)", 3),
        "wrong_project_context": ("hc/api/decorators.py", "        request.project = project", "        request.project = Project.objects.order_by(\"id\").first()", 2),
        "omit_pause_persistence": ("hc/api/views.py", "    check.save(update_fields=(\"status\", \"last_start\", \"alert_after\"))", "    pass", 1),
        "reject_readonly_get": ("hc/api/views.py", "@authorize_read\ndef get_check(", "@authorize\ndef get_check(", 1),
    }


def prepare_sources(destination):
    evidence = source_identity()
    manifest = []
    for arm in contracts.ARMS:
        target = destination / arm
        shutil.copytree(ROOT / "source", target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        patch = ""
        if arm != "original":
            path, old, new, expected_count = controls()[arm]
            original = (target / path).read_text()
            if original.count(old) != expected_count: raise ValueError("source regression anchor differs")
            changed = original.replace(old, new)
            (target / path).write_text(changed)
            patch = "".join(difflib.unified_diff(original.splitlines(keepends=True), changed.splitlines(keepends=True), fromfile="original/" + path, tofile=arm + "/" + path))
        manifest.append(dict(arm=arm, patch=patch, historical_deployment_executed=False,
                             current_complete_source_modules=True,
                             files=[dict(path=row["path"], bytes=(target / row["path"]).stat().st_size, sha256=hashlib.sha256((target / row["path"]).read_bytes()).hexdigest()) for row in evidence["files"]]))
    return manifest


def subprocess_native(source, output, arm, one=None, limit=None):
    optimize = ["-" + "O" * sys.flags.optimize] if sys.flags.optimize else []
    command = [sys.executable, *optimize, "-m", __package__ + ".native", "--source", str(source), "--output", str(output), "--arm", arm]
    if one: command += ["--one", *map(str, one)]
    if limit is not None: command += ["--limit", str(limit)]
    environment = os.environ.copy()
    package_base = ROOT.parent if __package__ == "native_healthchecks" else ROOT.parents[1]
    environment["PYTHONPATH"] = str(package_base) + os.pathsep + environment.get("PYTHONPATH", "")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = _run_file_backed(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode:
        raise RuntimeError("native subprocess failed:\n" + completed.stdout + completed.stderr)
    return dict(command=command, stdout=completed.stdout, stderr=completed.stderr, returncode=completed.returncode)


def acquire(output):
    if output.exists(): raise ValueError("acquisition needs a new output directory")
    dependencies = dependency_record()
    output.mkdir(parents=True)
    write(output / "native-dependencies.json", dependencies)
    write(output / "source-controls.json", prepare_sources(output / "source-controls"))
    write(output / "protocol.json", dict(operations=contracts.protocol(), callers=contracts.CALLERS,
        configurations=contracts.configurations(), key_formats=contracts.FORMATS, api_versions=contracts.API_VERSIONS,
        whole_application_state_graph=False, configuration_dependent_native_targets=True,
        shared_target_correspondence_family=False))
    runs = []
    for arm in contracts.ARMS:
        runs.append(subprocess_native(output / "source-controls" / arm, output / "native" / arm, arm))
        print(runs[-1]["stdout"].strip(), flush=True)
    write(output / "acquisition.json", dict(runs=runs, all_application_modules_imported_intact=True,
        source_imports_replaced=False, observation_acquired_before_production_diagnosis=True))


def cases(output):
    observed = []
    for arm in contracts.ARMS:
        document = read(output / "native" / arm / "observations.json.gz")
        for case in document["cases"]:
            observed.append((case["arm"], case["format"], case["api_version"], case["configuration"]))
            yield case
    expected = {(arm, fmt, api, configuration) for arm in contracts.ARMS for fmt in contracts.FORMATS for api in contracts.API_VERSIONS for configuration in contracts.configurations()}
    if len(observed) != len(set(observed)) or set(observed) != expected: raise ValueError("native configuration grid differs")


def diagnose(output):
    reports = []
    for case in cases(output):
        validation = contracts.check_case(case)
        profiles = [production.diagnose(case, caller, mode) for caller in contracts.CALLERS for mode in ("complete", "http_status")]
        reports.append(dict(arm=case["arm"], format=case["format"], api_version=case["api_version"], configuration=case["configuration"], validation=validation, profiles=profiles))
    write(output / "profiles.json.gz", reports)
    return reports


def replay(output):
    reports = read(output / "profiles.json.gz")
    replays = []
    for number, report in enumerate(reports):
        witnesses = [p for p in report["profiles"] if not p["equivalent"]]
        if not witnesses: continue
        length = max(p["length"] for p in witnesses)
        directory = output / "native-replay" / ("case-" + str(number).zfill(3))
        receipt = subprocess_native(output / "source-controls" / report["arm"], directory, report["arm"],
                                    (report["format"], report["api_version"], report["configuration"]), length)
        case = read(directory / "observations.json.gz")["cases"][0]
        contracts.check_case(case, required_length=length)
        checked = []
        for witness in witnesses:
            result = outcomes.independent_profile(case, witness["caller"], witness["mode"], replay_length=length)
            if result["length"] != witness["length"] or result["equivalent"]:
                raise ValueError("fresh native replay did not reproduce the recorded first prefix")
            checked.append(dict(caller=witness["caller"], mode=witness["mode"], length=witness["length"], indices=witness["indices"]))
        replays.append(dict(case_index=number, collected_prefix_length=length, checked_witnesses=checked, receipt=receipt,
                            native_record=str(directory.relative_to(output) / "observations.json.gz")))
    write(output / "native-replay.json", replays)


def upstream_tests(output):
    environment = os.environ.copy()
    package_base = ROOT.parent if __package__ == "native_healthchecks" else ROOT.parents[1]
    environment.update(PYTHONPATH=str(ROOT / "source") + os.pathsep + str(package_base),
        DJANGO_SETTINGS_MODULE=__package__ + ".settings", HEALTHCHECKS_DB=str(output / "upstream-tests.sqlite"), PYTHONDONTWRITEBYTECODE="1")
    optimize = ["-" + "O" * sys.flags.optimize] if sys.flags.optimize else []
    command = [sys.executable, *optimize, "-m", "django", "test", "hc.api.tests.test_get_check", "hc.api.tests.test_pause", "hc.api.tests.test_resume", "--noinput", "--verbosity", "1"]
    result = _run_file_backed(command, env=environment, capture_output=True, text=True)
    write(output / "upstream-tests.json", dict(command=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
        test_modules_unmodified=True, test_configuration="selected native API apps and original API URLConf; SQLite model synchronization"))
    if result.returncode: raise ValueError("original upstream API tests failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("acquire", "diagnose", "replay", "upstream", "verify", "all"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.command in ("acquire", "all"): acquire(output)
    if args.command in ("diagnose", "all"): diagnose(output)
    if args.command in ("replay", "all"): replay(output)
    if args.command in ("upstream", "all"): upstream_tests(output)
    from .summarize import verify
    if args.command == "all":
        summary = verify(output)
        write(output / "summary.json", summary)
        print(json.dumps(summary, sort_keys=True))
    elif args.command == "verify":
        summary = verify(output)
        if production.canonical(summary) != production.canonical(read(output / "summary.json")):
            raise ValueError("retained summary differs from recomputed native evidence")
        print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__": main()
