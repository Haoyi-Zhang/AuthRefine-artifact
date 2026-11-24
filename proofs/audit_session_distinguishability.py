#!/usr/bin/env python3
"""Enumerate session correspondence profiles and minimum covers by short tests.

The source and physical observations below are direct equations. No production
evaluator, diagnostic search, compiler, native adapter or fixture is imported.
Every test starts with all rows present. The default run exhausts all declared
words of length at most two for every permutation at sizes two through six.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
from itertools import combinations, permutations, product
import json
from math import comb, factorial
from pathlib import Path
import sys
from time import perf_counter

sys.dont_write_bytecode = True

CALLERS = ("unrestricted", "one-removal", "lookup-only")
OBSERVATIONS = ("decision-presence", "selected-row")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def alphabet(size):
    resources = sorted([f"credential-{i}" for i in range(1, size + 1)]
                       + ["missing"] + [f"row-{i}" for i in range(1, size + 1)])
    return [(resource, action) for resource in resources for action in ("lookup", "remove")]


def reference_step(size, present, request, binding):
    """binding[i - 1] is the credential of row i, not its inverse."""
    resource, action = request
    if action == "remove":
        after = present
        for row in range(1, size + 1):
            if resource == f"row-{row}":
                after &= ~(1 << (row - 1))
        return "allow", after, None
    selected = next((row for row in range(1, size + 1)
                     if present & (1 << (row - 1))
                     and resource == f"credential-{binding[row - 1]}"), None)
    return ("allow" if selected is not None else "deny"), present, selected


def physical_step(size, present, request):
    """Direct physical correspondence: credential j selects stored row j."""
    resource, action = request
    if action == "remove":
        if resource.startswith("row-"):
            row = int(resource.removeprefix("row-"))
            return "allow", present & ~(1 << (row - 1)), None
        return "allow", present, None
    if resource.startswith("credential-"):
        row = int(resource.removeprefix("credential-"))
        if present & (1 << (row - 1)):
            return "allow", present, row
    return "deny", present, None


def trace(size, requests, word, binding=None):
    present = (1 << size) - 1
    observations = [(None, present, None)]
    for index in word:
        outcome = (physical_step(size, present, requests[index]) if binding is None else
                   reference_step(size, present, requests[index], binding))
        observations.append(outcome)
        present = outcome[1]
    return tuple(observations)


def decision_presence(observations):
    return tuple((decision, present) for decision, present, _ in observations)


def admitted(requests, word):
    removals = sum(requests[index][1] == "remove" for index in word)
    return {"unrestricted": True, "one-removal": removals <= 1,
            "lookup-only": removals == 0}


def mask(members):
    result = 0
    for member in members:
        result |= 1 << member
    return result


def exhaustive_smaller_covers(coverage, complete, minimum, size, observation):
    """Check every subset smaller than the constructive cover, including empty."""
    rows = []
    for cardinality in range(minimum):
        checked = 0
        for subset in combinations(range(len(coverage)), cardinality):
            covered = 0
            for index in subset:
                covered |= coverage[index]
            checked += 1
            require(covered != complete,
                    f"{observation}, n={size}: shorter cover {subset}")
        require(checked == comb(len(coverage), cardinality), "subset enumeration count")
        rows.append({"sessions": size, "observation": observation,
                     "informative_tests": len(coverage), "tests_in_subset": cardinality,
                     "subsets_checked": checked, "covering_subsets": 0,
                     "union_operations": cardinality * checked})
    return rows


def audit_size(size):
    requests = alphabet(size)
    hypotheses = list(permutations(range(1, size + 1)))
    identity = tuple(range(1, size + 1))
    require(hypotheses[0] == identity, "identity permutation order")
    words = [()]
    words.extend((index,) for index in range(len(requests)))
    words.extend(product(range(len(requests)), repeat=2))
    word_positions = {word: index for index, word in enumerate(words)}
    eligibility = [admitted(requests, word) for word in words]
    full = mask(range(1, len(hypotheses)))
    first_words = {observation: {caller: [None] * len(hypotheses) for caller in CALLERS}
                   for observation in OBSERVATIONS}
    records = []

    # All words are evaluated from fresh initial states, in length/input order.
    # Empty words retain the initial presence observation explicitly.
    for word, allowed in zip(words, eligibility):
        target = trace(size, requests, word)
        target_projection = decision_presence(target)
        excluded = {observation: [] for observation in OBSERVATIONS}
        for member, binding in enumerate(hypotheses):
            source = trace(size, requests, word, binding)
            differs = {"decision-presence": decision_presence(source) != target_projection,
                       "selected-row": source != target}
            require(not differs["decision-presence"] or differs["selected-row"],
                    "richer observation lost a projected discrepancy")
            for observation in OBSERVATIONS:
                if differs[observation]:
                    excluded[observation].append(member)
                    for caller in CALLERS:
                        if allowed[caller] and first_words[observation][caller][member] is None:
                            first_words[observation][caller][member] = list(word)
        records.append({"request_indices": list(word),
                        "admitted_callers": [caller for caller in CALLERS if allowed[caller]],
                        "decision_presence_excluded": excluded["decision-presence"],
                        "selected_row_excluded": excluded["selected-row"]})

    # Finite closure obligations justify the all-words positive cases at each n.
    # Lookup-only retains the all-live state; identity agrees at every store cell.
    all_present = (1 << size) - 1
    lookup_closure = 0
    for binding in hypotheses:
        for request in requests:
            if request[1] == "lookup":
                actual = reference_step(size, all_present, request, binding)
                expected = physical_step(size, all_present, request)
                require(actual[:2] == expected[:2] and actual[1] == all_present,
                        "lookup-only projected closure")
                lookup_closure += 1
    identity_cells = 0
    for present in range(1 << size):
        for request in requests:
            require(reference_step(size, present, request, identity)
                    == physical_step(size, present, request), "identity store-cell agreement")
            identity_cells += 1

    profiles = []
    for member, binding in enumerate(hypotheses):
        result = {"sessions": size, "permutation_index": member,
                  "row_to_credential": list(binding)}
        for observation in OBSERVATIONS:
            for caller in CALLERS:
                word = first_words[observation][caller][member]
                expected_length = (None if member == 0 or
                                   (observation == "decision-presence" and caller == "lookup-only")
                                   else 2 if observation == "decision-presence" else 1)
                require((None if word is None else len(word)) == expected_length,
                        f"n={size}, binding={binding}: {observation}/{caller} length")
                result[f"{observation}/{caller}"] = {"matching": word is None,
                                                      "shortest_word": word,
                                                      "shortest_length": expected_length}
        profiles.append(result)

    # Every informative projected short word has precisely this form. The
    # remaining alphabet pairs, including two removals, have empty coverage.
    pair_words = []
    pair_coverage = []
    for row, credential in product(range(1, size + 1), repeat=2):
        word = (requests.index((f"row-{row}", "remove")),
                requests.index((f"credential-{credential}", "lookup")))
        pair_words.append(word)
        observed = records[word_positions[word]]["decision_presence_excluded"]
        predicted = [member for member, binding in enumerate(hypotheses)
                     if (binding[row - 1] == credential) != (row == credential)]
        require(observed == predicted and observed, "two-request discrepancy equation")
        pair_coverage.append(mask(observed))
    informative_pairs = set(pair_words)
    for word, record in zip(words, records):
        require(bool(record["decision_presence_excluded"]) == (word in informative_pairs),
                "unclassified informative short word")

    # Under selected-row observation, only credential lookups distinguish at
    # length one. Their coverage equals the corresponding projected pair.
    single_words = [(requests.index((f"credential-{i}", "lookup")),)
                    for i in range(1, size + 1)]
    single_coverage = [mask(records[word_positions[word]]["selected_row_excluded"])
                       for word in single_words]
    for word in words[:1 + len(requests)]:
        require(bool(records[word_positions[word]]["selected_row_excluded"])
                == (word in single_words), "unclassified informative one-request word")

    diagonal = []
    previous = 0
    for row in range(1, size):
        word = (requests.index((f"row-{row}", "remove")),
                requests.index((f"credential-{row}", "lookup")))
        coverage = mask(records[word_positions[word]]["decision_presence_excluded"])
        require(coverage == single_coverage[row - 1], "observation-dependent diagonal coverage")
        fresh = coverage & ~previous
        expected = factorial(size - row + 1) - factorial(size - row)
        require(fresh.bit_count() == expected, "factorial first-exclusion stratum")
        diagonal.append({"test_number": row, "decision_presence_word": list(word),
                         "selected_row_word": list(single_words[row - 1]),
                         "new_exclusions": fresh.bit_count(), "factorial_difference": expected,
                         "newly_excluded_permutation_indices": [member for member in range(len(hypotheses))
                                                                if fresh & (1 << member)]})
        previous |= coverage
    require(previous == full, "standard diagonal tests do not cover every nonidentity")
    cover_counts = exhaustive_smaller_covers(pair_coverage, full, size - 1, size, "decision-presence")
    cover_counts += exhaustive_smaller_covers(single_coverage, full, size - 1, size, "selected-row")

    width = len(requests)
    lookup_width = sum(action == "lookup" for _, action in requests)
    caller_words = {caller: sum(allowed[caller] for allowed in eligibility) for caller in CALLERS}
    require(len(words) == 1 + width + width * width, "complete short-word count")
    require(caller_words["lookup-only"] == 1 + lookup_width + lookup_width ** 2, "lookup word count")
    require(caller_words["one-removal"] == len(words) - lookup_width ** 2, "one-removal word count")
    counts = {
        "sessions": size, "permutations": len(hypotheses), "excluded_permutations": len(hypotheses) - 1,
        "alphabet_size": width, "words_length_zero": 1, "words_length_one": width,
        "words_length_two": width * width, "all_short_words": len(words),
        "lookup_only_short_words": caller_words["lookup-only"],
        "one_removal_short_words": caller_words["one-removal"],
        "binding_word_comparisons": len(hypotheses) * len(words),
        "observation_comparisons": 2 * len(hypotheses) * len(words),
        "reference_trace_steps": len(hypotheses) * (width + 2 * width * width),
        "physical_trace_steps": width + 2 * width * width,
        "lookup_only_closure_cells": lookup_closure, "identity_all_store_cells": identity_cells,
        "informative_projected_short_words": len(pair_words),
        "uninformative_projected_short_words": len(words) - len(pair_words),
        "informative_identity_single_words": len(single_words),
        "projected_cover_subsets_checked": sum(row["subsets_checked"] for row in cover_counts
                                                if row["observation"] == "decision-presence"),
        "identity_cover_subsets_checked": sum(row["subsets_checked"] for row in cover_counts
                                               if row["observation"] == "selected-row"),
        "minimum_projected_short_test_cover": size - 1,
        "minimum_identity_single_test_cover": size - 1,
        "projected_lookup_matching": len(hypotheses),
        "projected_one_removal_matching": 1, "projected_unrestricted_matching": 1,
        "identity_matching_each_caller": 1,
        "first_exclusion_counts": [row["new_exclusions"] for row in diagonal],
    }
    evidence = {"sessions": size,
                "requests": [{"resource": resource, "action": action} for resource, action in requests],
                "row_to_credential_permutations": [list(binding) for binding in hypotheses],
                "words": records, "profiles": profiles, "standard_covers": diagonal}
    return counts, evidence, cover_counts


def write_csv(path, records):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        for record in records:
            writer.writerow({key: json.dumps(value, separators=(",", ":")) if isinstance(value, (list, dict))
                             else value for key, value in record.items()})


def verify_csv(path, records):
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == list(records[0]), f"{path.name}: column order")
        actual = list(reader)
    expected = [{key: json.dumps(value, separators=(",", ":")) if isinstance(value, (list, dict))
                 else str(value) for key, value in record.items()} for record in records]
    require(actual == expected, f"{path.name}: retained counts differ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=list(range(2, 7)))
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path,
                             help="record a run in a new directory; an existing path is rejected")
    destination.add_argument("--verify-retained", type=Path,
                             help="recompute and compare retained scientific records without writing files")
    arguments = parser.parse_args()
    require(arguments.sizes == sorted(set(arguments.sizes))
            and all(2 <= size <= 6 for size in arguments.sizes),
            "sizes must be distinct increasing integers from 2 through 6")
    output = (arguments.output or arguments.verify_retained).resolve()
    if arguments.output is not None:
        require(not output.exists(), "output path already exists; choose a fresh directory or --verify-retained")
    else:
        require(output.is_dir(), "retained evidence directory is missing")
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    timer = perf_counter()
    cases, evidence, subsets = [], [], []
    for size in arguments.sizes:
        counts, details, covers = audit_size(size)
        cases.append(counts)
        evidence.append(details)
        subsets.extend(covers)
    aggregate_fields = ("permutations", "excluded_permutations", "all_short_words",
                        "binding_word_comparisons", "observation_comparisons",
                        "reference_trace_steps", "physical_trace_steps",
                        "lookup_only_closure_cells", "identity_all_store_cells",
                        "projected_cover_subsets_checked", "identity_cover_subsets_checked")
    result = {
        "status": "passed", "started_utc": started, "elapsed_seconds": perf_counter() - timer,
        "parameters": {"sizes": arguments.sizes, "maximum_word_length": 2,
                       "initial_store": "every identified row is present",
                       "fixed_correspondence": "row i maps to credential binding[i-1]",
                       "physical_correspondence": "identity after naming rows by their credentials",
                       "permutation_and_request_indices": "zero based in evidence; rows and credentials are one based",
                       "request_alphabet": "lookup/remove crossed with credential-1..n, missing, row-1..n",
                       "caller_languages": list(CALLERS),
                       "caller_definitions": {
                           "unrestricted": "every word over the declared alphabet",
                           "one-removal": "every word with at most one remove request; no-op removals count",
                           "lookup-only": "every word containing only lookup requests"},
                       "observations": list(OBSERVATIONS),
                       "test_reset": "each word starts from a fresh complete initial store",
                       "projected_cover_word_length_limit": 2, "selected_row_cover_word_length_limit": 1,
                       "dependencies": "Python standard library only",
                       "production_modules_imported": [], "native_executions": 0},
        "totals": {field: sum(case[field] for case in cases) for field in aggregate_fields},
        "cases": cases,
        "interpretation": [
            "Short-word matrices enumerate every declared word and permutation at each requested size.",
            "Positive all-words cases also check lookup-only closure and identity agreement at every store cell.",
            "Every uninformative short word is checked before minimum-cover enumeration discards it.",
            "Minimum-cover enumeration examines every subset below the achieved bound, not just diagonal tests.",
            "The theorem covers all n; finite enumeration and source execution remain separate evidence.",
            "The optimization counts independent words of a fixed maximum length, not arbitrary test suites or concatenated executions.",
        ],
    }
    sizes = " ".join(map(str, arguments.sizes))
    table = "\n".join(f"| {case['sessions']} | {case['permutations']} | {case['all_short_words']} | "
                      f"{case['binding_word_comparisons']} | {case['projected_cover_subsets_checked']} | "
                      f"{case['identity_cover_subsets_checked']} | {case['first_exclusion_counts']} |"
                      for case in cases)
    readme = f"""# Session correspondence distinguishability

