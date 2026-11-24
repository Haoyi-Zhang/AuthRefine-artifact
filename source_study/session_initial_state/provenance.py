"""Content-bound acquisition provenance; validation needs no native packages."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re

from .io import fields, read, require, same


ART = Path(__file__).resolve().parents[2]
CODE_PATHS = (
    "benchmarks/audit_session_initial_state.py",
    "source_study/session_initial_state/__init__.py",
    "source_study/session_initial_state/collector.py",
    "source_study/session_initial_state/contract.py",
    "source_study/session_initial_state/io.py",
    "source_study/session_initial_state/oracle.py",
    "source_study/session_initial_state/provenance.py",
    "source_study/session_initial_state/run.py",
    "source_study/session_initial_state/strategies.py",
    "source_study/session_initial_state/validation.py",
    "source_study/session_correspondence/__init__.py",
    "source_study/session_correspondence/fixtures.py",
    "source_study/session_correspondence/native.py",
    "source_study/stateful_sequence/__init__.py",
    "source_study/stateful_sequence/fixtures.py",
    "source_study/stateful_sequence/native.py",
    "source_study/stateful_sequence/source.py",
    "source_study/historical_h19/__init__.py",
    "source_study/historical_h19/source.py",
    "source_study/historical_h19/pins.json",
    "source_study/historical_h19/requirements.lock",
    "source_study/source/h19/after/piccolo_api/session_auth/tables.py",
)
EVIDENCE_PATHS = ("inputs.json.gz", "native-traces.jsonl.gz", "native-dependencies.json.gz", "source-execution.json")


def identity(root, relative):
    raw = (root / relative).read_bytes()
    return {"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def code_identities():
    return [identity(ART, path) for path in CODE_PATHS]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def verify_timestamps(start, finish):
    parsed = []
    for value in (start, finish):
        require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00", value) is not None,
                "acquisition timestamp must be a UTC instant with microseconds")
        parsed.append(datetime.fromisoformat(value))
    require(parsed[1] >= parsed[0], "acquisition finish precedes start")


def validate_dependency_record(value):
    fields(value, ("versions", "native_files", "python", "all_distributions"), "actual native dependency record")
    pins = read(ART / "source_study/historical_h19/pins.json")
    require(same(value["versions"], pins["required_versions"]), "actual native dependency versions differ from admission pins")
    require(same(value["native_files"], pins["native_files"]), "actual native dependency source identities differ")
    require(type(value["python"]) is str and bool(value["python"]), "native dependency Python runtime missing")
    require(type(value["all_distributions"]) is list, "actual distribution inventory required")
    versions = {}
    for row in value["all_distributions"]:
        fields(row, ("name", "version"), "actual distribution")
        require(all(type(row[key]) is str and bool(row[key]) for key in ("name", "version")), "actual distribution name/version must be strings")
        name = re.sub(r"[-_.]+", "-", row["name"]).lower()
        require(name not in versions, "ambiguous actual distribution identity")
        versions[name] = row["version"]
    lock = (ART / "source_study/historical_h19/requirements.lock").read_text()
    for line in lock.splitlines():
        if not line or line.startswith("#"):
            continue
        name, expected = line.split("==")
        name = re.sub(r"[-_.]+", "-", name).lower()
        require(versions.get(name) == expected, "actual installed distribution differs from lock: " + name)


def validate_source_record(value):
    require(type(value) is list and len(value) == 5, "executed source manifest coverage differs")
    from source_study.stateful_sequence.source import load
    # The admission loader parses and checks the selected source; it does not
    # execute the module or import the native ORM.
    expected = load()[3]
    for size, row in zip(range(2, 7), value):
        fields(row, ("size", "manifest"), "executed source manifest")
        require(same(row["size"], size) and same(row["manifest"], expected), "executed native source manifest differs")
        require(row["manifest"]["source_files_modified"] is False, "native source modification flag must be false")


def verify(directory, receipt):
    provenance = receipt["provenance"]
    fields(provenance, ("code_before", "code_after", "inputs_before", "evidence_files", "native_dependencies_rechecked"), "acquisition provenance")
    actual_code = code_identities()
    require(same(provenance["code_before"], actual_code) and same(provenance["code_after"], actual_code),
            "acquisition code/input identities differ from the executed sources")
    require(same(provenance["inputs_before"], identity(directory, "inputs.json.gz")),
            "pre-execution input identity differs")
    require(same(provenance["evidence_files"], [identity(directory, path) for path in EVIDENCE_PATHS]),
            "native evidence file identity differs")
    require(provenance["native_dependencies_rechecked"] is True, "native dependencies were not rechecked after execution")
    verify_timestamps(receipt["started_utc"], receipt["finished_utc"])
    dependencies = read(directory / "native-dependencies.json.gz")
    validate_dependency_record(dependencies)
    runtime = dependencies["python"].split()
    require(bool(runtime) and receipt["python"] == runtime[0],
            "acquisition Python runtime differs from the actual native dependency record")
    validate_source_record(read(directory / "source-execution.json"))
