"""Independent finite-state search for session costs from partial stores.

This script imports no AuthRefine semantics, production checker, proof audit,
native collector or application. All emitted results are finite equation
checks. A zero-cost reset is explicitly either to the initially supplied
store or to the complete store. No native execution is claimed.
"""

from collections import deque
from functools import lru_cache
from heapq import heappop, heappush
from itertools import permutations
import argparse
import gzip
import json
import sys
from math import factorial
from pathlib import Path
import time


@lru_cache(None)
def family(n, anchors):
    return tuple(p for p in permutations(range(n))
                 if all(p[i] == i for i in range(n) if anchors & (1 << i)))


def reference(p, store, op, observed):
    action, i = op
    if action == 'remove':
        after = store & ~(1 << i)
        return after, (True, after, None) if observed == 'row' else (True, after)
    row = p.index(i)
    allow = bool(store & (1 << row))
    return store, ((allow, store, row if allow else None)
                   if observed == 'row' else (allow, store))


def physical(n, store, op, observed):
    action, i = op
    if action == 'remove':
        after = store & ~(1 << i)
        return after, (True, after, None) if observed == 'row' else (True, after)
    allow = bool(store & (1 << i))
    return store, ((allow, store, i if allow else None)
                   if observed == 'row' else (allow, store))


def expected(n, anchors, initial, observed, reset):
    free = [i for i in range(n) if not anchors & (1 << i)]
    m = len(free)
    absent = sum(not initial & (1 << i) for i in free)
    if m <= 1:
        return {'requests': 0, 'resets': 0}
    if absent >= 2 and reset != 'complete':
        return None
    if observed == 'row':
        count = m - 1
    else:
        count = 2 * (m - 1) - int(0 < absent < m)
    return {'requests': count, 'resets': int(absent >= 2)}


def construction(n, anchors, initial, observed, reset):
    """Closed-form upper-bound word, independent of the search below."""
    free = [i for i in range(n) if not anchors & (1 << i)]
    present = [i for i in free if initial & (1 << i)]
    absent = [i for i in free if not initial & (1 << i)]
    if len(free) <= 1:
        return []
    if len(absent) >= 2 and reset != 'complete':
        return None
    if observed == 'row':
        if len(absent) >= 2:
            return [('reset', -1)] + [('lookup', i) for i in free[:-1]]
        return [('lookup', i) for i in present[:len(free)-1]]
    if not absent:
        return [(action, i) for i in free[:-1] for action in ('remove', 'lookup')]
    if not present:
        return [('reset', -1)] + [(action, i) for i in free[:-1]
                                  for action in ('remove', 'lookup')]
    word = [('lookup', absent[-1])]
    word += [(action, i) for i in present[:-1] for action in ('remove', 'lookup')]
    if len(absent) >= 2:
        word += [('reset', -1)]
        word += [(action, i) for i in absent[:-1] for action in ('remove', 'lookup')]
    return word


def search(n, initial, observed, reset):
    """Exact Dijkstra search over physical stores and surviving fixed permutations.

    Edges have lexicographic cost (requests, resets). Resets cost no request;
    tracking them as the secondary coordinate prevents zero-cost cycles and
    checks the minimum reset count among request-optimal strategies. The
    search does not import or consult the construction or expected formula.
    It searches the identity branch of every deterministic/adaptive strategy:
    each history fixes a next choice; identical (store, survivor) states have
    identical available futures.
    """
    bindings = tuple(permutations(range(n)))
    identity = tuple(range(n))
    inverse = tuple(tuple(p.index(j) for j in range(n)) for p in bindings)
    all_members = (1 << len(bindings)) - 1
    initial_state = (initial, all_members)
    distance = {initial_state: (0, 0)}
    parent = {}
    heap = [(0, 0, initial, all_members)]
    expanded = 0
    transitions = 0
    while heap:
        requests, resets, store, survivors = heappop(heap)
        state = (store, survivors)
        if distance[state] != (requests, resets):
            continue
        expanded += 1
        if survivors == 1:  # itertools lists identity first
            word = []
            cursor = state
            while cursor != initial_state:
                cursor, op = parent[cursor]
                word.append(op)
            word.reverse()
            return {'requests': requests, 'resets': resets,
                    'word': word, 'expanded': expanded,
                    'discovered': len(distance), 'transitions': transitions}
        edges = []
        for i in range(n):
            if store & (1 << i):
                edges.append(((store & ~(1 << i), survivors), (1, 0), ('remove', i)))
            retained = 0
            physical_allow = bool(store & (1 << i))
            for index, inv in enumerate(inverse):
                if not survivors & (1 << index):
                    continue
                row = inv[i]
                candidate_allow = bool(store & (1 << row))
                agrees = (candidate_allow == physical_allow)
                if observed == 'row' and candidate_allow and physical_allow:
                    agrees = row == i
                if agrees:
                    retained |= 1 << index
            if retained != survivors:
                edges.append(((store, retained), (1, 0), ('lookup', i)))
        if reset != 'none':
            restored = (1 << n) - 1 if reset == 'complete' else initial
            if store != restored:
                edges.append(((restored, survivors), (0, 1), ('reset', -1)))
        for next_state, weight, op in edges:
            transitions += 1
            cost = (requests + weight[0], resets + weight[1])
            if cost < distance.get(next_state, (float('inf'), float('inf'))):
                distance[next_state] = cost
                parent[next_state] = (state, op)
                heappush(heap, (*cost, *next_state))
    return {'requests': None, 'resets': None, 'word': None,
            'expanded': expanded, 'discovered': len(distance), 'transitions': transitions}