The retained run passed all direct-equation, complete short-word, closure and
minimum-cover checks for session counts {', '.join(map(str, arguments.sizes))}.
The proofs are in ../../proofs/session-distinguishability.md and the paper's
technical/session-distinguishability.tex. These records contain no new native
source executions; the existing native session records instantiate the equations.

## Verify the retained records without writing

From the artifact directory, run:

    PYTHONDONTWRITEBYTECODE=1 python proofs/audit_session_distinguishability.py --sizes {sizes} --verify-retained results/session-distinguishability

This recomputes the scientific summary fields, complete matrices, profiles and
both CSV files. The recorded starting time and elapsed time are not compared.
The script uses only the Python standard library and creates no temporary files.

To retain a separate run, select a fresh output directory:

    PYTHONDONTWRITEBYTECODE=1 python proofs/audit_session_distinguishability.py --sizes {sizes} --output results/session-distinguishability-reproduction

An existing output path is rejected before enumeration. The output destination
is mandatory; rerunning the audit never silently overwrites a recorded campaign.

## Complete enumeration counts

| Sessions | Permutations | Words of length 0–2 | Binding/word comparisons | Smaller projected cover subsets | Smaller identity cover subsets | First-exclusion counts |
| ---: | ---: | ---: | ---: | ---: | ---: | :--- |
{table}

