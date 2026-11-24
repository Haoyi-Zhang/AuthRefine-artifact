"""Read-only audit of the retained complete-output comparison evidence.

This reader does not import or execute a diagnosis implementation.  It checks
the retained process records, complete output identities and derived summaries
against the original scientific inputs.  The acquisition program and its
recorded source identities remain unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
from itertools import product
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("per-binding-product", "per-binding-target", "scan", "support-indexed",
           "finite-domain", "cudd")
TIMES = ("diagnosis_wall_ns", "diagnosis_cpu_ns", "serialization_ns")
COUNTERS = ("output_sha256", "output_bytes", "bindings", "matching", "failure_lengths",
            "diagnostic_reference_calls", "replay_steps", "graph_cells", "symbolic_nodes",
            "symbolic_peak_nodes", "symbolic_conditional_operations", "symbolic_predicates",
            "symbolic_cache_hits", "symbolic_regions", "family_relation_nodes",
            "family_relation_coordinates", "support_queries", "index_memberships_created",
            "index_memberships_removed")
WORKER_FIELDS = frozenset(("method", "records", "python", "platform",
                           "complete_outputs_compared", "process_peak_rss_kib", "dd_package"))
TRIAL_FIELDS = WORKER_FIELDS | {"repeat", "exit_code", "process_wall_ns", "stdout", "stderr"}
RECORD_FIELDS = frozenset(("id", *TIMES, *COUNTERS))
SOURCE_PATHS = (
    "benchmarks/symbolic_comparison.py", "benchmarks/stateful_family.py",
    "src/symbolic_family.py", "src/symbolic.py", "src/checker.py", "src/extensions.py",
    "src/protocol_profile.py", "src/protocol_grouped.py", "src/family_diagnosis.py")
ORIGIN_PATHS = ("results/family-cost/inputs.json", "results/family-cost/profiles.json",
                "results/session-correspondence/inputs.json.gz",
                "results/native-policy-store/inputs.json.gz")
ROOT_FILES = {"inputs.json.gz", "profiles.json.gz", "trials.json", "summary.json", "environment.json"}
SUMMARY_CONTRACT = {
    "output_contract": "all legal members, canonical first shortest word, every fixed-binding replay field",
    "timing_contract": "schema/family validation, relation/index construction, complete graph admission, diagnosis and all individual replays",
    "outside_diagnosis_clock": ["process startup", "module imports", "input decoding", "comparison against expected output", "output serialization"],
    "counter_interpretation": "Concrete reference calls, finite-domain recursive ITE invocations and CUDD ITE API calls are different units; timing compares complete tasks.",
    "source_reuse": "The earlier two-session targets also occur in the expanded session cohort. Caller languages and initial files are tasks on the same source interfaces, not additional applications.",
    "uncertainty": "Seven sequential rotated repetitions by default; ranges are observed minima/maxima on this host, not confidence intervals.",
}
SCOPE = {
    "operation": "read-only reconciliation of retained evidence",
    "executed_diagnosis_or_backend": False,
    "process_identity": "one retained stdout/stderr pair and one parent receipt per method and repetition",
    "backend_identity": "worker-reported package and runtime metadata, checked against the retained environment and dependency pins",
    "output_identity": "canonical complete-output byte count and digest, checked against every retained legal-binding profile",
    "limits": [
        "The historical worker record does not retain a process identifier or executable binary digest.",
        "The worker reports complete-output comparison; its retained digest binds that report to the expected output, not to an independent execution transcript.",
        "This audit does not execute CUDD, repeat timings, or independently re-prove the semantic correctness of the expected profiles.",
    ],
}


class EvidenceError(ValueError):
    """Retained evidence does not satisfy its acquisition contract."""


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def same(left, right):
    """JSON equality with distinct Boolean, integer, and floating-point values."""
    return encoded(left) == encoded(right)


def fields(value, expected, label):
    require(type(value) is dict and set(value) == set(expected), label + ": exact fields required")


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, label + ": integer required")


def string(value, label):
    require(type(value) is str and bool(value), label + ": nonempty string required")


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "JSON: duplicate key " + key)
        result[key] = value
    return result


def _constant(value):
    raise EvidenceError("JSON: nonfinite constant " + value)


def _float(value):
    parsed = float(value)
    require(math.isfinite(parsed), "JSON: nonfinite floating-point value")
    return parsed


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("invalid JSON: " + str(error)) from error


def read(path):
    raw = path.read_bytes()
    try:
        return decode(gzip.decompress(raw) if path.suffix == ".gz" else raw)
    except (OSError, EOFError) as error:
        raise EvidenceError("invalid compressed evidence: " + str(path)) from error


def applicable(task):
    return METHODS if task["protocol"] is None else METHODS[2:]


def source_tasks(root):
    """Reconstruct the declared task list from the four original input files."""
    cases = read(root / ORIGIN_PATHS[0])
    profiles = read(root / ORIGIN_PATHS[1])
    require(type(cases) is list and type(profiles) is list, "family-cost origin lists")
    require(len({v["id"] for v in cases}) == len(cases), "family-cost unique case identities")
    require(len({v["id"] for v in profiles}) == len(profiles), "family-cost unique profile identities")
    require({v["id"] for v in profiles} == {v["id"] for v in cases}, "family-cost origin coverage")
    expected = {row["id"]: row["profiles"] for row in profiles}
    tasks = [{"id": "family-cost/" + case["id"], "case": case["id"],
              "cohort": "family-cost", "group": case["group"], "regime": case["regime"],
              "caller": "total", "protocol": None, "policy": case["policy"],
              "machine": case["machine"], "family": case.get("family"),
              "expected": expected[case["id"]]} for case in cases]
    for cohort, source in zip(("session-correspondence", "native-policy-store"), ORIGIN_PATHS[2:]):
        cases = read(root / source)
        require(type(cases) is list, cohort + ": origin list")
        require(len({v["id"] for v in cases}) == len(cases), cohort + ": unique case identities")
        for case in cases:
            require(type(case["callers"]) is dict and "total" not in case["callers"], cohort + ": caller identities")
            for caller, protocol in [("total", None), *case["callers"].items()]:
                key = "support-indexed" if protocol is None else "protocol-grouped/" + caller
                tasks.append({"id": cohort + "/" + case["id"] + "/" + caller,
                              "case": case["id"], "cohort": cohort,
                              "group": case.get("arm", "native"), "regime": case.get("arm", "native"),
                              "caller": caller, "protocol": protocol, "policy": case["policy"],
                              "machine": case["machine"], "family": case["family"],
                              "expected": case["expected"][key]})
    require(len({v["id"] for v in tasks}) == len(tasks), "unique declared task identities")
    return tasks


def validate_profiles(task):
    """Check full family coverage and the retained replay schema, without diagnosis."""
    profiles = task["expected"]
    require(type(profiles) is list and bool(profiles), task["id"] + ": nonempty complete profiles")
    aliases = task["policy"]["aliases"]
    names = [alias["name"] for alias in aliases]
    require(len(set(names)) == len(names), "unique binding coordinates")
    candidates = {alias["name"]: alias["candidates"] for alias in aliases}
    if task["family"] is None:
        cardinality = 1
        for alias in aliases:
            require(len(set(alias["candidates"])) == len(alias["candidates"]), "unique alias candidates")
            cardinality *= len(alias["candidates"])
        require(cardinality == len(profiles), task["id"] + ": complete Cartesian family denominator")
        family = [dict(zip(names, choices)) for choices in product(*(candidates[name] for name in names))]
    else:
        require(type(task["family"]) is list and bool(task["family"]), "declared family list")
        family, seen = [], set()
        for binding in task["family"]:
            key = encoded(binding)
            if key not in seen:
                seen.add(key)
                family.append(binding)
    require(len(family) == len(profiles), task["id"] + ": complete legal-family denominator")
    alphabet = task["machine"]["alphabet"]
    for binding, profile in zip(family, profiles):
        fields(binding, names, "binding")
        for name, value in binding.items():
            require(type(value) is str and value in candidates[name], "binding candidate")
        fields(profile, ("binding", "equivalent", "length", "indices", "trace"), "profile")
        require(same(profile["binding"], binding), "profile binding order and identity")
        require(type(profile["equivalent"]) is bool, "profile equivalence Boolean")
        if profile["equivalent"]:
            require(all(profile[key] is None for key in ("length", "indices", "trace")), "matching profile has no failure witness")
            continue
        integer(profile["length"], "failure length", minimum=1)
        require(type(profile["indices"]) is list and type(profile["trace"]) is list,
                "failure indices and replay lists")
        require(len(profile["indices"]) == len(profile["trace"]) == profile["length"], "complete replay length")
        for position, (index, step) in enumerate(zip(profile["indices"], profile["trace"])):
            integer(index, "replay alphabet index")
            require(index < len(alphabet), "replay index in target alphabet")
            expected_fields = {"binding", "request", "source", "target", "compared_equal", "decision_equal", "state_equal"}
            if task["protocol"] is not None:
                expected_fields |= {"protocol_state", "source_state", "target_state"}
            fields(step, expected_fields, "replay step")
            require(same(step["binding"], binding) and same(step["request"], alphabet[index]), "replay request and binding identity")
            for key in ("compared_equal", "decision_equal", "state_equal"):
                require(type(step[key]) is bool, "replay comparison Boolean: " + key)
            for key in ("source", "target"):
                require(type(step[key]) is list and len(step[key]) == 2 and step[key][0] in ("allow", "deny"), "replay observed result")
                integer(step[key][1], "replay observed state")
            require(step["decision_equal"] is (step["source"][0] == step["target"][0]), "replay decision comparison")
            require(step["state_equal"] is (step["source"][1] == step["target"][1]), "replay state comparison")
            require(step["compared_equal"] is (step["decision_equal"] and step["state_equal"]), "replay combined comparison")
            require(step["compared_equal"] is (position < profile["length"] - 1), "replay stops at first failure")
            for key in expected_fields & {"protocol_state", "source_state", "target_state"}:
                integer(step[key], "replay " + key)


def prepare_tasks(inputs, profiles, origins):
    require(type(inputs) is list and type(profiles) is list, "input/profile lists")
    require(len(inputs) == len(profiles) == len(origins), "complete input/profile denominator")
    tasks = []
    for value, row, origin in zip(inputs, profiles, origins):
        fields(value, ("id", "case", "cohort", "group", "regime", "caller", "protocol", "policy", "machine", "family"), "task")
        fields(row, ("id", "profiles"), "profile container")
        require(type(value["id"]) is str and row["id"] == value["id"], "input/profile identity and order")
        task = {**value, "expected": row["profiles"]}
        require(same(task, origin), "task and complete profiles differ from scientific origin: " + value["id"])
        validate_profiles(task)
        payload = encoded(task["expected"])
        task["output_contract"] = {
            "output_sha256": hashlib.sha256(payload).hexdigest(), "output_bytes": len(payload),
            "bindings": len(task["expected"]),
            "matching": sum(row["equivalent"] for row in task["expected"]),
            "failure_lengths": sorted({row["length"] for row in task["expected"] if not row["equivalent"]}),
        }
        tasks.append(task)
    require(len({v["id"] for v in tasks}) == len(tasks), "unique comparison task identities")
    return tasks


def validate_environment(environment, identities, packages):
    fields(environment, ("source_identities", "input_preparation_wall_ns", "python", "executable", "platform", "packages", "campaign_sources_unchanged"), "environment")
    fields(environment["source_identities"], SOURCE_PATHS, "historical source identities")
    require(same(environment["source_identities"], identities), "historical acquisition source identity differs")
    integer(environment["input_preparation_wall_ns"], "input preparation time")
    for key in ("python", "executable", "platform"):
        string(environment[key], "environment " + key)
    require(Path(environment["executable"]).is_absolute(), "recorded executable path must be absolute")
    require(environment["campaign_sources_unchanged"] is True, "campaign source stability report")
    require(same(environment["packages"], packages) and packages.get("dd") == "0.6.0", "recorded dependency pins")


def validate_trial(trial, raw, stderr, tasks, environment, repeat, method):
    fields(raw, WORKER_FIELDS, "raw worker")
    fields(trial, TRIAL_FIELDS, "process receipt")
    require(same(raw, {key: trial[key] for key in WORKER_FIELDS}), "complete raw worker and receipt differ")
    integer(trial["repeat"], "repeat")
    require(trial["repeat"] == repeat and trial["method"] == method, "rotated method/repetition grid")
    integer(trial["exit_code"], "process return code")
    require(trial["exit_code"] == 0 and raw["complete_outputs_compared"] is True, "successful checked process")
    integer(trial["process_wall_ns"], "process wall time", minimum=1)
    integer(raw["process_peak_rss_kib"], "process peak RSS", minimum=1)
    require(raw["python"] == environment["python"] and raw["platform"] == environment["platform"], "worker runtime metadata differs")
    require(same(raw["dd_package"], environment["packages"]["dd"] if method == "cudd" else None), "worker backend metadata differs")
    stem = f"trials/repeat-{repeat:02d}-{method}"
    require(trial["stdout"] == stem + ".stdout.json" and trial["stderr"] == stem + ".stderr.txt", "exact worker log paths")
    require(type(stderr) is bytes and stderr == b"", "worker stderr must be empty")
    selected = [task for task in tasks if method in applicable(task)]
    require(type(raw["records"]) is list and len(raw["records"]) == len(selected), "complete method/task denominator")
    elapsed = 0
    for task, row in zip(selected, raw["records"]):
        fields(row, RECORD_FIELDS, "timed record")
        require(row["id"] == task["id"], "exact method/task order")
        for key in TIMES + tuple(k for k in COUNTERS if k not in ("output_sha256", "failure_lengths")):
            integer(row[key], "timed record " + key)
        require(type(row["output_sha256"]) is str and re.fullmatch("[0-9a-f]{64}", row["output_sha256"]) is not None, "output digest shape")
        require(type(row["failure_lengths"]) is list, "failure strata list")
        for length in row["failure_lengths"]:
            integer(length, "failure stratum", minimum=1)
        require(same({key: row[key] for key in task["output_contract"]}, task["output_contract"]), "complete output identity and denominator")
        elapsed += row["diagnosis_wall_ns"] + row["serialization_ns"]
    require(trial["process_wall_ns"] >= elapsed, "process duration cannot be shorter than its sequential timed sections")


def derive_summary(tasks, trials, repeats):
    matrix = {(trial["repeat"], trial["method"]): {row["id"]: row for row in trial["records"]} for trial in trials}
    rows = []
    for task in tasks:
        row = {key: task[key] for key in ("id", "case", "cohort", "group", "regime", "caller")}
        row["methods"] = {}
        for method in applicable(task):
            samples = [matrix[repeat, method][task["id"]] for repeat in range(repeats)]
            entry = {}
            for key in COUNTERS:
                values = [sample[key] for sample in samples]
                if key in ("symbolic_nodes", "symbolic_peak_nodes"):
                    entry[key] = {"min": min(values), "max": max(values), "samples": values}
                else:
                    require(all(same(value, values[0]) for value in values), "stable repeated work/output: " + key)
                    entry[key] = values[0]
            for key in TIMES:
                values = [sample[key] for sample in samples]
                entry[key] = {"median": statistics.median(values), "min": min(values), "max": max(values), "samples": values}
            row["methods"][method] = entry
        rows.append(row)
    return {"status": "PASS", "tasks": len(tasks),
            "case_method_pairs": sum(len(applicable(task)) for task in tasks), "repeats": repeats,
            "processes": len(trials), "timed_task_records": sum(len(trial["records"]) for trial in trials),
            "cohort_tasks": dict(sorted(Counter(task["cohort"] for task in tasks).items())),
            "methods": list(METHODS), "records": rows, **SUMMARY_CONTRACT}


def validate_campaign(tasks, trials, retained, environment, workers, errors):
    require(type(retained) is dict and "repeats" in retained, "retained summary")
    repeats = retained["repeats"]
    integer(repeats, "repeat count", minimum=3)
    require(repeats <= 15, "repeat count at most 15")
    grid = [(repeat, method) for repeat in range(repeats)
            for method in METHODS[repeat % len(METHODS):] + METHODS[:repeat % len(METHODS)]]
    require(type(trials) is list and len(trials) == len(grid), "complete method/repetition grid")
    expected_stdout = {f"trials/repeat-{repeat:02d}-{method}.stdout.json" for repeat, method in grid}
    expected_stderr = {name.replace(".stdout.json", ".stderr.txt") for name in expected_stdout}
    require(type(workers) is dict and set(workers) == expected_stdout, "complete raw stdout grid")
    require(type(errors) is dict and set(errors) == expected_stderr, "complete raw stderr grid")
    for trial, (repeat, method) in zip(trials, grid):
        stem = f"trials/repeat-{repeat:02d}-{method}"
        validate_trial(trial, workers[stem + ".stdout.json"], errors[stem + ".stderr.txt"], tasks, environment, repeat, method)
    actual = derive_summary(tasks, trials, repeats)
    require(same(actual, retained), "derived summary differs, including scalar types")
    return actual


def _files(directory):
    require(directory.is_dir() and not directory.is_symlink(), "evidence directory must be a real directory")
    paths = list(directory.rglob("*"))
    require(not any(path.is_symlink() for path in paths), "evidence symlinks are not admitted")
    return {path.relative_to(directory).as_posix(): path for path in paths if path.is_file()}


def _snapshot(paths):
    snapshot = {}
    for name, path in paths.items():
        require(path.is_file() and not path.is_symlink(), "required evidence file: " + name)
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
        require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), "evidence changed while reading: " + name)
        snapshot[name] = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "mtime_ns": after.st_mtime_ns}
    return snapshot


def dependency_pins(root):
    pins = {}
    for line in (root / "requirements-symbolic.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        require(re.fullmatch(r"[A-Za-z0-9_-]+==[A-Za-z0-9_.+-]+", line) is not None, "exact symbolic dependency pin")
        name, version = line.split("==")
        require(name not in pins, "unique dependency pin")
        pins[name] = version
    require(set(pins) == {"dd", "astutils", "networkx", "ply", "setuptools"}, "complete symbolic dependency pins")
    return pins


def load_evidence(directory, root=ROOT):
    """Load and validate a retained campaign; never create a file or run workers."""
    directory, root = Path(directory).absolute(), Path(root).absolute()
    files = _files(directory)
    require(ROOT_FILES <= set(files), "required campaign root files")
    protected = {"campaign/" + name: path for name, path in files.items()}
    protected.update({name: root / name for name in (*SOURCE_PATHS, *ORIGIN_PATHS, "requirements-symbolic.txt")})
    before = _snapshot(protected)
    inputs, profiles, trials, retained, environment = (read(files[name]) for name in ("inputs.json.gz", "profiles.json.gz", "trials.json", "summary.json", "environment.json"))
    identities = {name: before[name]["sha256"] for name in SOURCE_PATHS}
    pins = dependency_pins(root)
    validate_environment(environment, identities, pins)
    tasks = prepare_tasks(inputs, profiles, source_tasks(root))
    workers = {name: read(path) for name, path in files.items() if name.endswith(".stdout.json")}
    errors = {name: path.read_bytes() for name, path in files.items() if name.endswith(".stderr.txt")}
    require(set(files) == ROOT_FILES | set(workers) | set(errors), "exact retained campaign file set")
    actual = validate_campaign(tasks, trials, retained, environment, workers, errors)
    after = _snapshot(protected)
    require(same(before, after) and set(_files(directory)) == set(files), "read-only audit changed or lost scientific evidence")
    report = {key: actual[key] for key in ("status", "tasks", "case_method_pairs", "repeats", "processes", "timed_task_records", "cohort_tasks", "methods")}
    report.update(complete_binding_profiles=sum(len(task["expected"]) for task in tasks),
                  campaign_files=len(files), historical_source_files=len(SOURCE_PATHS),
                  original_scientific_input_files=len(ORIGIN_PATHS),
                  bytes_and_modification_times_unchanged=True, scope=SCOPE)
    inventory = {name: {key: row[key] for key in ("bytes", "sha256")} for name, row in sorted(after.items())}
    return {"summary": report, "inventory": inventory, "tasks": tasks, "trials": trials,
            "retained": retained, "environment": environment, "workers": workers, "errors": errors,
            "identities": identities, "packages": pins}


def controls(evidence):
    """Malformed copies are rejection controls, never additional measurements."""
    tasks, environment = evidence["tasks"], evidence["environment"]
    base = evidence["trials"][0]
    results = []

    def expect(name, function, rejected):
        try:
            function()
        except EvidenceError as error:
            require(rejected, "positive control rejected: " + name + ": " + str(error))
            results.append({"name": name, "expected": "reject", "outcome": "reject", "reason": str(error)})
        else:
            require(not rejected, "malformed control accepted: " + name)
            results.append({"name": name, "expected": "accept", "outcome": "accept"})

    def trial_control(name, change, change_raw=False):
        trial = deepcopy(base)
        raw = deepcopy(evidence["workers"][base["stdout"]])
        change(raw if change_raw else trial)
        expect(name, lambda: validate_trial(trial, raw, b"", tasks, environment, 0, METHODS[0]), True)

    trial_control("empty raw worker object", lambda row: row.clear(), True)
    trial_control("missing raw records", lambda row: row.pop("records"), True)
    trial_control("undeclared raw field", lambda row: row.update(extra=True), True)
    trial_control("Boolean process return code", lambda row: row.update(exit_code=False))
    trial_control("floating process return code", lambda row: row.update(exit_code=0.0))
    trial_control("nonzero process return code", lambda row: row.update(exit_code=1))
    trial_control("Boolean repetition identifier", lambda row: row.update(repeat=False))
    trial_control("floating repetition identifier", lambda row: row.update(repeat=0.0))
    trial_control("Boolean process duration", lambda row: row.update(process_wall_ns=True))
    trial_control("impossibly short process duration", lambda row: row.update(process_wall_ns=1))
    trial_control("stdout path outside declared log", lambda row: row.update(stdout="../worker.json"))
    trial_control("wrong stderr identity", lambda row: row.update(stderr="trials/unrelated.stderr.txt"))

    def paired_control(name, change, index=0):
        trial = deepcopy(evidence["trials"][index])
        change(trial)
        raw = {key: deepcopy(trial[key]) for key in WORKER_FIELDS}
        original = evidence["trials"][index]
        expect(name, lambda: validate_trial(trial, raw, b"", tasks, environment, original["repeat"], original["method"]), True)

    paired_control("missing timed task", lambda row: row["records"].pop())
    paired_control("duplicated timed task", lambda row: row["records"].__setitem__(-1, deepcopy(row["records"][0])))
    paired_control("missing timing field", lambda row: row["records"][0].pop("diagnosis_cpu_ns"))
    paired_control("undeclared timing field", lambda row: row["records"][0].update(extra=0))
    paired_control("Boolean diagnosis time", lambda row: row["records"][0].update(diagnosis_wall_ns=True))
    paired_control("Boolean output count", lambda row: row["records"][0].update(bindings=True))
    paired_control("negative scientific counter", lambda row: row["records"][0].update(replay_steps=-1))
    paired_control("different complete output", lambda row: row["records"][0].update(output_sha256="0" * 64))
    paired_control("different output byte count", lambda row: row["records"][0].update(output_bytes=row["records"][0]["output_bytes"] + 1))
    paired_control("different family denominator", lambda row: row["records"][0].update(bindings=row["records"][0]["bindings"] + 1))
    paired_control("unchecked complete output", lambda row: row.update(complete_outputs_compared=1))
    paired_control("Boolean memory counter", lambda row: row.update(process_peak_rss_kib=True))
    paired_control("different worker Python metadata", lambda row: row.update(python="different runtime"))
    paired_control("different worker platform metadata", lambda row: row.update(platform="different platform"))
    paired_control("backend metadata on explicit method", lambda row: row.update(dd_package="0.6.0"))
    cudd_index = next(index for index, trial in enumerate(evidence["trials"]) if trial["method"] == "cudd")
    paired_control("missing CUDD package metadata", lambda row: row.update(dd_package=None), cudd_index)
    paired_control("different CUDD package metadata", lambda row: row.update(dd_package="0.0.0"), cudd_index)
    raw = evidence["workers"][base["stdout"]]
    expect("nonempty worker stderr", lambda: validate_trial(base, raw, b"warning\n", tasks, environment, 0, METHODS[0]), True)

    def campaign_control(name, key, value):
        values = {field: evidence[field] for field in ("tasks", "trials", "retained", "environment", "workers", "errors")}
        values[key] = value
        expect(name, lambda: validate_campaign(**values), True)

    campaign_control("missing method process", "trials", evidence["trials"][:-1])
    campaign_control("duplicate method process", "trials", [*evidence["trials"][:-1], evidence["trials"][0]])
    reordered = list(evidence["trials"])
    reordered[0], reordered[1] = reordered[1], reordered[0]
    campaign_control("changed acquisition rotation", "trials", reordered)
    campaign_control("missing raw worker file", "workers", {key: value for key, value in evidence["workers"].items() if key != base["stdout"]})
    campaign_control("extra raw worker file", "workers", {**evidence["workers"], "trials/extra.stdout.json": raw})
    retained = deepcopy(evidence["retained"])
    retained["records"][0]["methods"][METHODS[0]]["symbolic_nodes"]["min"] = False
    campaign_control("Boolean zero in derived summary", "retained", retained)
    retained = deepcopy(evidence["retained"])
    retained["records"][0]["methods"][METHODS[0]]["diagnosis_wall_ns"]["median"] += 1
    campaign_control("changed derived timing median", "retained", retained)
    env = deepcopy(environment)
    env["source_identities"].pop(SOURCE_PATHS[0])
    expect("missing historical source identity", lambda: validate_environment(env, evidence["identities"], evidence["packages"]), True)
    env = deepcopy(environment)
    env["campaign_sources_unchanged"] = 1
    expect("numeric campaign stability flag", lambda: validate_environment(env, evidence["identities"], evidence["packages"]), True)
    expect("duplicate JSON object key", lambda: decode(b'{"exit_code":1,"exit_code":0}'), True)
    expect("nonfinite JSON number", lambda: decode(b'{"time":NaN}'), True)
    expect("overflowed JSON number", lambda: decode(b'{"time":1e999}'), True)
    expect("unaltered complete worker", lambda: validate_trial(base, raw, b"", tasks, environment, 0, METHODS[0]), False)
    reordered_raw = dict(reversed(list(raw.items())))
    expect("JSON object key order is immaterial", lambda: validate_trial(base, reordered_raw, b"", tasks, environment, 0, METHODS[0]), False)
    expect("unaltered full campaign", lambda: validate_campaign(tasks, evidence["trials"], evidence["retained"], environment, evidence["workers"], evidence["errors"]), False)
    return {"status": "PASS", "kind": "in-memory malformed copies and positive admission controls",
            "scientific_measurements_added": 0, "rejection_controls": sum(row["expected"] == "reject" for row in results),
            "positive_controls": sum(row["expected"] == "accept" for row in results), "records": results}


def output_destination(path, results, root):
    """Refuse existing paths, symlink routing, and overlap with protected inputs."""
    path = path.absolute()
    require(not path.exists() and not path.is_symlink(), "fresh audit output directory required")
    require(path.parent.is_dir(), "audit output parent must already exist")
    require(all(not parent.is_symlink() for parent in (path.parent, *path.parents)), "audit output must not traverse symlinks")
    resolved = path.resolve()
    protected = [results.resolve(), *(root / name for name in (*SOURCE_PATHS, *ORIGIN_PATHS, "requirements-symbolic.txt"))]
    require(all(resolved != item and resolved not in item.parents and item not in resolved.parents for item in protected), "audit output overlaps scientific evidence")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results/symbolic-comparison")
    parser.add_argument("--output", type=Path, help="new directory for the audit report; omitted means no writes")
    parser.add_argument("--controls", action="store_true", help="also check malformed in-memory copies and positive controls")
    parser.add_argument("--verify-review", type=Path, help="compare the current read-only audit with a retained audit report")
    args = parser.parse_args(argv)
    try:
        require(not (args.output and args.verify_review), "choose output or verify-review")
        destination = output_destination(args.output, args.results, ROOT) if args.output else None
        evidence = load_evidence(args.results)
        result = {"summary.json": evidence["summary"], "inventory.json": evidence["inventory"]}
        if args.controls or args.verify_review:
            result["controls.json"] = controls(evidence)
        if args.verify_review:
            for name, value in result.items():
                require(same(read(args.verify_review / name), value), "retained review differs: " + name)
        if destination:
            destination.mkdir()
            for name, value in result.items():
                with (destination / name).open("x") as handle:
                    handle.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
        response = dict(evidence["summary"])
        if "controls.json" in result:
            response["controls"] = {key: result["controls.json"][key] for key in ("status", "rejection_controls", "positive_controls", "scientific_measurements_added")}
        if args.verify_review:
            response["retained_review_matches"] = True
        print(json.dumps(response, indent=2))
    except (EvidenceError, OSError, KeyError, TypeError, ValueError, OverflowError, RecursionError) as error:
        print("comparison evidence rejected: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