def check_constructions():
    counts = {'initial_anchor_contexts': 0, 'binding_trace_checks': 0,
              'request_comparisons': 0, 'construction_checks': 0,
              'infeasibility_contexts': 0}
    rows = []
    for n in range(2, 7):
        for anchors in range(1 << n):
            bindings = family(n, anchors)
            free = [i for i in range(n) if not anchors & (1 << i)]
            for initial in range(1 << n):
                counts['initial_anchor_contexts'] += 1
                for observed in ('projected', 'row'):
                    for reset in ('none', 'initial', 'complete'):
                        want = expected(n, anchors, initial, observed, reset)
                        word = construction(n, anchors, initial, observed, reset)
                        if want is None:
                            if word is not None:
                                raise ValueError('Unexpected word for infeasible case')
                            absent = [i for i in free if not initial & (1 << i)]
                            if len(absent) < 2:
                                raise ValueError('Infeasibility certificate absent')
                            beta = list(range(n));a,b = absent[:2]
                            beta[a],beta[b] = beta[b],beta[a]
                            # Every reachable store is a subset of initial;
                            # inspect all of them and every request. Reset-to-
                            # initial remains inside this same closed domain.
                            for store in range(1 << n):
                                if store & ~initial:
                                    continue
                                for i in range(n):
                                    for action in ('remove', 'lookup'):
                                        actual = physical(n, store, (action,i), observed)
                                        proposed = reference(tuple(beta), store, (action,i), observed)
                                        if actual != proposed:
                                            raise ValueError(('Infeasibility failure', n, anchors, initial))
                            counts['infeasibility_contexts'] += 1
                            continue
                        if word is None:
                            raise ValueError('Missing attainable construction')
                        request_count = sum(op[0] != 'reset' for op in word)
                        reset_count = sum(op[0] == 'reset' for op in word)
                        if (request_count, reset_count) != (want['requests'], want['resets']):
                            raise ValueError(('cost',n,anchors,initial,observed,reset))
                        survivors = []
                        for beta in bindings:
                            counts['binding_trace_checks'] += 1
                            actual_store = candidate_store = initial
                            agrees = True
                            for op in word:
                                if op[0] == 'reset':
                                    actual_store = candidate_store = ((1 << n)-1 if reset == 'complete' else initial)
                                    continue
                                counts['request_comparisons'] += 1
                                actual_store, actual = physical(n, actual_store, op, observed)
                                candidate_store, candidate = reference(beta, candidate_store, op, observed)
                                if actual != candidate:
                                    agrees = False
                            if agrees:
                                survivors.append(beta)
                        if survivors != [tuple(range(n))]:
                            raise ValueError(('Not singleton identity',n,anchors,initial,observed,reset,survivors))
                        counts['construction_checks'] += 1
                rows.append({'n': n, 'anchors': anchors, 'initial': initial,
                             'free_rows': len(free),
                             'absent_free_rows': sum(not initial & (1 << i) for i in free)})
    return {'totals': counts, 'contexts': rows}


def matches_full_language(n, initial, binding, observed, removals):
    """Independent reachable reference/target product for a fixed binding."""
    agenda = deque([(initial, initial)])
    visited = {(initial, initial)}
    compared = 0
    while agenda:
        concrete, proposed = agenda.popleft()
        for i in range(n):
            for action in (('lookup', 'remove') if removals else ('lookup',)):
                compared += 1
                next_concrete, actual = physical(n, concrete, (action, i), observed)
                next_proposed, candidate = reference(binding, proposed, (action, i), observed)
                if actual != candidate:
                    return False, len(visited), compared
                after = (next_concrete, next_proposed)
                if after not in visited:
                    visited.add(after)
                    agenda.append(after)
        # Reset-to-initial is a return to the product's start and adds no
        # previously unvisited state. Both no-reset and reset-initial language
        # equality are therefore classified by this same closed product.
    return True, len(visited), compared


