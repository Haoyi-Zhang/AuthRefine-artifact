#!/usr/bin/env python3
"""Independent request-cost audit for the distinct-token session equations.

Only the Python standard library is imported.  Finite trace checks and
transposition invariants are separate from the general mathematical proof.
Existing native edges are read, never reacquired.  No production semantics,
search routine, fixture generator, ORM, or native adapter is imported.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import csv
from datetime import datetime, timezone
import gzip
import io
from itertools import permutations
import json
from math import factorial
from pathlib import Path
import sys
from time import perf_counter

sys.dont_write_bytecode = True
ARTIFACT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def members(size, anchors):
    free = tuple(i for i in range(size) if i not in anchors)
    answer = []
    for values in permutations(free):
        binding = list(range(size))
        for row, credential in zip(free, values):
            binding[row] = credential
        answer.append(tuple(binding))
    return free, answer


def reference_step(present, request, binding):
    kind, named = request
    if kind == "remove":
        after = present if named is None else present & ~(1 << named)
        return "allow", after, None
    selected = next((row for row, credential in enumerate(binding)
                     if credential == named and present & (1 << row)), None)
    return ("allow" if selected is not None else "deny"), present, selected


def physical_step(present, request):
    kind, named = request
    if kind == "remove":
        return "allow", present if named is None else present & ~(1 << named), None
    found = named is not None and bool(present & (1 << named))
    return ("allow" if found else "deny"), present, named if found else None


def trace(size, word, binding=None, initial=None):
    present = (1 << size) - 1 if initial is None else initial
    result = []
    for request in word:
        row = (physical_step(present, request) if binding is None else
               reference_step(present, request, binding))
        result.append(row)
        present = row[1]
    return result


def first_difference(actual, expected, rich=False):
    require(len(actual) == len(expected), "trace lengths differ")
    for position, (left, right) in enumerate(zip(actual, expected), 1):
        if (left if rich else left[:2]) != (right if rich else right[:2]):
            return position
    return None


def request_record(request):
    kind, index = request
    return {"action": kind, "resource": "missing" if index is None else
            f"{'row' if kind == 'remove' else 'credential'}-{index + 1}"}


def observations(rows):
    return [[decision, present, None if selected is None else selected + 1]
            for decision, present, selected in rows]


def certificate(size, anchors, free, support, kind):
    """A fixed alternative plus a closed store/action domain, not a strategy search."""
    unseen = [i for i in free if i not in support]
    require(len(unseen) >= 2, "lower-bound certificate needs two untouched coordinates")
    swapped = unseen[:2]
    binding = list(range(size))
    binding[swapped[0]], binding[swapped[1]] = binding[swapped[1]], binding[swapped[0]]
    all_present = (1 << size) - 1
    if kind == "deletion-support":
        mutable = set(anchors) | set(support)
        required_present = sum(1 << i for i in free if i not in support)
        stores = [state for state in range(1 << size)
                  if state & required_present == required_present]
        actions = ([('remove', i) for i in sorted(mutable)] +
                   [('lookup', i) for i in range(size)] + [('remove', None), ('lookup', None)])
        rich = False
    else:
        require(kind == "query-support", "unknown certificate kind")
        stores = list(range(1 << size))
        actions = ([('remove', i) for i in range(size)] +
                   [('lookup', i) for i in sorted(set(anchors) | set(support))] +
                   [('remove', None), ('lookup', None)])
        rich = True
    domain = set(stores)
    require(all_present in domain, "fresh store or reset escapes certificate domain")
    checked = 0
    for state in stores:
        for request in actions:
            left = reference_step(state, request, binding)
            right = physical_step(state, request)
            require((left if rich else left[:2]) == (right if rich else right[:2]),
                    f"invalid {kind} transposition certificate")
            require(left[1] == right[1] and left[1] in domain,
                    "certificate domain is not transition closed")
            checked += 1
    return {
        "sessions": size, "anchors": [i + 1 for i in anchors],
        "kind": kind, "used_free_coordinates": [i + 1 for i in support],
        "untouched_transposition": [i + 1 for i in swapped],
        "alternative_row_to_credential": [i + 1 for i in binding],
        "store_masks": stores, "requests": [request_record(r) for r in actions],
        "observation": "selected-row" if rich else "decision-presence",
        "transition_comparisons": checked, "closed_under_fresh_store_reset": True,
    }


def audit_case(size, anchor_mask):
    anchors = tuple(i for i in range(size) if anchor_mask & (1 << i))
    free, family = members(size, anchors)
    m = len(free)
    count = max(m - 1, 0)
    require(len(family) == factorial(m), "anchored family cardinality")
    word = [request for i in free[:count] for request in (('remove', i), ('lookup', i))]
    rich_word = [('lookup', i) for i in free[:count]]
    pairs = [[('remove', i), ('lookup', i)] for i in free[:count]]
    physical = trace(size, word)
    rich_physical = trace(size, rich_word)
    pair_physical = [trace(size, pair) for pair in pairs]
    profiles = []
    strata = Counter()
    short_comparisons = 0
    for member, binding in enumerate(family):
        continuous = trace(size, word, binding)
        rich = trace(size, rich_word, binding)
        paired = [trace(size, pair, binding) for pair in pairs]
        first = first_difference(continuous, physical)
        rich_first = first_difference(rich, rich_physical, rich=True)
        pair_failures = [i + 1 for i, (left, right) in enumerate(zip(paired, pair_physical))
                         if first_difference(left, right) is not None]
        short_comparisons += len(pairs)
        moved = [i + 1 for i, row in enumerate(free) if binding[row] != row]
        first_moved = min(moved) if moved else None
        expected = 2 * first_moved if first_moved is not None else None
        require(first == expected and rich_first == first_moved,
                "continuous or selected-row first-exclusion position")
        require((min(pair_failures) if pair_failures else None) == first_moved,
                "reset and continuous tests disagree on their first stratum")
        require((first is None) == (binding == tuple(range(size))),
                "constructed trace does not retain exactly identity")
        if first is not None:
            strata[first] += 1
        # The cumulative trace's later failure must not become a global length claim.
        for request in ([('remove', i) for i in range(size)] +
                        [('lookup', i) for i in range(size)] +
                        [('remove', None), ('lookup', None)]):
            require(reference_step((1 << size) - 1, request, binding)[:2] ==
                    physical_step((1 << size) - 1, request)[:2],
                    "a projected single request unexpectedly distinguishes")
        profiles.append({
            "permutation_index": member,
            "row_to_credential": [i + 1 for i in binding],
            "continuous_first_difference": first,
            "first_reset_test": min(pair_failures) if pair_failures else None,
            "selected_row_first_difference": rich_first,
            "individual_shortest_projected_length": 2 if moved else None,
            "individual_shortest_selected_row_length": 1 if moved else None,
            "continuous_reference_observations": observations(continuous),
            "selected_row_reference_observations": observations(rich),
            "reset_pair_reference_observations": [observations(t) for t in paired],
        })
    expected_strata = {2 * i: factorial(m - i + 1) - factorial(m - i)
                       for i in range(1, m)}
    require(dict(strata) == expected_strata, "cumulative factorial strata")

    # This word contains every informative query available after its single
    # deletion. Repetition and reordering cannot add information to that state.
    one_removal = []
    for removed in range(size):
        maximal = [('remove', removed)] + [('lookup', i) for i in range(size)]
        target = trace(size, maximal)
        survivors = [i for i, binding in enumerate(family)
                     if first_difference(trace(size, maximal, binding), target) is None]
        expected_members = [i for i, binding in enumerate(family) if binding[removed] == removed]
        require(survivors == expected_members, "maximal one-removal information")
        expected_count = factorial(m) if removed in anchors else factorial(m - 1)
        require(len(survivors) == expected_count, "one-removal stabilizer cardinality")
        one_removal.append({"removed_row": removed + 1,
                            "word": [request_record(r) for r in maximal],
                            "surviving_permutation_indices": survivors})

    certificates = []
    for support_mask in range(1 << m):
        support = tuple(free[i] for i in range(m) if support_mask & (1 << i))
        if len(support) >= m - 1:
            continue
        for kind in ("deletion-support", "query-support"):
            certificates.append(certificate(size, anchors, free, support, kind))
    row = {
        "sessions": size, "anchor_mask": anchor_mask,
        "anchors": [i + 1 for i in anchors], "free_coordinates": m,
        "family_members": len(family),
        "minimum_projected_requests": 2 * count,
        "minimum_selected_row_requests": count,
        "minimum_one_removal_runs": count,
        "continuous_first_exclusions": [{"request_position": i, "bindings": strata[i]}
                                        for i in sorted(strata)],
        "short_pair_binding_comparisons": short_comparisons,
        "maximal_one_removal_binding_comparisons": len(family) * size,
        "deletion_support_certificates": len(certificates) // 2,
        "query_support_certificates": len(certificates) // 2,
        "certificate_transition_comparisons": sum(c['transition_comparisons'] for c in certificates),
    }
    evidence = {"sessions": size, "anchor_mask": anchor_mask,
                "anchors": row['anchors'], "initial_store_mask": (1 << size) - 1,
                "continuous_word": [request_record(r) for r in word],
                "continuous_physical_observations": observations(physical),
                "selected_row_word": [request_record(r) for r in rich_word],
                "selected_row_physical_observations": observations(rich_physical),
                "reset_words": [[request_record(r) for r in pair] for pair in pairs],
                "reset_physical_observations": [observations(t) for t in pair_physical],
                "profiles": profiles, "maximal_one_removal_words": one_removal}
    return row, evidence, certificates


def bfs_minimum(size):
    """Exhaust the shorter reachable belief states for one uninterrupted word."""
    family = tuple(permutations(range(size)))
    agreeing = {}
    for deleted in range(1 << size):
        for credential in range(size):
            agreeing[deleted, credential] = sum(
                1 << i for i, binding in enumerate(family)
                if bool(deleted & (1 << binding.index(credential))) ==
                bool(deleted & (1 << credential)))
    start = (0, (1 << len(family)) - 1)
    queue = deque([(start, ())])
    seen = {start}
    expanded = Counter()
    discovered = Counter({0: 1})
    while queue:
        (deleted, surviving), word = queue.popleft()
        expanded[len(word)] += 1
        if surviving == 1:
            require(len(word) == 2 * (size - 1), "belief BFS differs from the request lower bound")
            return {"sessions": size, "minimum_requests": len(word),
                    "witness": [request_record(r) for r in word],
                    "states_expanded": sum(expanded.values()), "states_discovered": len(seen),
                    "expanded_by_depth": dict(sorted(expanded.items())),
                    "discovered_by_depth": dict(sorted(discovered.items())),
                    "all_smaller_depths_exhausted": True,
                    "reset_allowed": False}
        for kind in ('remove', 'lookup'):
            for i in range(size):
                next_state = ((deleted | (1 << i), surviving) if kind == 'remove' else
                              (deleted, surviving & agreeing[deleted, i]))
                if next_state not in seen:
                    seen.add(next_state)
                    require(len(seen) <= 100_000, "small BFS state envelope exceeded")
                    next_word = word + ((kind, i),)
                    discovered[len(next_word)] += 1
                    queue.append((next_state, next_word))
    raise ValueError("no single trace certifies identity")


def native_edge_reconciliation(native_path, sizes):
    raw = json.loads(gzip.decompress(native_path.read_bytes()))
    by_size = {row['sessions']: row for row in raw}
    require(len(by_size) == len(raw), "duplicate retained native size")
    cases = []
    for size in sizes:
        require(size in by_size, "native baseline size unavailable")
        graph = by_size[size]['baseline']
        machine = graph['machine']
        edges = {(edge['from_state'], edge['input_index']): (i, edge)
                 for i, edge in enumerate(graph['edges'])}
        require(len(edges) == len(graph['edges']), "duplicate retained native cell")
        present = (1 << size) - 1
        initial_rows = next(e['observation']['before_rows'] for e in graph['edges']
                            if e['from_state'] == present)
        require([r['id'] for r in initial_rows] == list(range(1, size + 1)),
                "native row names differ")
        require(len({r['token'] for r in initial_rows}) == size and
                len({r['user_id'] for r in initial_rows}) == 1,
                "native initial tokens or user do not satisfy the theorem")
        token_by_row = {r['id']: r['token'] for r in initial_rows}
        current_rows = initial_rows
        records = []
        for position, request in enumerate(
                [r for i in range(size - 1) for r in (('remove', i), ('lookup', i))], 1):
            named = request_record(request)
            wire_request = ['client', named['resource'], named['action']]
            index = machine['alphabet'].index(wire_request)
            edge_index, edge = edges[present, index]
            observed = edge['observation']
            expected = physical_step(present, request)
            require(observed['request'] == wire_request and observed['before_state'] == present,
                    "native edge starts at another request or store")
            require(observed['before_rows'] == current_rows, "native row records do not compose")
            removed = request[1] + 1 if request[0] == 'remove' else None
            expected_rows = [r for r in current_rows if r['id'] != removed]
            require(observed['after_rows'] == expected_rows, "native full row effect differs")
            selected = None if observed['selected_record'] is None else observed['selected_record']['id'] - 1
            require((observed['decision'], observed['after_state'], selected) == expected,
                    "native decision/presence/identity differs from the constructed trace")
            expected_user = None if expected[2] is None else next(
                r['user_id'] for r in initial_rows if r['id'] == expected[2] + 1)
            require(observed['returned_user_id'] == expected_user, "native returned user differs")
            require(observed['removed_ids'] == ([removed] if removed is not None else []) and
                    observed['store_changed'] == (expected_rows != current_rows),
                    "native removal metadata differs")
            require(observed['token_argument'] == token_by_row[request[1] + 1],
                    "native token argument differs")
            q = graph['states'].index(present)
            target_edge = machine['transitions'][q][index]
            require((target_edge[0], machine['observations'][target_edge[1]]) == expected[:2],
                    "retained machine edge disagrees with native row observation")
            require(len(edge['prefix']) == len(edge['prefix_observations']),
                    "native acquisition prefix is incomplete")
            records.append({"request_position": position, "retained_edge_index": edge_index,
                            "from_store_mask": present, "input_index": index,
                            "acquired_prefix_indices": edge['prefix'],
                            "observation": observed})
            present, current_rows = expected[1], observed['after_rows']
        cases.append({"sessions": size, "constructed_requests": len(records),
                      "retained_edges": records, "full_row_continuity": True})
    return {"status": "passed", "cases": cases,
            "constructed_words": len(cases),
            "retained_edge_uses": sum(c['constructed_requests'] for c in cases),
            "new_native_executions": 0,
            "scope": "Read-only composition of existing native baseline graph cells. Full before/after rows agree between adjacent selected cells. This is not a new continuous native replay."}


def scope_controls():
    identity = (0, 1, 2, 3)
    cycle = (1, 2, 3, 0)
    word = [('remove', 0), ('lookup', 1)]
    require(first_difference(trace(4, word, cycle), trace(4, word)) == 2,
            "restricted-family counterexample changed")
    require(all(identity[i] != cycle[i] for i in range(4)), "correlated control has an anchor")
    require(first_difference(trace(2, [('lookup', 0)], (1, 0), initial=2),
                             trace(2, [('lookup', 0)], initial=2)) == 1,
            "inherited-store counterexample changed")
    return {
        "restricted_family": {"row_to_credential": [[1, 2, 3, 4], [2, 3, 4, 1]],
                              "common_fixed_coordinates": [],
                              "covering_word": [request_record(r) for r in word],
                              "requests": 2,
                              "interpretation": "The full remaining permutation family is necessary for the lower bound."},
        "inherited_store": {"sessions": 2, "initial_store_mask": 2,
                            "word": [request_record(('lookup', 0))], "requests": 1,
                            "interpretation": "The residual-cost theorem starts from the complete store, not a previously deleted store."}}


def csv_text(rows):
    fields = ('sessions', 'anchor_mask', 'free_coordinates', 'family_members',
              'minimum_projected_requests', 'minimum_selected_row_requests',
              'minimum_one_removal_runs', 'deletion_support_certificates',
              'query_support_certificates', 'certificate_transition_comparisons')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def readme(summary):
    t = summary['totals']
    bfs_sizes = summary['parameters']['bfs_sizes']
    bfs_scope = ("The finite BFS checks one uninterrupted word only, at sizes " +
                 ", ".join(map(str, bfs_sizes)) + "." if bfs_sizes else
                 "No finite BFS is requested at these sizes.")
    return f"""# Session request-cost evidence

