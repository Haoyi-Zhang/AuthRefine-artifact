#!/usr/bin/env python3
"""Acquire or verify complete identity-observation witnesses on native sessions.

From artifact/, --acquire --results /fresh/path executes the pinned native
methods and writes a separate study. Without --acquire this command is a
read-only check and requires only the standard library. Existing session
timings and their ordinary decision/presence profiles are never rewritten.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, deque
import gzip
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ART = Path(__file__).resolve().parents[2]
for directory in (ART, ART / "src"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from source_study.session_correspondence import fixtures, oracle
from source_study.session_correspondence.observation_contract import (
    check_graph, check_record, credential_arguments, native_replay_rows,
    propose_bijections, require, selected_map, summarize_profiles)

CALLERS = ("unrestricted", "lookup-only", "one-removal")
TOTAL_METHODS = ("per-binding-product", "per-binding-target", "shared-target", "support-indexed")
SOURCE = "source_study/source/h19/after/piccolo_api/session_auth/tables.py"
SELECTED_METHODS = ["SessionsBase.get_user_id", "SessionsBase.remove_session"]
CONTROL_ARM = "omit-delete: an introduced control that suppresses the selected method's deletion statement"


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def write(path, value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(data, mtime=0))
    else:
        path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def source_cases(source_results):
    cases = read(source_results / "inputs.json.gz")
    native = {row["sessions"]: row for row in read(source_results / "native-observations.json.gz")}
    require(len(cases) == 10 and {(row["sessions"], row["arm"]) for row in cases} ==
            {(size, arm) for size in range(2, 7) for arm in ("baseline", "omit-delete")},
            "observation study requires the declared five-size baseline/control cohort")
    return cases, native


def identity_profiles(case, graph):
    selected = selected_map(graph)
    return {caller: [oracle.profile(case["sessions"], case["machine"], binding, case["callers"][caller], selected)
                     for binding in case["family"]] for caller in CALLERS}


def profile_words(profiles):
    return sorted({tuple(row["indices"]) for records in profiles.values() for row in records if not row["equivalent"]},
                  key=lambda word: (len(word), word))


async def collect_duplicate():
    """Acquire the real database's reachable graph with two equal token values."""
    from source_study.session_correspondence.native import Sessions
    rows = fixtures.rows(2)
    rows[1]["token"] = rows[0]["token"]

    class StoredRowsSession(Sessions):
        async def reset(self, fixture_rows=None):
            return await super().reset(rows if fixture_rows is None else fixture_rows)

    session = StoredRowsSession(2)
    try:
        await session.initialize()
        initial_rows = fixtures.serialized_rows(await session.snapshot())
        schema = {"token_unique": session.table.token._meta.unique,
                  "token_nullable": session.table.token._meta.null,
                  "inserted_rows": len(initial_rows)}
        requests = fixtures.alphabet(2)
        paths, waiting, edges = {3: []}, deque([3]), []
        prefix_operations = 0
        while waiting:
            state = waiting.popleft()
            for index, request in enumerate(requests):
                await session.reset()
                prefix = [await session.invoke(requests[previous]) for previous in paths[state]]
                observed = await session.invoke(request)
                require(observed["before_state"] == state, "duplicate-token prefix reached another store")
                edges.append({"from_state": state, "input_index": index, "prefix": list(paths[state]),
                              "prefix_observations": prefix, "observation": observed})
                prefix_operations += len(prefix)
                following = observed["after_state"]
                if following not in paths:
                    paths[following] = paths[state] + [index]
                    waiting.append(following)
        states = list(paths)
        transitions = [[None] * len(requests) for _ in states]
        for edge in edges:
            observed = edge["observation"]
            transitions[states.index(edge["from_state"])][edge["input_index"]] = [
                observed["decision"], states.index(observed["after_state"])]
        graph = {"states": states, "edges": edges, "prefix_operations": prefix_operations,
                 "source_operations": len(edges) + prefix_operations,
                 "machine": {"state_names": ["session-1-present", "session-2-present"],
                             "alphabet": requests, "observations": states, "initial": states.index(3),
                             "transitions": transitions}}
        return {"id": "duplicate-token", "sessions": 2, "arm": "baseline", "initial_rows": initial_rows,
                "credential_arguments": credential_arguments(2), "schema": schema, "graph": graph,
                "source_modified": False,
                "input_change": "The second fixture row has the first row's token; the native database accepts both rows."}
    finally:
        session.close()