Every word starts with all rows present. The projected cover allows at most two
requests per word; the selected-row cover allows at most one. The candidate tests
for minimum-cover enumeration are all informative words in those classes, after
the complete enumeration establishes that the other words exclude no binding.

## Retained records

- summary.json records parameters, exact counts, closure obligations and the run.
- case-counts.csv gives one row per session count.
- minimum-cover-counts.csv gives every exhaustively checked subset cardinality.
- complete-enumeration.json.gz retains every permutation, request and short word,
  its excluded members under both observations, all caller-specific profiles and
  the standard covers with their disjoint first-exclusion memberships.

All request and permutation references in the compressed file are zero based;
row and credential numbers are one based. For an excluded member, shortest_word
is a list of request indices. A null shortest_word denotes a matching member.
The corresponding positive cases have separately checked closure obligations.
"""
    if arguments.verify_retained is not None:
        retained = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        require(set(retained) == set(result), "summary fields differ")
        for field in ("status", "parameters", "totals", "cases", "interpretation"):
            require(retained[field] == result[field], f"summary {field} differs")
        require(isinstance(retained["started_utc"], str)
                and isinstance(retained["elapsed_seconds"], (int, float))
                and retained["elapsed_seconds"] >= 0, "recorded run metadata is invalid")
        verify_csv(output / "case-counts.csv", cases)
        verify_csv(output / "minimum-cover-counts.csv", subsets)
        with gzip.open(output / "complete-enumeration.json.gz", "rt", encoding="utf-8") as stream:
            require(json.load(stream) == evidence, "complete retained enumeration differs")
        require((output / "README.md").read_text(encoding="utf-8") == readme,
                "recorded reproduction instructions or count table differ")
    else:
        output.mkdir(parents=True, exist_ok=False)
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        write_csv(output / "case-counts.csv", cases)
        write_csv(output / "minimum-cover-counts.csv", subsets)
        with (output / "complete-enumeration.json.gz").open("wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
                compressed.write((json.dumps(evidence, separators=(",", ":")) + "\n").encode("utf-8"))
        (output / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps({"status": result["status"], "sizes": arguments.sizes,
                      "mode": "verified-retained-records" if arguments.verify_retained is not None else "recorded-new-run",
                      "totals": result["totals"], "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
