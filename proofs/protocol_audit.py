"""Exhaustively audit a declared two-state caller-protocol model family.

The oracle enumerates admitted words and looks up an independently supplied
reference transition table. It does not import reference_step, use the policy
interpreter, or use the checker's graph traversal. The implementation under
comparison is verify_protocol; policy ASTs are generated from those reference
cells so their agreement is also exercised.

The complete domain has 81 denial-stuttering reference tables, 256 unrestricted
candidate tables and 81 partial caller protocols, each with two states and two
requests, fixed initial state 0 and complete Boolean-state observations. This
is a finite exhaustive audit of this domain, not a program-population sample.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from itertools import product
import json
from pathlib import Path
import sys
import time

ARTIFACT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT / "src"))
from checker import Rejected
from protocol_check import verify_protocol


ALPHABET = [["caller", "object", "a"], ["caller", "object", "b"]]


def reference_tables():
    for choices in product(range(3), repeat=4):
        yield tuple(("deny", index // 2) if choice == 0 else ("allow", choice - 1)
                    for index, choice in enumerate(choices))


def candidate_tables():
    choices = [(decision, state) for decision in ("deny", "allow") for state in range(2)]
    yield from product(choices, repeat=4)


def caller_tables():
    yield from product((None, 0, 1), repeat=4)


def policy_from_table(cells):
    rules = []
    for index, (decision, successor) in enumerate(cells):
        state, action = divmod(index, 2)
        rules.append({
            "decision": decision,
            "guard": [{"field": "state", "name": "flag", "value": bool(state)},
                      {"field": "action", "name": ("a", "b")[action], "negated": False}],
            "updates": ([{"name": "flag", "value": bool(successor)}] if decision == "allow" else []),
        })
    return {"principals": ["caller"], "resources": ["object"], "actions": ["a", "b"],
            "roles": [], "members": [], "state": [["flag", False]], "aliases": [], "rules": rules}


def machine_from_table(cells):
    return {"state_names": ["flag"], "alphabet": ALPHABET, "observations": [0, 1], "initial": 0,
            "transitions": [[list(cells[2 * state + action]) for action in range(2)] for state in range(2)]}


def protocol_from_table(cells):
    return {"initial": 0, "transitions": [list(cells[:2]), list(cells[2:])]}


def reachable_product_nodes(candidate, protocol):
    reached = {(0, 0)}
    frontier = [(0, 0)]
    while frontier:
        target, caller = frontier.pop()
        for action in range(2):
            following_caller = protocol[2 * caller + action]
            if following_caller is None:
                continue
            following = (candidate[2 * target + action][1], following_caller)
            if following not in reached:
                reached.add(following)
                frontier.append(following)
    return reached


def replay_word(reference, candidate, protocol, word):
    """Return None for a disabled word, otherwise every independently computed row."""
    source_state = target_state = caller_state = 0
    rows = []
    for action in word:
        following_caller = protocol[2 * caller_state + action]
        if following_caller is None:
            return None
        expected = reference[2 * source_state + action]
        actual = candidate[2 * target_state + action]
        rows.append((caller_state, action, expected, actual))
        source_state, target_state, caller_state = expected[1], actual[1], following_caller
    return rows


def enumerate_word_oracle(reference, candidate, protocol):
    """No reference interpreter and no paired-state search are used here."""
    nodes = reachable_product_nodes(candidate, protocol)
    if protocol[0] is None and protocol[1] is None:
        return {"status": "inconclusive", "length": None, "nodes": len(nodes), "word": None}
    # The separately mechanized theorem supplies the finite completeness bound.
    # Enumerating words (including repeated-state words) is independent of the
    # implementation's source/target/protocol traversal and parent reconstruction.
    for length in range(1, len(nodes) + 1):
        for word in product(range(2), repeat=length):
            rows = replay_word(reference, candidate, protocol, word)
            if rows is not None and any(expected != actual for _, _, expected, actual in rows):
                return {"status": "mismatch", "length": length, "nodes": len(nodes), "word": word}
    return {"status": "equivalent", "length": None, "nodes": len(nodes), "word": None}


def compare_case(reference, candidate, protocol, policy=None, machine=None, caller=None):
    expected = enumerate_word_oracle(reference, candidate, protocol)
    try:
        observed = verify_protocol(policy if policy is not None else policy_from_table(reference),
                                   machine if machine is not None else machine_from_table(candidate),
                                   caller if caller is not None else protocol_from_table(protocol))
    except Rejected as error:
        if error.kind != "inconclusive" or expected["status"] != "inconclusive":
            raise AssertionError({"expected": expected, "rejection": error.kind, "message": str(error)}) from error
        observed = {"status": "inconclusive", "length": None}
    if observed["status"] != expected["status"]:
        raise AssertionError({"expected": expected, "observed": observed})
    if expected["status"] == "mismatch":
        if observed.get("length") != expected["length"] or observed["length"] > expected["nodes"]:
            raise AssertionError({"expected": expected, "observed": observed})
        witness = tuple(("a", "b").index(row["request"][2]) for row in observed["trace"])
        rows = replay_word(reference, candidate, protocol, witness)
        if (rows is None or len(rows) != observed["length"]
                or any(a != b for _, _, a, b in rows[:-1]) or rows[-1][2] == rows[-1][3]):
            raise AssertionError({"invalid_witness": witness, "rows": rows})
        for row, actual_row in zip(rows, observed["trace"]):
            if (row[0] != actual_row["protocol_state"] or list(row[2]) != actual_row["source"]
                    or list(row[3]) != actual_row["target"]):
                raise AssertionError({"oracle_row": row, "observed_row": actual_row})
    elif expected["status"] == "equivalent" and observed.get("product_states") != expected["nodes"]:
        raise AssertionError({"expected": expected, "observed": observed})
    return expected


def digest_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_audit(reference_limit=81):
    started = time.perf_counter()
    references = list(reference_tables())[:reference_limit]
    candidates = list(candidate_tables())
    protocols = list(caller_tables())
    machines = [machine_from_table(cells) for cells in candidates]
    callers = [protocol_from_table(cells) for cells in protocols]
    totals, lengths, product_sizes = Counter(), Counter(), Counter()
    per_reference = []
    ordered_digest = hashlib.sha256()
    examples = {}
    for reference_index, reference in enumerate(references):
        counts = Counter()
        policy = policy_from_table(reference)
        for candidate_index, candidate in enumerate(candidates):
            for protocol_index, protocol in enumerate(protocols):
                result = compare_case(reference, candidate, protocol, policy,
                                      machines[candidate_index], callers[protocol_index])
                status = result["status"]
                totals[status] += 1
                counts[status] += 1
                product_sizes[str(result["nodes"])] += 1
                if result["length"] is not None:
                    lengths[str(result["length"])] += 1
                record = [reference_index, candidate_index, protocol_index,
                          status, result["length"], result["nodes"]]
                ordered_digest.update(json.dumps(record, separators=(",", ":")).encode() + b"\n")
                key = status if result["length"] is None else f"mismatch_length_{result['length']}"
                examples.setdefault(key, {"reference_index": reference_index, "candidate_index": candidate_index,
                                          "protocol_index": protocol_index, "reference": reference,
                                          "candidate": candidate, "protocol": protocol, "oracle": result})
        per_reference.append({"reference_index": reference_index, "cells": reference, "counts": dict(counts)})
        print(json.dumps({"reference_completed": reference_index + 1,
                          "cases_completed": sum(totals.values()), "counts": dict(totals)}), flush=True)
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Exhaustive declared two-state, two-request finite domain; no application prevalence claim",
        "all_passed": True,
        "reference_tables": len(references), "candidate_tables": len(candidates), "caller_protocols": len(protocols),
        "complete_declared_domain": len(references) == 81,
        "cases": sum(totals.values()), "status_counts": dict(totals),
        "shortest_mismatch_lengths": dict(sorted(lengths.items())),
        "reachable_target_protocol_node_counts": dict(sorted(product_sizes.items())),
        "oracle": "Direct word enumeration and independent reference-cell lookup; no reference_step or source-policy evaluator",
        "oracle_completeness_basis": "ProtocolDiagnosis.lean shortest_admitted_witness_bound",
        "implementation_contract": "No enabled event is inconclusive although the mathematical epsilon-only language is equivalent",
        "comparison_fields": ["status", "shortest length", "admissibility", "every replay row", "proper-prefix agreement",
                              "final disagreement", "reachable-product bound", "accepted reachable-product count"],
        "ordered_comparison_sha256": ordered_digest.hexdigest(),
        "wall_seconds": time.perf_counter() - started,
        "source_sha256": {path.relative_to(ARTIFACT).as_posix(): digest_file(path) for path in (
            Path(__file__), ARTIFACT / "proofs/ProtocolDiagnosis.lean",
            ARTIFACT / "src/protocol_check.py", ARTIFACT / "src/checker.py")},
        "per_reference": per_reference, "examples": examples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New result JSON path")
    parser.add_argument("--reference-limit", type=int, default=81,
                        help="1–81 reference tables; only 81 exhausts the declared domain")
    args = parser.parse_args()
    if not 1 <= args.reference_limit <= 81:
        parser.error("--reference-limit must be 1 through 81")
    if args.output.exists():
        parser.error("--output must not already exist")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = run_audit(args.reference_limit)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "all_passed", "complete_declared_domain", "cases", "status_counts", "wall_seconds")}), flush=True)


if __name__ == "__main__":
    main()
