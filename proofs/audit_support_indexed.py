"""Validate support-indexed profiles on the existing 23,040-pair audit domain.

This reuses the previously declared 180 policy representatives and 128 total
two-state target tables. It adds an implementation to that validation domain;
it does not add 23,040 new policies, applications, or independent experiments.
The oracle uses the separate direct source semantics and explicit source/target
product search from exhaustive_audit.py, then independently reconstructs every
returned fixed-binding replay row.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

ARTIFACT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT / "src"))
from exhaustive_audit import (complete_bindings, direct_product, direct_step,
                              policy_representatives, target_machines)
from family_diagnosis import support_indexed_profile


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def direct_replay(policy, machine, binding, indices):
    source = sum(1 << i for i, (_, value) in enumerate(policy["state"]) if value)
    target = machine["initial"]
    rows = []
    final_state = final_request = None
    for index in indices:
        request = machine["alphabet"][index]
        actual = direct_step(policy, source, request, binding)
        decision, following = machine["transitions"][target][index]
        expected = (decision, machine["observations"][following])
        rows.append({
            "request": request, "binding": binding,
            "source": list(actual), "target": list(expected),
            "decision_equal": actual[0] == expected[0],
            "state_equal": actual[1] == expected[1],
            "compared_equal": actual == expected,
        })
        final_state, final_request = target, index
        source, target = actual[1], following
    return rows, final_state, final_request


def compare_case(policy, machine):
    report = support_indexed_profile(policy, machine)
    bindings = list(complete_bindings(policy))
    if len(report["profiles"]) != len(bindings):
        raise AssertionError("support-indexed result omitted a family member")
    expected_profiles = []
    for binding in bindings:
        length, indices = direct_product(policy, machine, binding)
        expected = {"binding": binding, "equivalent": length is None, "length": length,
                    "indices": indices, "trace": None}
        if length is not None:
            rows, target, request = direct_replay(policy, machine, binding, indices)
            expected["trace"] = rows
            if length == 0:
                expected["reason"] = "initial observation"
            else:
                expected.update(target_state=target, request=request)
        expected_profiles.append(expected)
    if report["profiles"] != expected_profiles:
        raise AssertionError({"reason": "full fixed-binding profile differs",
                              "expected": expected_profiles, "actual": report["profiles"]})
    matches = sum(row["equivalent"] for row in expected_profiles)
    lengths = [row["length"] for row in expected_profiles if not row["equivalent"]]
    strata = Counter("infinity" if row["equivalent"] else str(row["length"])
                     for row in expected_profiles)
    expected_aggregate = {
        "classification": "all" if matches == len(bindings) else "none" if matches == 0 else "some",
        "bindings": len(bindings), "matching_bindings": matches,
        "failing_bindings": len(bindings) - matches,
        "shortest_failure": min(lengths) if lengths else None,
        "strata": dict(strata),
    }
    if any(report[key] != value for key, value in expected_aggregate.items()):
        raise AssertionError("support-indexed aggregate does not describe its profiles")
    return report


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    policies, machines = policy_representatives(), list(target_machines())
    if len(policies) != 180 or len(machines) != 128:
        raise AssertionError("the previously declared tiny domain has changed")
    domains = {"policies": policies, "machines": machines}
    (output / "inputs.json").write_bytes(encoded(domains))
    digest, counts, strata, work = hashlib.sha256(), Counter(), Counter(), Counter()
    pairs = bindings = replays = 0
    with (output / "profiles.jsonl.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as stream:
            for pi, policy in enumerate(policies):
                for mi, machine in enumerate(machines):
                    result = compare_case(policy, machine)
                    row = {"policy_id": pi, "machine_id": mi, **result}
                    data = encoded(row) + b"\n"
                    stream.write(data)
                    digest.update(data)
                    counts[result["classification"]] += 1
                    strata.update(result["strata"])
                    work.update(result["work_breakdown"])
                    pairs += 1
                    bindings += result["bindings"]
                    replays += result["replay_evaluations"]
                if (pi + 1) % 60 == 0:
                    print(f"checked {pi + 1}/180 existing policy representatives", flush=True)
    files = [Path(__file__).resolve(), ARTIFACT / "src/family_diagnosis.py",
             ARTIFACT / "src/exhaustive_audit.py", ARTIFACT / "src/extensions.py",
             ARTIFACT / "src/checker.py"]
    summary = {
        "status": "PASS", "policy_machine_pairs": pairs,
        "policy_semantic_representatives": len(policies), "machines_per_policy": len(machines),
        "binding_profiles_checked": bindings, "replay_rows_checked": replays,
        "family_classifications": dict(sorted(counts.items())),
        "binding_shortest_lengths": dict(sorted(strata.items())),
        "implementation_work_breakdown": dict(sorted(work.items())),
        "profiles_uncompressed_sha256": digest.hexdigest(),
        "inputs_sha256": hashlib.sha256(encoded(domains)).hexdigest(),
        "source_sha256": {str(path.relative_to(ARTIFACT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in files},
        "scope": [
            "The same 23,040 policy/target pairs already used by exhaustive_audit.py; only the new support-indexed implementation is added.",
            "One request, one Boolean source bit, zero or one two-candidate role alias, 180 initialized policy representatives, all 128 total two-state targets of the declared shape.",
            "The independent direct semantics and source/target product oracle check exact matching families, shortest words, every replay field, and every semantic aggregate.",
            "This audit is not a new application sample or an independent real-world prevalence estimate.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "runtime.json").write_text(json.dumps({"wall_seconds": time.perf_counter() - started,
                                                    "python": sys.version}, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new output directory")
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))