def ordinary_rows(result):
    return [{key: row[key] for key in ("binding", "equivalent", "length", "indices", "trace")}
            for row in result["profiles"]]


def diagnose_duplicate(raw):
    # These production imports occur only after native acquisition is saved.
    from benchmarks.stateful_family import run_method
    from protocol_profile import protocol_binding_profile
    from protocol_grouped import support_indexed_protocol_profile
    case = {"id": raw["id"], "sessions": 2, "arm": "baseline", "policy": fixtures.contract(2),
            "machine": raw["graph"]["machine"], "family": fixtures.family(2),
            "callers": fixtures.callers(raw["graph"]["machine"]["alphabet"])}
    results = {}
    for method in TOTAL_METHODS:
        results[method] = ordinary_rows(run_method(case, method))
    for caller in CALLERS:
        for label, method in (("scan", protocol_binding_profile), ("grouped", support_indexed_protocol_profile)):
            result = method(case["policy"], case["machine"], case["callers"][caller], family=case["family"])
            results[f"protocol-{label}/{caller}"] = ordinary_rows(result)
    return {"case": case, "proposal": propose_bijections(raw["initial_rows"], raw["credential_arguments"]),
            "profiles": results}


def acquire(results, source_results):
    require(not results.exists(), "use a fresh observation-study destination")
    from source_study.historical_h19.source import check_native
    from source_study.session_correspondence.native import replay_words
    dependency = check_native()
    cases, native = source_cases(source_results)
    profiles, physical = [], []
    started = time.perf_counter_ns()
    for case in cases:
        records = identity_profiles(case, native[case["sessions"]][case["arm"]])
        words = profile_words(records)
        observations = asyncio.run(replay_words(case["sessions"], case["arm"], words))
        profiles.append({"id": case["id"], "sessions": case["sessions"], "arm": case["arm"], "callers": records})
        physical.append({"id": case["id"], "sessions": case["sessions"], "arm": case["arm"], "words": observations})
        print(f"native identity witnesses: {case['id']}, {len(words)} distinct words", flush=True)
    duplicate = asyncio.run(collect_duplicate())
    results.mkdir(parents=True)
    write(results / "native-witnesses.json.gz", physical)
    write(results / "duplicate-native.json.gz", duplicate)
    write(results / "identity-profiles.json.gz", profiles)
    write(results / "acquisition.json", {
        "native_dependencies_checked": bool(dependency), "required_native_packages": dependency["versions"],
        "python": dependency["python"], "baseline_source_modified": False, "control_arm": CONTROL_ARM,
        "source": SOURCE, "selected_methods": SELECTED_METHODS,
        "clock_and_store": "The fixed unexpired-row fixtures use the existing source loader and native ORM/SQLite environment.",
        "wall_ns": time.perf_counter_ns() - started,
        "timing_scope": "This is a witness-acquisition and duplicate-input validation run, not an algorithm benchmark; earlier diagnosis timings remain unchanged."})
    write(results / "duplicate-diagnosis.json", diagnose_duplicate(duplicate))
    summary = verify(results, source_results, check_summary=False)
    write(results / "summary.json", summary)
    return summary


