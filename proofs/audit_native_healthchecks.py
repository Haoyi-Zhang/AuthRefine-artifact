#!/usr/bin/env python3
"""Read-only review of the retained native Healthchecks observation chain.

The audit opens retained SQLite files in read-only mode, decodes the saved core
inputs and replays, and repeats the concrete observation controls from review.
It does not run Django, acquire new application data, or rewrite scientific
records. Optional review output requires a new directory outside --results.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from copy import deepcopy
import difflib
import gzip
import hashlib
import hmac
import itertools
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import sys

sys.dont_write_bytecode = True
ARTIFACT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT))
from source_study.native_healthchecks import contracts, outcomes, production

PACKAGE = ARTIFACT / "source_study/native_healthchecks"
TABLES = {"projects": "accounts_project", "checks": "api_check", "flips": "api_flip",
          "profiles": "accounts_profile", "channels": "api_channel"}
IDENTITY_LENGTHS = {"original": (None, None), "omit_readonly_context": (1, None),
                    "wrong_project_context": (1, 2), "omit_pause_persistence": (15, 18),
                    "reject_readonly_get": (1, 1)}
CONTROL_EDITS = {
    "omit_readonly_context": ("hc/api/views.py", "check.to_dict(readonly=request.readonly, v=request.v)", "check.to_dict(v=request.v)", 3),
    "wrong_project_context": ("hc/api/decorators.py", "        request.project = project", "        request.project = Project.objects.order_by(\"id\").first()", 2),
    "omit_pause_persistence": ("hc/api/views.py", "    check.save(update_fields=(\"status\", \"last_start\", \"alert_after\"))", "    pass", 1),
    "reject_readonly_get": ("hc/api/views.py", "@authorize_read\ndef get_check(", "@authorize\ndef get_check(", 1),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def contained(root, relative):
    relative = Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts, "nonlocal retained path")
    result = (root / relative).resolve()
    require(result.is_relative_to(root.resolve()), "retained path escapes its supplied root")
    return result


def argument(receipt, flag):
    command = receipt["command"]
    require(type(command) is list and all(type(part) is str for part in command),
            "invalid acquisition command")
    require(command.count(flag) == 1, "ambiguous acquisition argument: " + flag)
    index = command.index(flag)
    require(index + 1 < len(command), "missing acquisition argument: " + flag)
    return command[index + 1]


def key(case):
    return tuple(case[field] for field in ("arm", "format", "api_version", "configuration"))


def module_routes(document, receipt, results, arm):
    """Recorded absolute paths identify ancestry; only package-relative files open."""
    require(type(receipt["returncode"]) is int and receipt["returncode"] == 0
            and argument(receipt, "--arm") == arm, "native subprocess receipt")
    source = PurePosixPath(argument(receipt, "--source"))
    require(source.name == arm, "source receipt assigned to another arm")
    require(document["original_models"] is True and document["native_http_client"] is True
            and document["source_imports_replaced"] is False
            and document["selected_api_boundary"] is True
            and document["full_service_deployment"] is False, "native acquisition flags")
    imported = document["imported_application_modules"]
    expected = {}
    for row in read(PACKAGE / "source-evidence.json")["files"]:
        relative = PurePosixPath(row["path"])
        if relative.suffix != ".py" or row["path"] == "hc/test.py" or "tests" in relative.parts:
            continue
        parts = relative.with_suffix("").parts
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        expected[name] = str(source / relative)
    require(len(expected) == 27 and contracts.typed_equal(imported, expected),
            "application module map is not the complete declared source mapping")
    for name, path in imported.items():
        require(name == "hc" or name.startswith("hc."), "unexpected application module name")
        try:
            relative = PurePosixPath(path).relative_to(source)
        except ValueError as error:
            raise ValueError("application module escaped its recorded source root") from error
        require(contained(results / "source-controls" / arm, str(relative)).is_file(),
                "imported application module is absent from delivered source")
    return len(imported)


def audit_sources(results):
    acquisition = read(results / "acquisition.json")
    require(acquisition["all_application_modules_imported_intact"] is True
            and acquisition["observation_acquired_before_production_diagnosis"] is True
            and acquisition["source_imports_replaced"] is False, "source acquisition declarations")
    require(len(acquisition["runs"]) == len(contracts.ARMS), "source acquisition run count")
    require(all(type(row["returncode"]) is int and row["returncode"] == 0
                for row in acquisition["runs"]), "unsuccessful source acquisition receipt")
    receipts = {argument(row, "--arm"): row for row in acquisition["runs"]}
    require(set(receipts) == set(contracts.ARMS), "source acquisition arms")
    manifest = read(results / "source-controls.json")
    require([row["arm"] for row in manifest] == list(contracts.ARMS), "source control manifest arms")
    evidence = read(PACKAGE / "source-evidence.json")
    paths = [row["path"] for row in evidence["files"]]
    require(len(paths) == len(set(paths)) == 34, "original source manifest must contain 34 unique files")
    for row in evidence["files"]:
        raw = contained(PACKAGE / "source", row["path"]).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(contracts.typed_equal(len(raw), row["upstream_bytes"]) and blob == row["upstream_git_blob"],
                "delivered original module differs from its source evidence")
    checked = 0
    changes = {}
    for control in manifest:
        arm = control["arm"]
        require([row["path"] for row in control["files"]] == paths, "source manifest file coverage")
        require(control["current_complete_source_modules"] is True
                and control["historical_deployment_executed"] is False, "source control declarations")
        changed = []
        for row in control["files"]:
            raw = contained(results / "source-controls" / arm, row["path"]).read_bytes()
            require(contracts.typed_equal(len(raw), row["bytes"]) and hashlib.sha256(raw).hexdigest() == row["sha256"],
                    "retained source control bytes differ")
            original = contained(PACKAGE / "source", row["path"]).read_bytes()
            expected = original
            if arm != "original" and row["path"] == CONTROL_EDITS[arm][0]:
                _, old, new, occurrences = CONTROL_EDITS[arm]
                require(original.decode().count(old) == occurrences, "source control anchor count")
                expected = original.decode().replace(old, new).encode()
            require(raw == expected, "source control is not its independently declared edit")
            if raw != original:
                changed.append(row["path"])
            checked += 1
        if arm == "original":
            require(not changed and not control["patch"], "original source was modified")
        else:
            require(changed == [CONTROL_EDITS[arm][0]], "source control modified another file")
            path = changed[0]
            before = contained(PACKAGE / "source", path).read_text()
            after = contained(results / "source-controls" / arm, path).read_text()
            patch = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                               fromfile="original/" + path, tofile=arm + "/" + path))
            require(patch == control["patch"], "retained source diff differs")
        changes[arm] = changed
    return receipts, {"source_files_checked": checked, "source_changes": changes}


def sqlite_snapshot(path):
    # mode=ro also rejects a missing file instead of creating an empty database.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as database:
        database.row_factory = sqlite3.Row
        return {name: [dict(row) for row in database.execute("SELECT * FROM " + table + " ORDER BY id")]
                for name, table in TABLES.items()}


def native_cases(results, receipts):
    protocol = read(results / "protocol.json")
    require(contracts.typed_equal(protocol["operations"], contracts.protocol())
            and contracts.typed_equal(protocol["callers"], contracts.CALLERS)
            and contracts.typed_equal(protocol["configurations"], contracts.configurations()), "retained caller declaration")
    require(protocol["shared_target_correspondence_family"] is False, "incorrect common-target family claim")
    cases, rows, counts, modules = {}, [], Counter(), {}
    check_codes, channel_codes, hashed_keys, rotated_keys = set(), set(), set(), set()
    for arm in contracts.ARMS:
        document = read(results / "native" / arm / "observations.json.gz")
        require(document["arm"] == arm and len(document["cases"]) == 24, "native source-arm cases")
        modules[arm] = module_routes(document, receipts[arm], results, arm)
        for case in document["cases"]:
            case_key = key(case)
            require(case_key not in cases and case["arm"] == arm, "duplicate or misrouted native case")
            require(len(case["records"]) == 37
                    and contracts.typed_equal([record["operation"] for record in case["records"]], protocol["operations"]),
                    "incomplete native caller word")
            cases[case_key] = case
            previous = case["initial"]
            keys = {owner + "_" + role: case["owners"][owner][role]
                    for owner in ("alice", "bob") for role in ("rw", "ro")}
            if case["format"] == "hashed":
                require(not hashed_keys.intersection(keys.values()), "reused hashed fixture credentials")
                hashed_keys.update(keys.values())
            for owner in case["owners"].values():
                require(owner["check_uuid"] not in check_codes and owner["channel_uuid"] not in channel_codes,
                        "native fixtures reused a generated identity")
                check_codes.add(owner["check_uuid"])
                channel_codes.add(owner["channel_uuid"])
            for record in case["records"]:
                require(contracts.typed_equal(record["before"], previous), "discontinuous physical native prefix")
                previous = record["after"]
                op = record["operation"]
                counts["native_operations"] += 1
                counts["native_sql_statements"] += len(record["sql"])
                if op["kind"] == "http":
                    counts["native_http_requests"] += 1
                    body, headers = record["response_text"], record["response_headers"]
                    require(int(headers["Content-Length"]) == len(body.encode()), "retained body byte count")
                    parsed = json.loads(body) if headers["Content-Type"].startswith("application/json") else None
                    require(contracts.typed_equal(parsed, record["response"]), "parsed response differs from raw wire body")
                    require(contracts.typed_equal(record["request"], contracts.request_spec(case, op, keys)), "actual credential routing")
                else:
                    counts["native_key_rotations"] += 1
                    slot = protocol["configurations"][case["configuration"]][op["owner"] + "_" + op["role"]]
                    owner, role = slot.split("_")
                    column = "api_key" if role == "rw" else "api_key_readonly"
                    require(record["producer_project"] == owner and record["producer_role"] == role
                            and record["producer_class"] == "hc.accounts.models.Project", "actual native key producer")
                    token = record["returned_key"]
                    require(len(token) == 32 and token.startswith("hcw_" if role == "rw" else "hcr_")
                            and token != keys[slot] and token not in rotated_keys, "native replacement key")
                    rotated_keys.add(token)
                    wanted = deepcopy(record["before"]["projects"])
                    project = next(row for row in wanted if row["id"] == case["owners"][owner]["project_id"])
                    project[column] = token[4:12] + "." + hmac.digest(
                        b"owned-native-healthchecks-test-key", token.encode(), "sha256").hex()
                    require(contracts.typed_equal(record["after"]["projects"], wanted), "native rotation changed another physical slot")
                    keys["old_" + slot], keys[slot] = keys[slot], token
            database = contained(results / "native" / arm, case["sqlite_file"])
            require(contracts.typed_equal(sqlite_snapshot(database), case["records"][-1]["after"]), "final SQLite rows differ from record")
            counts["sqlite_final_snapshots_checked"] += 1
            checked = contracts.check_case(case)
            rich = outcomes.independent_profile(case, "lifecycle", "complete")
            status = outcomes.independent_profile(case, "lifecycle", "http_status")
            if case["configuration"] == "identity":
                require(contracts.typed_equal((rich["length"], status["length"]), IDENTITY_LENGTHS[arm]), "identity source-control first event")
                if arm == "original":
                    require(not checked["disagreements"], "unmodified identity contract discrepancy")
                    counts["unmodified_identity_zero_disagreements"] += 1
                else:
                    first = case["records"][rich["length"] - 1]
                    if arm == "omit_readonly_context":
                        require(first["http_status"] == 200 and first["request_readonly"] is True
                                and "uuid" in first["response"], "serializer omission absent from raw response")
                    elif arm == "wrong_project_context":
                        require(first["http_status"] == 200
                                and first["request_project_id"] == case["owners"]["alice"]["project_id"]
                                and first["manager_result_is_request_project"] is False, "first object-handoff failure")
                        second = case["records"][1]
                        require(second["http_status"] == 403
                                and second["request_project_id"] != case["owners"]["bob"]["project_id"], "second project attribution failure")
                    elif arm == "omit_pause_persistence":
                        stored = next(row for row in first["after"]["checks"] if row["id"] == case["owners"]["alice"]["check_id"])
                        require(first["http_status"] == 200 and first["response"]["status"] == "paused"
                                and stored["status"] == "new", "pause persistence failure absent from physical rows")
                    else:
                        require(contracts.typed_equal(first["http_status"], 401)
                                and contracts.typed_equal(first["source_manager_returns"], [None]), "readonly rejection source event")
            rows.append({"case": list(case_key), "rich_first_length": rich["length"],
                         "http_first_length": status["length"], "disagreement_events": len(checked["disagreements"])})
    expected = set(itertools.product(contracts.ARMS, contracts.FORMATS, contracts.API_VERSIONS, contracts.configurations()))
    require(len(cases) == 120 and set(cases) == expected, "complete native configuration grid")
    counts["native_cases"] = len(cases)
    return cases, check_codes, {"counts": dict(counts), "imported_application_modules_per_arm": modules,
        "distinct_initial_check_codes": len(check_codes), "distinct_initial_channel_codes": len(channel_codes),
        "distinct_hashed_initial_keys": len(hashed_keys), "distinct_rotated_keys": len(rotated_keys), "cases": rows}


def projected(rows, mode):
    require(mode in ("complete", "http_status"), "undeclared observation")
    return rows if mode == "complete" else [{"http_status": row.get("http_status")} for row in rows]


def audit_profiles(results, cases, original_codes):
    reports = read(results / "profiles.json.gz")
    require(len(reports) == 120 and {key(report) for report in reports} == set(cases), "diagnostic case coverage")
    counts, matching, profile_rows = Counter(), Counter(), []
    for report in reports:
        case_key = key(report)
        case = cases[case_key]
        require(contracts.typed_equal(key(case), case_key), "diagnostic configuration types differ")
        require(contracts.typed_equal(report["validation"], contracts.check_case(case)), "retained contract checks differ")
        expected_all, actual_all = outcomes.vectors(case)
        require(len(report["profiles"]) == 6
                and {(p["caller"], p["mode"]) for p in report["profiles"]}
                == set(itertools.product(contracts.CALLERS, ("complete", "http_status"))), "caller/observation profile coverage")
        for profile in report["profiles"]:
            counts["configuration_profile_results"] += 1
            limit = contracts.CALLERS[profile["caller"]]
            require(contracts.typed_equal(profile["admitted_operations"], limit)
                    and profile["prefix_only"] is True
                    and profile["configuration"] == case["configuration"], "declared profile boundary differs")
            expected = projected(expected_all[:limit], profile["mode"])
            actual = projected(actual_all[:limit], profile["mode"])
            first = next((i + 1 for i, (left, right) in enumerate(zip(expected, actual, strict=True)) if not contracts.typed_equal(left, right)), None)
            require(contracts.typed_equal(
                (profile["length"], profile["equivalent"], profile["indices"]),
                (first, first is None, [] if first is None else list(range(first)))), "global fixed-prefix result")
            require(contracts.typed_equal([row["start"] for row in profile["components"]], list(range(0, limit, 15))), "complete encoding block coverage")
            for component in profile["components"]:
                start = component["start"]
                end = min(start + 15, limit)
                inputs = component["inputs"]
                book, machine, policy, caller = (inputs[name] for name in ("codebook", "machine", "policy", "caller"))
                size = end - start
                require(book[0] is None and len(book) == len({json.dumps(v, sort_keys=True) for v in book}), "injective observation codebook")
                require(contracts.typed_equal((policy["aliases"], policy["roles"], policy["members"]), ([], [], []))
                        and len(caller["transitions"]) <= 16 and len(policy["state"]) <= 7, "core capture envelope")
                require(contracts.typed_equal((machine["initial"], caller["initial"], machine["observations"][0]), (0, 0, 0))
                        and all(value is False for _, value in policy["state"]), "capture initial sentinel")
                require(all(type(code) is int and 0 <= code < len(book) for code in machine["observations"]),
                        "invalid target observation code")
                require(contracts.typed_equal([book[code] for code in machine["observations"][1:]], actual[start:end]), "target codes differ from actual native vectors")
                require(len(policy["rules"]) == len(machine["alphabet"]) == size, "capture alphabet/rule count")
                require(contracts.typed_equal(machine["transitions"], [[(["allow", q + 1] if q == i else None) for i in range(size)] for q in range(size + 1)])
                        and contracts.typed_equal(caller["transitions"], [[(q + 1 if q == i else None) for i in range(size)] for q in range(size + 1)]), "capture target/caller prefix language")
                decoded = []
                positions = {name: i for i, (name, _) in enumerate(policy["state"])}
                require(len(positions) == len(policy["state"]), "duplicate capture state bit")
                for i, rule in enumerate(policy["rules"]):
                    require(rule["decision"] == "allow"
                            and contracts.typed_equal(rule["guard"], [{"field": "principal", "name": machine["alphabet"][i][0], "negated": False}]), "capture constant-output guard")
                    require(len(rule["updates"]) == len(positions)
                            and {update["name"] for update in rule["updates"]} == set(positions)
                            and all(type(update["value"]) is bool for update in rule["updates"]), "complete capture state assignment")
                    value = sum(1 << positions[update["name"]] for update in rule["updates"] if update["value"])
                    require(value < len(book), "invalid source observation code")
                    decoded.append(book[value])
                require(contracts.typed_equal(decoded, expected[start:end]), "source codes differ from independent reference vectors")
                boundary = case["initial"] if start == 0 else case["records"][start - 1]["after"]
                require(component["application_boundary_continuity_checked"] is True
                        and contracts.typed_equal(component["application_boundary_before"], boundary), "physical block boundary reset")
                local = next((i + 1 for i, (left, right) in enumerate(zip(expected[start:end], actual[start:end], strict=True)) if not contracts.typed_equal(left, right)), None)
                require(set(component["methods"]) == {"protocol-scan", "protocol-grouped"}, "production comparator coverage")
                for result in component["methods"].values():
                    counts["production_component_comparisons"] += 1
                    require(contracts.typed_equal(result["bindings"], 1) and len(result["profiles"]) == 1, "capture family is not a singleton")
                    row = result["profiles"][0]
                    require(contracts.typed_equal((row["binding"], row["equivalent"], row["length"]), ({}, local is None, local)), "production local profile")
                    if local is None:
                        require(row["trace"] is None and row["indices"] is None, "matching component has a negative trace")
                    else:
                        require(contracts.typed_equal(row["indices"], list(range(local))) and len(row["trace"]) == local, "component shortest word")
                        for i, step in enumerate(row["trace"]):
                            require(all(type(code) is int and 0 <= code < len(book)
                                        for code in (step["source"][1], step["target"][1])), "invalid replay observation code")
                            require(contracts.typed_equal(book[step["source"][1]], expected[start + i])
                                    and contracts.typed_equal(book[step["target"][1]], actual[start + i]), "replay decoding differs from native/reference records")
                            require(step["source"][0] == step["target"][0] == "allow"
                                    and contracts.typed_equal((step["request"], step["binding"], step["compared_equal"]),
                                                              (machine["alphabet"][i], {}, i < local - 1)), "capture replay or proper-prefix agreement")
                            counts["decoded_core_replay_rows"] += 1
            matching[(case_key[0], profile["caller"], profile["mode"])] += int(profile["equivalent"])
            profile_rows.append({"case": list(case_key), "caller": profile["caller"], "mode": profile["mode"], "first_length": first})
    manifest = read(results / "native-replay.json")
    require(all(type(row["case_index"]) is int and 0 <= row["case_index"] < len(reports) for row in manifest),
            "invalid native prefix replay case index")
    require(len({row["case_index"] for row in manifest}) == len(manifest), "duplicate native prefix replay")
    fresh_codes = set()
    for replay in manifest:
        report = reports[replay["case_index"]]
        case_key = key(report)
        failed = [p for p in report["profiles"] if not p["equivalent"]]
        require(failed, "negative replay has no negative profile")
        limit = max(p["length"] for p in failed)
        require(contracts.typed_equal(replay["collected_prefix_length"], limit), "fresh replay length")
        document = read(contained(results, replay["native_record"]))
        require(len(document["cases"]) == 1, "fresh replay case count")
        module_routes(document, replay["receipt"], results, case_key[0])
        case = document["cases"][0]
        require(contracts.typed_equal(key(case), case_key) and len(case["records"]) == limit, "fresh replay configuration")
        require(int(argument(replay["receipt"], "--limit")) == limit, "replay subprocess prefix limit")
        contracts.check_case(case, required_length=limit)
        database = contained(contained(results, replay["native_record"]).parent, case["sqlite_file"])
        require(contracts.typed_equal(sqlite_snapshot(database), case["records"][-1]["after"]),
                "fresh replay SQLite rows differ from record")
        checked = []
        for witness in failed:
            actual = outcomes.independent_profile(case, witness["caller"], witness["mode"], replay_length=limit)
            require(actual["equivalent"] is False and contracts.typed_equal(actual["length"], witness["length"]), "fresh native prefix did not reproduce the failure")
            checked.append({name: witness[name] for name in ("caller", "mode", "length", "indices")})
        require(contracts.typed_equal(replay["checked_witnesses"], checked), "retained native replay certificate")
        for owner in case["owners"].values():
            require(owner["check_uuid"] not in original_codes | fresh_codes, "fresh replay reused a primary fixture identity")
            fresh_codes.add(owner["check_uuid"])
        counts["native_replay_cases"] += 1
        counts["native_replay_operations"] += len(case["records"])
        counts["native_replay_http_requests"] += sum(row["operation"]["kind"] == "http" for row in case["records"])
        counts["negative_witnesses_reproduced"] += len(failed)
    require(len(manifest) == sum(any(not p["equivalent"] for p in report["profiles"]) for report in reports), "native negative replay coverage")
    upstream = read(results / "upstream-tests.json")
    found = re.search(r"Ran (\d+) tests", upstream["stderr"])
    require(type(upstream["returncode"]) is int and upstream["returncode"] == 0
            and "\nOK\n" in upstream["stderr"] and found, "upstream test receipt")
    counts["upstream_tests"] = int(found.group(1))
    return {"counts": dict(counts), "fresh_replay_check_codes": len(fresh_codes), "profiles": profile_rows,
            "matching_profiles": [{"arm": k[0], "caller": k[1], "mode": k[2], "matching_of_24": value}
                                  for k, value in sorted(matching.items())]}


def observation_controls(original):
    """Repeat the specific review regressions; these are not native acquisitions."""
    checks = []

    def record(case, name, index):
        checked = contracts.check_case(case)
        direct = outcomes.independent_profile(case, "lifecycle", "complete")
        produced = production.diagnose(case, "lifecycle", "complete")
        require(checked["first_difference"]["index"] == index
                and direct["length"] == produced["length"] == index + 1, "review control escaped: " + name)
        checks.append({"control": name, "first_event": index + 1,
                       "fields": checked["first_difference"]["fields"]})

    def body(row, value):
        row["response"] = value
        row["response_text"] = json.dumps(value)
        row["response_headers"]["Content-Length"] = str(len(row["response_text"].encode()))

    case = deepcopy(original)
    body(case["records"][10], {"error": "accepted and leaked a credential"})
    record(case, "changed JSON error body", 10)
    case = deepcopy(original)
    case["records"][0]["response"]["timeout"] = 1
    body(case["records"][0], case["records"][0]["response"])
    record(case, "changed previously omitted response field", 0)
    case = deepcopy(original)
    case["records"][0]["source_manager_returns"] = [{"native_class": "hc.accounts.models.Project", "project_id": case["owners"]["bob"]["project_id"]}]
    case["records"][0]["manager_result_is_request_project"] = False
    record(case, "wrong manager-to-request object handoff", 0)
    case = deepcopy(original)
    for index, row in enumerate(case["records"]):
        for side in ("before", "after"):
            if index > 29 or (index == 29 and side == "after"):
                project = next(p for p in row[side]["projects"] if p["id"] == case["owners"]["bob"]["project_id"])
                project["api_key_readonly"] = "UNINTENDED-OTHER-PROJECT-KEY-LOSS"
    record(case, "rotation corrupts another credential slot", 29)
    case = deepcopy(original)
    case["records"][20]["response_headers"]["Access-Control-Allow-Origin"] = "http://unexpected.example"
    record(case, "wrong preflight response metadata", 20)
    case = deepcopy(original)
    case["records"][10]["response_cookies"] = {"credential": "credential=unexpected; Path=/"}
    record(case, "unexpected error response cookie", 10)
    case = deepcopy(original)
    case["records"][9]["response_text"] = "wrong 404 detail"
    case["records"][9]["response_headers"]["Content-Length"] = str(len(case["records"][9]["response_text"].encode()))
    record(case, "changed non-JSON error body", 9)
    first_lengths = []
    for index, row in enumerate(original["records"]):
        case = deepcopy(original)
        if row["operation"]["kind"] == "http":
            case["records"][index]["http_status"] = 418
        else:
            case["records"][index]["producer_class"] = "wrong.native.Project"
        produced = production.diagnose(case, "lifecycle", "complete")
        require(produced["length"] == index + 1, "eventwise first failure crossed a block boundary")
        first_lengths.append(produced["length"])
    case = deepcopy(original)
    for row in case["records"]:
        if row["operation"]["kind"] == "http" and "Access-Control-Allow-Methods" in row["response_headers"]:
            parts = row["response_headers"]["Access-Control-Allow-Methods"].split(", ")
            row["response_headers"]["Access-Control-Allow-Methods"] = ", ".join(reversed(parts))
    require(not contracts.check_case(case)["disagreements"]
            and production.diagnose(case, "lifecycle", "complete")["equivalent"], "declared CORS method-order normalization")
    return {"status": "passed", "controls": checks, "eventwise_first_failure_lengths": first_lengths,
            "cors_method_order_preserves_equivalence": True, "new_native_executions": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="optional new directory for review results; never an existing directory")
    args = parser.parse_args()
    results = args.results.resolve()
    require(results.is_dir(), "retained result directory is absent")
    output = args.output.resolve() if args.output is not None else None
    if output is not None:
        require(not output.exists() and not output.is_relative_to(results),
                "review output must be a new directory outside the scientific records")
    receipts, sources = audit_sources(results)
    cases, identities, native = native_cases(results, receipts)
    profiles = audit_profiles(results, cases, identities)
    controls = observation_controls(cases[("original", "legacy", 1, "identity")])
    counts = {**native["counts"], **profiles["counts"]}
    retained = read(results / "summary.json")
    for field in ("native_cases", "native_operations", "native_http_requests", "native_key_rotations",
                  "native_sql_statements", "configuration_profile_results", "production_component_comparisons",
                  "native_replay_cases", "native_replay_operations", "native_replay_http_requests", "upstream_tests"):
        require(contracts.typed_equal(retained[field], counts[field]), "retained scientific summary differs: " + field)
    summary = {"status": "passed", **counts, "source_files_checked": sources["source_files_checked"],
               "observation_controls": len(controls["controls"]),
               "event_positions_checked": len(controls["eventwise_first_failure_lengths"]),
               "new_native_executions": 0, "open_blocking_findings": [],
               "shortest_scope": "Prefixes of each declared finite caller word; separately acquired configuration-specific targets.",
               "project_handoff_interpretation": "The replaced-Project control first changes ORM-instance handoff at event 1; wrong project attribution and HTTP status first differ at event 2."}
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
        for name, document in (("summary.json", summary), ("source-review.json", sources),
                               ("native-review.json", native), ("profile-review.json", profiles),
                               ("observation-controls.json", controls)):
            (output / name).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