This independent standard-library audit checks the operational theorem in
`proofs/session-operation-cost.md`. The complete initial store, correct supplied
anchors, and full permutation family on unanchored coordinates are explicit.

The retained run covers {t['anchored_cases']} anchor sets and
{t['anchored_binding_cases']} anchored binding cases. It checks
{t['lower_bound_certificates']} transposition certificates with
{t['certificate_transition_comparisons']} closed-domain transition comparisons.
{bfs_scope}
The general reset/adaptive lower bound follows from the invariant proof;
these finite computations do not enumerate unbounded strategies.

The native record reconciliation uses {t['retained_native_edge_uses']} already
acquired graph edges for {t['native_constructed_words']} constructed words.
There are no new native executions and no new timing benchmark.

From `artifact/`, verify without writing:

```sh
PYTHONDONTWRITEBYTECODE=1 python proofs/audit_session_operation_cost.py --verify-retained results/session-operation-cost
```

To save an independent repetition, use `--output` with a new directory; an
existing destination is rejected before computation. `--native-results` can
select the retained session-correspondence directory. Verification recomputes
all scientific fields, full profile/certificate records, BFS, native-edge
reconciliation, CSV and this README; only the recorded start and elapsed time
are ignored. The native input and retained evidence are never overwritten.

`summary.json` records parameters and counts; `case-counts.csv` has one row per
anchor set; `complete-evidence.json.gz` retains every anchored permutation,
constructed reference trace, one-removal survivor set and transposition
certificate; `bfs.json` records the finite searches; and
`native-edge-reconciliation.json` records the exact existing cells used.
Rows and credentials in JSON labels are one based. Store masks use bit i-1
for row i. A null first difference means agreement on that word.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[2, 3, 4, 5, 6], choices=range(2, 7))
    parser.add_argument('--native-results', type=Path, default=ARTIFACT / 'results/session-correspondence')
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument('--output', type=Path)
    destination.add_argument('--verify-retained', type=Path)
    args = parser.parse_args()
    if args.sizes != sorted(set(args.sizes)):
        parser.error('sizes must be sorted and distinct')
    if args.output is not None and args.output.exists():
        parser.error('choose a new output directory; existing evidence is never overwritten')
    native_path = args.native_results.resolve() / 'native-observations.json.gz'
    if not native_path.is_file():
        parser.error('retained native-observations.json.gz is required')
    if args.output is not None and args.output.resolve().is_relative_to(args.native_results.resolve()):
        parser.error('output must not be inside the retained native input directory')
    native_before = (native_path.read_bytes(), native_path.stat().st_mtime_ns)
    began = datetime.now(timezone.utc).isoformat()
    clock = perf_counter()
    rows, cases, certificates = [], [], []
    for size in args.sizes:
        for anchor_mask in range(1 << size):
            row, evidence, certs = audit_case(size, anchor_mask)
            rows.append(row)
            cases.append(evidence)
            certificates.extend(certs)
    bfs = [bfs_minimum(size) for size in args.sizes if size <= 4]
    native = native_edge_reconciliation(native_path, args.sizes)
    controls = scope_controls()
    require(native_before == (native_path.read_bytes(), native_path.stat().st_mtime_ns),
            'retained native input changed during read-only reconciliation')
    totals = {
        'anchored_cases': len(rows),
        'anchored_binding_cases': sum(r['family_members'] for r in rows),
        'short_pair_binding_comparisons': sum(r['short_pair_binding_comparisons'] for r in rows),
        'maximal_one_removal_binding_comparisons': sum(r['maximal_one_removal_binding_comparisons'] for r in rows),
        'deletion_support_certificates': sum(r['deletion_support_certificates'] for r in rows),
        'query_support_certificates': sum(r['query_support_certificates'] for r in rows),
        'lower_bound_certificates': len(certificates),
        'certificate_transition_comparisons': sum(r['certificate_transition_comparisons'] for r in rows),
        'bfs_searches': len(bfs), 'native_constructed_words': native['constructed_words'],
        'retained_native_edge_uses': native['retained_edge_uses'], 'new_native_executions': 0,
    }
    summary = {
        'status': 'passed', 'started_utc': began, 'elapsed_seconds': perf_counter() - clock,
        'parameters': {'sizes': args.sizes, 'all_correct_anchor_subsets': True,
                       'family': 'every permutation fixing the supplied anchors',
                       'binding_direction': 'row to credential',
                       'initial_store': 'all rows present, distinct unexpired tokens, one returned user',
                       'lifecycle': 'fixed clock, nonrenewing lookup, named-row removal',
                       'reset': 'restore the complete store; preserve binding and accumulated observations',
                       'adaptive_scope': 'sound identity-certification branch; not identification of an arbitrary unknown permutation',
                       'request_cost': 'one per lookup or removal; resets and supplied anchor discovery excluded',
                       'bfs_sizes': [r['sessions'] for r in bfs], 'bfs_state_envelope': 100_000,
                       'dependencies': 'Python standard library only', 'production_modules_imported': []},
        'totals': totals, 'cases': rows,
        'results': {'projected_minimum_requests': '2 * max(n - k - 1, 0)',
                    'selected_row_minimum_requests': 'max(n - k - 1, 0)',
                    'one_removal_minimum_nonempty_runs': 'max(n - k - 1, 0)',
                    'unrestricted_nonempty_runs': 'one if n-k >= 2, otherwise zero',
                    'continuous_first_failure_positions': '2i, with (m-i+1)! - (m-i)! newly excluded bindings',
                    'individual_shortest_projected_witness': 'two requests for each nonidentity member',
                    'native_input_bytes_and_mtime_unchanged': True},
        'scope_controls': controls,
        'interpretation': [
            'Transposition certificates are finite instances of closed observation invariants, not an enumeration of all adaptive strategies.',
            'Used deletion/query supports accumulate across the whole certification history and survive resets.',
            'The cumulative covering trace is different from an individually shortest counterexample.',
            'One-removal words may have arbitrary finite length; all post-removal lookups still only fix the removed correspondence.',
            'Anchors are correct and given before a fresh complete-store experiment. Arbitrary correlated subfamilies and inherited partial stores can have lower costs.',
            'Native-edge reconciliation composes retained observations and does not constitute a new continuous native run.',
        ],
    }
    evidence = {'cases': cases, 'lower_bound_certificates': certificates, 'scope_controls': controls}
    payloads = {'summary.json': summary, 'complete-evidence.json.gz': evidence,
                'bfs.json': bfs, 'native-edge-reconciliation.json': native}
    if args.verify_retained is not None:
        target = args.verify_retained
        for name, actual in payloads.items():
            path = target / name
            expected = json.loads(gzip.decompress(path.read_bytes()) if name.endswith('.gz') else path.read_bytes())
            if name == 'summary.json':
                for obj in (expected, actual):
                    obj.pop('started_utc', None)
                    obj.pop('elapsed_seconds', None)
            # JSON round trip normalizes integer dictionary keys in BFS layers.
            require(expected == json.loads(json.dumps(actual)), f'retained {name} differs')
        require((target / 'case-counts.csv').read_text() == csv_text(rows), 'retained CSV differs')
        require((target / 'README.md').read_text() == readme(summary), 'retained README differs')
    else:
        target = args.output
        target.mkdir(parents=True, exist_ok=False)
        for name, value in payloads.items():
            encoded = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
            (target / name).write_bytes(gzip.compress(encoded, mtime=0) if name.endswith('.gz') else encoded)
        (target / 'case-counts.csv').write_text(csv_text(rows), encoding='utf-8')
        (target / 'README.md').write_text(readme(summary), encoding='utf-8')
    print(json.dumps({'status': 'passed', 'operation': 'read-only verification' if args.verify_retained else 'new evidence',
                      'totals': totals}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