def verify(results, source_results, *, check_summary=True):
    cases, native = source_cases(source_results)
    acquisition = read(results / "acquisition.json")
    packages = read(ART / "source_study/historical_h19/pins.json")["required_versions"]
    require(acquisition["baseline_source_modified"] is False and acquisition["control_arm"] == CONTROL_ARM
            and acquisition["source"] == SOURCE and acquisition["selected_methods"] == SELECTED_METHODS,
            "identity-study source or introduced-control description differs")
    require(acquisition["native_dependencies_checked"] is True and acquisition["required_native_packages"] == packages,
            "identity-study native dependency record differs")
    require(isinstance(acquisition["python"], str) and acquisition["python"] and
            type(acquisition["wall_ns"]) is int and acquisition["wall_ns"] > 0,
            "identity-study acquisition record is incomplete")
    profile_list = read(results / "identity-profiles.json.gz")
    physical_list = read(results / "native-witnesses.json.gz")
    profiles = {row["id"]: row for row in profile_list}
    physical = {row["id"]: row for row in physical_list}
    ids = {row["id"] for row in cases}
    require(len(profiles) == len(profile_list) == len(physical) == len(physical_list) == len(ids),
            "identity study repeats or omits case identifiers")
    require(set(profiles) == set(physical) == ids, "identity study case coverage differs")
    case_summaries = []
    binding_rows = excluded_rows = matched_rows = word_runs = operations = 0
    identity_disagreements = decision_state_disagreements = 0
    baseline_proposals = []
    for case in cases:
        name, size, arm = case["id"], case["sessions"], case["arm"]
        graph = native[size][arm]
        initial_rows = next(edge["observation"]["before_rows"] for edge in graph["edges"] if not edge["prefix"])
        cells = check_graph(size, graph, initial_rows, arm)
        require(case["machine"] == graph["machine"], "identity case table differs from source records")
        require(case["family"] == fixtures.family(size), "identity case family differs")
        require(case["callers"] == fixtures.callers(case["machine"]["alphabet"]), "identity caller differs")
        wanted = identity_profiles(case, graph)
        require(profiles[name] == {"id": name, "sessions": size, "arm": arm, "callers": wanted},
                "retained complete identity profile differs")
        words = {tuple(row["indices"]): row["observations"] for row in physical[name]["words"]}
        require(len(words) == len(physical[name]["words"]) and sorted(words, key=lambda w: (len(w), w)) == profile_words(wanted),
                "physical identity words are missing, duplicated or extra")
        for word, observations in words.items():
            require(len(word) == len(observations) == 1, "identity study should have one-request witnesses")
            state = (1 << size) - 1
            for index, observed in zip(word, observations):
                require(observed == cells[state, index], "fresh identity execution differs from acquired source cell")
                state = observed["after_state"]
            word_runs += 1
            operations += len(observations)
        proposal = propose_bijections(initial_rows, credential_arguments(size))
        require(proposal["status"] == "supported-bijection-shape" and proposal["family"] == case["family"],
                "native baseline records do not support the declared bijection shape")
        if arm == "baseline":
            baseline_proposals.append({"sessions": size, "proposal": proposal})
        callers = {}
        coverage = Counter()
        for caller, records in wanted.items():
            require([row["binding"] for row in records] == case["family"], "identity family order differs")
            for row in records:
                binding_rows += 1
                if row["equivalent"]:
                    matched_rows += 1
                    require(row["length"] is None and row["indices"] is None and row["trace"] is None,
                            "matching identity profile contains a witness")
                    continue
                excluded_rows += 1
                require(row["length"] == 1, "unexpected identity shortest length")
                word = tuple(row["indices"])
                observed = words[word]
                expected_trace = native_replay_rows(case, row["binding"], caller, row["indices"], observed)
                require(row["trace"] == expected_trace, "identity replay fields differ from physical records")
                oracle.check_native_witness(size, row["binding"], row["indices"], observed, selected_identity=True)
                identity_disagreements += not row["trace"][-1]["identity_equal"]
                decision_state_disagreements += not (
                    row["trace"][-1]["decision_equal"] and row["trace"][-1]["state_equal"])
                coverage[word] += 1
            callers[caller] = summarize_profiles(records)
            expected_matching = 0 if arm == "omit-delete" and caller != "lookup-only" else 1
            require(callers[caller]["matching"] == expected_matching, "identity observation viability differs")
        case_summaries.append({"id": name, "callers": callers, "distinct_native_words": len(words),
                               "native_operations": sum(map(len, words.values())),
                               "binding_caller_coverage": [{"indices": list(word), "excluded_binding_rows": count}
                                                           for word, count in sorted(coverage.items())]})
    raw = read(results / "duplicate-native.json.gz")
    duplicate = read(results / "duplicate-diagnosis.json")
    require(raw["source_modified"] is False and raw["schema"] == {
                "token_unique": False, "token_nullable": False, "inserted_rows": 2},
            "duplicate-token control no longer uses the unmodified nonunique token column")
    duplicate_rows = fixtures.serialized_rows(fixtures.rows(2))
    duplicate_rows[1]["token"] = duplicate_rows[0]["token"]
    require(raw["id"] == "duplicate-token" and raw["sessions"] == 2 and raw["arm"] == "baseline"
            and raw["initial_rows"] == duplicate_rows and raw["credential_arguments"] == credential_arguments(2),
            "duplicate-token inputs differ from the declared single token change")
    cells = check_graph(2, raw["graph"], raw["initial_rows"])
    require(len(raw["initial_rows"]) == 2 and len({row["token"] for row in raw["initial_rows"]}) == 1,
            "duplicate-token control does not contain two equal tokens")
    proposal = propose_bijections(raw["initial_rows"], raw["credential_arguments"])
    require(duplicate["proposal"] == proposal and proposal["status"] == "unsupported-bijection-shape"
            and proposal["family"] is None and "row-token-values-not-unique" in proposal["issues"],
            "automatic family proposal accepted unsupported one-to-one records")
    case = duplicate["case"]
    require(case == {"id": raw["id"], "sessions": 2, "arm": "baseline", "policy": fixtures.contract(2),
                     "machine": raw["graph"]["machine"], "family": fixtures.family(2),
                     "callers": fixtures.callers(raw["graph"]["machine"]["alphabet"])}, "explicit duplicate-input contract changed")
    methods = set(TOTAL_METHODS) | {f"protocol-{method}/{caller}" for caller in CALLERS for method in ("scan", "grouped")}
    require(set(duplicate["profiles"]) == methods, "duplicate-input comparator coverage differs")
    duplicate_comparisons = 0
    for method, records in duplicate["profiles"].items():
        caller = case["callers"][method.split("/")[1]] if "/" in method else None
        expected = [oracle.profile(2, case["machine"], binding, caller) for binding in case["family"]]
        require(records == expected and all(not row["equivalent"] and row["length"] == 1 for row in records),
                "explicit duplicate-input family should be diagnosed as all excluded")
        for row in records:
            word = row["indices"]
            require(len(word) == 1, "duplicate-input witness should use one observed cell")
            observed = [cells[3, word[0]]]
            actual = native_replay_rows(case, row["binding"], method.split("/")[1] if "/" in method else "unrestricted",
                                        word, observed, identity=False)
            if "/" not in method:
                actual = [{key: value for key, value in r.items() if key not in {"source_state", "target_state", "protocol_state"}}
                          for r in actual]
            require(actual == row["trace"], "explicit duplicate-input replay differs from native records")
            duplicate_comparisons += 1
    deletion = cells[3, fixtures.alphabet(2).index(["client", "row-1", "remove"])]
    require(deletion["removed_ids"] == [1, 2] and deletion["after_state"] == 0,
            "native repeated-token deletion did not remove both matching rows")
    summary = {"status": "PASS", "identity_cases": len(cases), "caller_profiles": len(cases) * len(CALLERS),
               "binding_rows": binding_rows, "matching_binding_rows": matched_rows,
               "excluded_binding_rows": excluded_rows, "distinct_native_word_runs": word_runs,
               "native_identity_operations": operations, "cases": case_summaries,
               "excluded_by_identity": identity_disagreements,
               "excluded_by_decision_or_state": decision_state_disagreements,
               "baseline_family_proposals": baseline_proposals,
               "duplicate_token": {"native_states": len(raw["graph"]["states"]), "native_cells": len(raw["graph"]["edges"]),
                                   "native_source_operations": raw["graph"]["source_operations"],
                                   "proposal_status": proposal["status"], "proposal_issues": proposal["issues"],
                                   "explicit_contract_classification": "none", "explicit_family_size": len(case["family"]),
                                   "complete_comparator_profiles": len(methods), "binding_comparisons": duplicate_comparisons,
                                   "one_removal_deleted_rows": deletion["removed_ids"]},
               "scope": "Identity observations are checked by direct source equations, complete record-bearing replays and native calls. They are an observation-ablation study, not a richer encoding claimed for the general diagnostic backend. Family proposals check source-record prerequisites; explicit user contracts remain diagnosable when those prerequisites fail. Earlier timing results are unchanged."}
    require((binding_rows, matched_rows, excluded_rows, word_runs, operations) == (5232, 20, 5212, 35, 35),
            "identity study denominators differ from the declared cohort")
    if check_summary:
        require(read(results / "summary.json") == summary, "identity-study summary differs from raw records")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--results", type=Path, default=ART / "results/session-observation")
    parser.add_argument("--source-results", type=Path, default=ART / "results/session-correspondence")
    args = parser.parse_args()
    summary = acquire(args.results, args.source_results) if args.acquire else verify(args.results, args.source_results)
    print(json.dumps({key: value for key, value in summary.items() if key not in {"cases", "baseline_family_proposals"}}, indent=2))


if __name__ == "__main__":
    main()
