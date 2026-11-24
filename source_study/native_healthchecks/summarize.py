"""Recompute retained scientific results from native records and exact source edits."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from . import contracts, outcomes, production, run
from .native import raw_store


def _admit_modules(document, receipt, arm, source_paths):
    command = receipt["command"]
    if type(command) is not list or not all(type(value) is str for value in command):
        raise ValueError("native module receipt has an invalid command")
    for flag in ("--source", "--arm"):
        if command.count(flag) != 1 or command.index(flag) + 1 >= len(command):
            raise ValueError("native module receipt has an ambiguous source route")
    source = PurePosixPath(command[command.index("--source") + 1])
    if command[command.index("--arm") + 1] != arm or source.name != arm or document["arm"] != arm:
        raise ValueError("native module receipt identifies a different source arm")
    if (document["original_models"] is not True or document["native_http_client"] is not True
            or document["source_imports_replaced"] is not False
            or document["selected_api_boundary"] is not True or document["full_service_deployment"] is not False):
        raise ValueError("native module acquisition declarations differ")
    expected = {}
    for path in source_paths:
        relative = PurePosixPath(path)
        if relative.suffix != ".py" or path == "hc/test.py" or "tests" in relative.parts:
            continue
        parts = relative.with_suffix("").parts
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        expected[name] = str(source / relative)
    if len(expected) != 27 or not contracts.typed_equal(document["imported_application_modules"], expected):
        raise ValueError("native module map is not the complete declared source mapping")


def verify(output):
    output = Path(output)
    evidence = run.source_identity()
    paths = [row["path"] for row in evidence["files"]]
    if len(paths) != len(set(paths)) or len(paths) != 34:
        raise ValueError("original source manifest must contain 34 unique files")
    if any(type(row["upstream_bytes"]) is not int for row in evidence["files"]):
        raise ValueError("original source byte counts must be integers")
    source_controls = run.read(output / "source-controls.json")
    if [row["arm"] for row in source_controls] != list(contracts.ARMS):
        raise ValueError("source control collection differs")
    for control in source_controls:
        arm = control["arm"]
        listed = [row["path"] for row in control["files"]]
        if len(listed) != len(set(listed)) or set(listed) != set(paths):
            raise ValueError("source control manifest is not the complete unique original file set")
        if control["current_complete_source_modules"] is not True or control["historical_deployment_executed"] is not False:
            raise ValueError("source control declarations differ")
        for row in control["files"]:
            raw = (output / "source-controls" / arm / row["path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != row["sha256"] or not contracts.typed_equal(len(raw), row["bytes"]):
                raise ValueError("executed source control bytes differ")
            expected = (run.ROOT / "source" / row["path"]).read_bytes()
            if arm != "original" and row["path"] == run.controls()[arm][0]:
                _, old, new, count = run.controls()[arm]
                if expected.decode().count(old) != count: raise ValueError("control anchor differs")
                expected = expected.decode().replace(old, new).encode()
            if raw != expected: raise ValueError("source control is not the declared exact edit")
    acquisition = run.read(output / "acquisition.json")
    if (acquisition["all_application_modules_imported_intact"] is not True
            or acquisition["observation_acquired_before_production_diagnosis"] is not True
            or acquisition["source_imports_replaced"] is not False):
        raise ValueError("native acquisition declarations differ")
    receipts = acquisition["runs"]
    if len(receipts) != len(contracts.ARMS):
        raise ValueError("native acquisition receipt count differs")
    arms = []
    for receipt in receipts:
        if type(receipt["returncode"]) is not int or receipt["returncode"] != 0:
            raise ValueError("native acquisition receipt is not successful")
        command = receipt["command"]
        if (type(command) is not list or not all(type(value) is str for value in command)
                or command.count("--arm") != 1 or command.index("--arm") + 1 >= len(command)):
            raise ValueError("native acquisition receipt has no unambiguous source arm")
        arms.append(command[command.index("--arm") + 1])
    if len(set(arms)) != len(arms) or set(arms) != set(contracts.ARMS):
        raise ValueError("native acquisition receipts do not cover each source arm")
    replays = run.read(output / "native-replay.json")
    if any(type(row["receipt"]["returncode"]) is not int or row["receipt"]["returncode"] != 0 for row in replays):
        raise ValueError("native replay receipt is not successful")
    upstream = run.read(output / "upstream-tests.json")
    match = re.search(r"Ran (\d+) tests", upstream["stderr"])
    if type(upstream["returncode"]) is not int or upstream["returncode"] != 0 or not match or "\nOK\n" not in upstream["stderr"]:
        raise ValueError("upstream native test receipt is not successful")
    for arm, receipt in zip(arms, receipts, strict=True):
        document = run.read(output / "native" / arm / "observations.json.gz")
        _admit_modules(document, receipt, arm, paths)
        if len(document["cases"]) != 24 or any(case["arm"] != arm for case in document["cases"]):
            raise ValueError("native source document has misrouted cases")
    declared = run.read(output / "protocol.json")
    if not contracts.typed_equal(declared["operations"], contracts.protocol()) or not contracts.typed_equal(declared["configurations"], contracts.configurations()) or not contracts.typed_equal(declared["callers"], contracts.CALLERS):
        raise ValueError("declared native protocol differs")
    if declared["shared_target_correspondence_family"] is not False:
        raise ValueError("declared native target family differs")
    reports = run.read(output / "profiles.json.gz")
    if len(reports) != 120: raise ValueError("production diagnostic case count differs")
    if any(type(row["case_index"]) is not int or not 0 <= row["case_index"] < len(reports) for row in replays):
        raise ValueError("invalid native replay case index")
    replay_map = {record["case_index"]: record for record in replays}
    if len(replay_map) != len(replays): raise ValueError("duplicate native replay")
    totals = Counter()
    sets = defaultdict(list)
    prefix_lengths = defaultdict(list)
    for index, case in enumerate(run.cases(output)):
        report = reports[index]
        key = (case["arm"], case["format"], case["api_version"], case["configuration"])
        if not contracts.typed_equal(key, (report["arm"], report["format"], report["api_version"], report["configuration"])):
            raise ValueError("diagnostic report routed to a different native configuration")
        validation = contracts.check_case(case)
        database = output / "native" / case["arm"] / case["sqlite_file"]
        if not contracts.typed_equal(raw_store(database), case["records"][-1]["after"]):
            raise ValueError("final physical SQLite file differs from the native observation")
        if not contracts.typed_equal(validation, report["validation"]): raise ValueError("retained contract results differ")
        expected_profiles = [production.diagnose(case, caller, mode) for caller in contracts.CALLERS for mode in ("complete", "http_status")]
        if production.canonical(expected_profiles) != production.canonical(report["profiles"]):
            raise ValueError("retained production profile or encoding differs")
        totals["native_cases"] += 1
        totals["native_operations"] += len(case["records"])
        totals["native_http_requests"] += sum(r["operation"]["kind"] == "http" for r in case["records"])
        totals["native_key_rotations"] += sum(r["operation"]["kind"] == "rotate" for r in case["records"])
        totals["native_sql_statements"] += sum(len(r["sql"]) for r in case["records"])
        for profile in report["profiles"]:
            group = (case["arm"], profile["caller"], profile["mode"], case["format"], case["api_version"])
            if profile["equivalent"]: sets[group].append(case["configuration"])
            else: sets.setdefault(group, [])
            totals["configuration_profile_results"] += 1
            totals["production_component_comparisons"] += sum(len(c["methods"]) for c in profile["components"])
            if case["configuration"] == "identity":
                prefix_lengths[(case["arm"], profile["caller"], profile["mode"])].append(profile["length"])
        witnesses = [p for p in report["profiles"] if not p["equivalent"]]
        if witnesses:
            replay = replay_map.get(index)
            if replay is None: raise ValueError("native first-prefix replay is missing")
            length = max(p["length"] for p in witnesses)
            if not contracts.typed_equal(replay["collected_prefix_length"], length): raise ValueError("replay prefix length differs")
            replay_document = run.read(output / replay["native_record"])
            _admit_modules(replay_document, replay["receipt"], case["arm"], paths)
            if len(replay_document["cases"]) != 1:
                raise ValueError("native replay document case count differs")
            replay_case = replay_document["cases"][0]
            if not contracts.typed_equal((replay_case["arm"], replay_case["format"], replay_case["api_version"], replay_case["configuration"]), key):
                raise ValueError("replay used a different actual configuration")
            contracts.check_case(replay_case, required_length=length)
            replay_database = (output / replay["native_record"]).parent / replay_case["sqlite_file"]
            if not contracts.typed_equal(raw_store(replay_database), replay_case["records"][-1]["after"]):
                raise ValueError("replay SQLite file differs from the final replay observation")
            wanted_checks = []
            for witness in witnesses:
                actual = outcomes.independent_profile(replay_case, witness["caller"], witness["mode"], replay_length=length)
                if actual["equivalent"] is not False or not contracts.typed_equal(actual["length"], witness["length"]):
                    raise ValueError("native replay did not reproduce the first differing prefix")
                wanted_checks.append(dict(caller=witness["caller"], mode=witness["mode"], length=witness["length"], indices=witness["indices"]))
            if not contracts.typed_equal(replay["checked_witnesses"], wanted_checks): raise ValueError("replay certificate differs")
            totals["native_replay_cases"] += 1
            totals["native_replayed_witnesses"] += len(wanted_checks)
            totals["native_replay_operations"] += length
            totals["native_replay_http_requests"] += sum(row["operation"]["kind"] == "http" for row in replay_case["records"])
        elif index in replay_map:
            raise ValueError("unnecessary replay was labelled a negative witness")
    aggregated = []
    for arm in contracts.ARMS:
        for caller in contracts.CALLERS:
            for mode in ("complete", "http_status"):
                rows = [sorted(sets[(arm, caller, mode, fmt, api)]) for fmt in contracts.FORMATS for api in contracts.API_VERSIONS]
                if any(not contracts.typed_equal(row, rows[0]) for row in rows[1:]): raise ValueError("format/API strata have different acceptance sets; report separately")
                lengths = prefix_lengths[(arm, caller, mode)]
                if any(not contracts.typed_equal(value, lengths[0]) for value in lengths[1:]): raise ValueError("format/API strata have different first-prefix lengths; report separately")
                aggregated.append(dict(arm=arm, caller=caller, observation=mode, accepted_configurations=rows[0], identity_first_difference=lengths[0], repeated_strata=len(rows)))
    totals["upstream_tests"] = int(match.group(1))
    return dict(status="PASS", **dict(totals), source_files=len(evidence["files"]), native_source_arms=len(contracts.ARMS),
        applications=1, initial_key_formats=len(contracts.FORMATS), api_versions=len(contracts.API_VERSIONS), fixed_route_configurations=len(contracts.configurations()),
        cases_per_arm=24, selected_modules_imported_complete=True, source_imports_replaced=False,
        shared_target_correspondence_family=False, complete_physical_reachability_claim=False,
        observation="Complete JSON objects, exact non-JSON error bodies, all response headers and cookies, native identity handoff, selected persisted rows; Flip wall-clock literals are retained raw but projected to presence and processing relation.",
        shortest_scope="Prefixes of the declared finite caller words only; consecutive encoding blocks preserve the already executed application state.",
        profiles=aggregated)