def check_surviving_families():
    rows = []
    compared = 0
    product_states = 0
    binding_products = 0
    profiles = [('projected_lookup', 'projected', False),
                ('projected_mutating', 'projected', True),
                ('selected_row_lookup', 'row', False),
                ('selected_row_mutating', 'row', True)]
    for n in range(2, 7):
        for anchors in range(1 << n):
            bindings = family(n, anchors)
            free = [i for i in range(n) if not anchors & (1 << i)]
            for initial in range(1 << n):
                present = [i for i in free if initial & (1 << i)]
                absent = [i for i in free if not initial & (1 << i)]
                row = {'n': n, 'anchors': anchors, 'initial': initial,
                       'free_present':len(present),'free_absent':len(absent),
                       'profiles': {}}
                for label, observed, removals in profiles:
                    survivors = []
                    for binding in bindings:
                        matches, states, edges = matches_full_language(n, initial, binding, observed, removals)
                        binding_products += 1
                        product_states += states
                        compared += edges
                        if matches:
                            survivors.append(binding)
                    if label == 'projected_lookup':
                        want_members = [beta for beta in bindings if {beta[i] for i in present} == set(present)]
                        want_count = factorial(len(present)) * factorial(len(absent))
                    else:
                        want_members = [beta for beta in bindings if all(beta[i] == i for i in present)]
                        want_count = factorial(len(absent))
                    if survivors != want_members or len(survivors) != want_count:
                        raise ValueError(('family mismatch', n, anchors, initial, label))
                    row['profiles'][label] = {'survivors':len(survivors),
                                              'exact_family_checked':True}
                rows.append(row)
    return {'contexts': len(rows), 'profiles': len(rows)*len(profiles),
            'binding_products':binding_products,'visited_product_states':product_states,
            'transition_comparisons':compared,'rows':rows}


def audit():
    """Recompute the complete finite audit, with deterministic scientific output."""
    cases = []
    for n in range(1,5):
        for initial in range(1 << n):
            for observed in ('projected','row'):
                for reset in ('none','initial','complete'):
                    actual = search(n, initial, observed, reset)
                    want = expected(n, 0, initial, observed, reset)
                    expected_cost = (None,None) if want is None else (want['requests'],want['resets'])
                    if (actual['requests'],actual['resets']) != expected_cost:
                        raise ValueError(('search discrepancy',n,initial,observed,reset,want,actual))
                    cases.append({'n':n, 'initial':initial, 'observed':observed,'reset':reset,**actual})
    finite = check_constructions()
    surviving = check_surviving_families()
    result = {'status':'PASS','new_native_executions':0,
              'search_cases':len(cases),'search':cases,**finite,
              'surviving_family_audit':surviving}
    return result


def read(path):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key: " + key)
            value[key] = item
        return value
    def invalid(value):
        raise ValueError("nonfinite JSON constant: " + value)
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path, help="write a fresh result file; existing files are rejected")
    destination.add_argument("--verify", type=Path, help="recompute and compare every scientific field with a retained result")
    args = parser.parse_args()
    if args.output is not None and args.output.exists():
        parser.error("output already exists; choose a fresh file")
    start = time.monotonic()
    result = audit()
    if args.verify is not None:
        if encoded(read(args.verify)) != encoded(result):
            raise ValueError("retained finite audit differs from independent recomputation")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        raw = encoded(result)
        # Exclusive creation prevents a concurrent run from overwriting evidence.
        with args.output.open("xb") as stream:
            stream.write(gzip.compress(raw, mtime=0) if args.output.suffix == ".gz" else raw + b"\n")
    print(json.dumps({"status": result["status"], "search_cases": result["search_cases"],
                      "search_expanded": sum(row["expanded"] for row in result["search"]),
                      "search_transitions": sum(row["transitions"] for row in result["search"]),
                      **result["totals"],
                      "surviving_family_audit": {key: value for key, value in result["surviving_family_audit"].items() if key != "rows"},
                      "new_native_executions": 0,
                      "elapsed_seconds": time.monotonic() - start}, indent=2))


if __name__ == "__main__":
    main()
