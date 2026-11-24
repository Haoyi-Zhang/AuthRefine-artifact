"""Independent finite-word audit of fixed-binding caller-protocol profiles.

The complete declared domain has two reference interpretations. Each has one
Boolean state, one request, and one of nine denial-stuttering transition
tables. The target has two states with identity observations and one of 25
partial tables (a cell is absent or has a decision and successor). The caller
has two states and one of nine partial tables. Initial states are zero.

All 9*9*25*9 = 18,225 ordered family/target/caller instances are compared.
The oracle evaluates at most four repeated requests by table lookup. It does
not call the policy interpreter or construct the implementation's graph.
Four is the product bound: two target states times two caller states.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
from itertools import product
import json
from pathlib import Path
import sys

ARTIFACT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT / "src"))
from checker import Rejected
from protocol_profile import protocol_binding_profile

ALPHABET = [["caller", "object", "invoke"]]
FAMILY = [{"mode": "left"}, {"mode": "right"}]


def reference_tables():
    for choices in product(range(3), repeat=2):
        yield tuple(("deny", state) if choice == 0 else ("allow", choice - 1)
                    for state, choice in enumerate(choices))


def target_tables():
    yield from product((None, ("deny", 0), ("deny", 1),
                        ("allow", 0), ("allow", 1)), repeat=2)


def caller_tables():
    yield from product((None, 0, 1), repeat=2)


def inputs(left, right, target, caller):
    rules = []
    for mode, table in enumerate((left, right)):
        for state, (decision, following) in enumerate(table):
            rules.append({
                "decision": decision,
                "guard": [
                    {"field": "role", "alias": "mode", "negated": bool(mode)},
                    {"field": "state", "name": "flag", "value": bool(state)},
                ],
                "updates": ([{"name": "flag", "value": bool(following)}]
                            if decision == "allow" else []),
            })
    policy = {
        "principals": ["caller"], "resources": ["object"], "actions": ["invoke"],
        "roles": ["left", "right"], "members": [["caller", "left"]],
        "state": [["flag", False]],
        "aliases": [{"name": "mode", "kind": "role", "candidates": ["left", "right"]}],
        "rules": rules,
    }
    machine = {
        "state_names": ["flag"], "alphabet": ALPHABET, "observations": [0, 1],
        "initial": 0,
        "transitions": [[list(edge) if edge is not None else None] for edge in target],
    }
    protocol = {"initial": 0, "transitions": [[edge] for edge in caller]}
    return policy, machine, protocol


def oracle_admission(target, caller):
    """Look along the only request word, through the finite product bound."""
    if caller[0] is None:
        return "inactive"
    q = t = 0
    for length in range(1, 5):
        next_t = caller[t]
        if next_t is None:
            return "admitted"
        edge = target[q]
        if edge is None:
            return "missing"
        q, t = edge[1], next_t
    return "admitted"


def oracle_profile(reference, target, caller):
    """Return exact shortest length and all independently computed replay rows."""
    source = q = t = 0
    rows = []
    for length in range(1, 5):
        next_t = caller[t]
        if next_t is None:
            return None, None
        expected = reference[source]
        actual = target[q]
        if actual is None:
            raise AssertionError("oracle_profile called before admission")
        rows.append({
            "request": ALPHABET[0], "source_state": source,
            "target_state": q, "protocol_state": t,
            "source": list(expected), "target": list(actual),
            "decision_equal": expected[0] == actual[0],
            "state_equal": expected[1] == actual[1],
            "compared_equal": expected == actual,
        })
        if expected != actual:
            return length, rows
        source, q, t = expected[1], actual[1], next_t
    return None, None


def compare_case(left, right, target, caller):
    admission = oracle_admission(target, caller)
    try:
        result = protocol_binding_profile(*inputs(left, right, target, caller), family=FAMILY)
    except Rejected as error:
        if admission == "admitted" or error.kind != "inconclusive":
            raise AssertionError(("unexpected rejection", admission, error.kind)) from error
        return {"status": "inconclusive", "admission": admission}
    if admission != "admitted":
        raise AssertionError("incomplete interface returned a classified family")
    lengths = []
    for table, binding, row in zip((left, right), FAMILY, result["profiles"], strict=True):
        length, replay = oracle_profile(table, target, caller)
        if row["binding"] != binding or row["length"] != length or row["equivalent"] != (length is None):
            raise AssertionError(("wrong family profile", binding, length, row))
        if length is None:
            if row["indices"] is not None or row["trace"] is not None:
                raise AssertionError("matching binding has a witness")
        else:
            if row["indices"] != [0] * length or len(row["trace"]) != length:
                raise AssertionError("wrong repeated-request witness")
            for got, expected in zip(row["trace"], replay, strict=True):
                if got["binding"] != binding or any(got[key] != value for key, value in expected.items()):
                    raise AssertionError(("wrong witness replay", expected, got))
            if length > result["target_protocol_reachable_states"]:
                raise AssertionError("witness exceeds reachable-product bound")
        lengths.append(length)
    matches = [binding for binding, length in zip(FAMILY, lengths, strict=True) if length is None]
    if result["matching_family"] != matches:
        raise AssertionError("matching family does not equal the independently checked rows")
    if result["graph_traversals"] != 1:
        raise AssertionError("family result does not use one target/caller graph")
    expected_class = "all" if len(matches) == 2 else "some" if len(matches) == 1 else "none"
    if result["classification"] != expected_class:
        raise AssertionError("wrong family classification")
    return {"status": "classified", "classification": expected_class, "lengths": lengths,
            "graph_states": result["target_protocol_reachable_states"],
            "semantic_evaluations": result["transition_evaluations"],
            "replay_evaluations": result["replay_evaluations"]}


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    refs, targets, callers = list(reference_tables()), list(target_tables()), list(caller_tables())
    domains = {"references": refs, "targets": targets, "callers": callers,
               "family": FAMILY, "alphabet": ALPHABET,
               "initial_states": [0, 0, 0], "word_bound": 4}
    (output / "domains.json").write_text(json.dumps(domains, indent=2) + "\n")
    digest, counts, strata = hashlib.sha256(), Counter(), Counter()
    cases = 0
    with (output / "cases.jsonl.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as stream:
            for i, left in enumerate(refs):
                for j, right in enumerate(refs):
                    for k, target in enumerate(targets):
                        for l, caller in enumerate(callers):
                            result = compare_case(left, right, target, caller)
                            row = {"reference_ids": [i, j], "target_id": k, "caller_id": l, **result}
                            encoded = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
                            stream.write(encoded)
                            digest.update(encoded)
                            cases += 1
                            key = result.get("classification", result.get("admission"))
                            counts[key] += 1
                            for length in result.get("lengths", []):
                                strata["infinity" if length is None else str(length)] += 1
    paths = [ARTIFACT / "src/protocol_profile.py", Path(__file__).resolve(),
             ARTIFACT / "src/extensions.py", ARTIFACT / "src/checker.py"]
    summary = {
        "domain": "all ordered pairs of 9 denial-stuttering one-request reference tables, 25 partial two-state targets, 9 partial two-state callers",
        "instances": cases, "expected_instances": 9 * 9 * 25 * 9,
        "outcomes": dict(sorted(counts.items())),
        "classified_binding_shortest_lengths": dict(sorted(strata.items())),
        "oracle": "independent table lookup on request words of lengths 1 through 4; no policy evaluator or graph search",
        "cases_uncompressed_sha256": digest.hexdigest(),
        "all_comparisons_passed": True,
        "source_sha256": {str(path.relative_to(ARTIFACT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in paths},
        "limits": ["One request, one Boolean source state, two target states, two caller states, equal initial observations.",
                   "The explicit two-binding family may contain behaviorally equal interpretations.",
                   "This finite implementation audit does not measure application prevalence or verify source observers."],
    }
    if cases != summary["expected_instances"]:
        raise AssertionError("incomplete audit enumeration")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new output directory")
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))
