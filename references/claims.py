#!/usr/bin/env python3
"""Reconcile cited counts and costs from the retained scientific records.

This command reads raw profiles, source observations and process measurements.
It does not acquire new observations, rerun a checker or time an algorithm.
The independent semantic experiments have their own reproduction commands in
claim_evidence_ledger.csv. All paths below are part of the standalone artifact.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ARTIFACT = HERE.parent
TOTAL = ('per-binding-product', 'per-binding-target', 'shared-target', 'support-indexed')
CALLERS = ('unrestricted', 'lookup-only', 'one-removal')
METHODS = TOTAL + tuple(f'protocol-{algorithm}/{caller}' for caller in CALLERS
                       for algorithm in ('scan', 'grouped'))
CLOCKS = ('diagnosis_wall_ns', 'diagnosis_cpu_ns', 'serialization_ns')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def equal(actual, expected, message):
    require(actual == expected, f'{message}: found {actual!r}, expected {expected!r}')


def read(relative):
    path = ARTIFACT / relative
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)


def lines(relative):
    with gzip.open(ARTIFACT / relative, 'rt', encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(typed_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def profile_length(row):
    """Check retained first-failure shape, including the empty-word case."""
    require(type(row['equivalent']) is bool, 'Profile equivalence must be Boolean')
    length = row['length']
    if row['equivalent']:
        require(length is None and row['indices'] is None and row['trace'] is None,
                'A matching profile contains a failure witness')
        return 0
    require(type(length) is int and length >= 0, 'Invalid excluded-profile length')
    equal(len(row['indices']), length, 'Witness request count')
    equal(len(row['trace']), length, 'Witness replay count')
    if length:
        require(all(step['compared_equal'] for step in row['trace'][:-1]),
                'Witness continued after an earlier recorded failure')
        require(row['trace'][-1]['compared_equal'] is False, 'Witness has no final recorded failure')
        require(all(step['binding'] == row['binding'] for step in row['trace']),
                'Witness replay changed the fixed binding')
    return length


def classification(profiles):
    matches = sum(row['equivalent'] for row in profiles)
    return 'all' if matches == len(profiles) else 'none' if matches == 0 else 'some'


def overlapping_supports():
    base = 'results/support-overlap/'
    summary, inputs = read(base + 'summary.json'), read(base + 'inputs.json')
    classes, lengths, sizes = Counter(), Counter(), Counter()
    targets, unique = defaultdict(set), {}
    family_rows = bindings = replays = 0
    for row in lines(base + 'profiles.jsonl.gz'):
        family_rows += 1
        require(row['family_mask'] not in targets[row['target']], 'Repeated overlap family')
        targets[row['target']].add(row['family_mask'])
        expected = [binding for i, binding in enumerate(inputs['all_bindings'])
                    if row['family_mask'] & (1 << i)]
        equal([p['binding'] for p in row['profiles']], expected, 'Overlap supplied family')
        equal(len(row['profiles']), row['bindings'], 'Overlap profile count')
        equal(classification(row['profiles']), row['classification'], 'Overlap classification')
        classes[row['classification']] += 1
        sizes[str(row['bindings'])] += 1
        bindings += row['bindings']
        for profile in row['profiles']:
            key = (row['target'], encoded(profile['binding']))
            serial = encoded(profile)
            equal(unique.setdefault(key, serial), serial, 'Fixed answer across overlap families')
            lengths['infinity' if profile['length'] is None else str(profile['length'])] += 1
            replays += profile_length(profile)
    equal(len(targets), 65, 'Overlap targets')
    require(all(masks == set(range(1, 256)) for masks in targets.values()), 'Incomplete overlap family domain')
    for actual, field in [(family_rows, 'family_diagnoses'), (bindings, 'binding_profiles_checked'),
                          (replays, 'witness_replay_rows_checked'), (dict(classes), 'family_classifications'),
                          (dict(lengths), 'binding_shortest_lengths'), (dict(sizes), 'families_by_cardinality')]:
        equal(actual, summary[field], 'Overlap ' + field)
    equal((family_rows, bindings, replays, len(unique)), (16575, 66560, 127744, 520), 'Overlap denominators')
    controls = summary['mutation_controls']
    require(len(controls) == 3 and all(row['detected'] and row['detection_stage'] == 'independent-comparison'
                                      for row in controls), 'Overlap executed fault controls')
    return {'family_contexts': family_rows, 'distinct_target_binding_pairs': len(unique),
            'binding_rows': bindings, 'replay_rows': replays, 'family_classifications': dict(classes),
            'shortest_lengths': dict(lengths), 'executed_fault_controls': len(controls)}


def retained_family_cost():
    variation = read('results/timing-variation/variation.json')
    trials = read('results/family-cost/trials.json')
    grouped, output_agreement = defaultdict(list), defaultdict(set)
    records = 0
    for process in trials:
        equal(process['exit_code'], 0, 'Family-cost process exit')
        for row in process['records']:
            records += 1
            # These retained output identities are comparisons, not new source
            # provenance. The public reconciliation report contains no digest.
            output_agreement[row['id']].add(row['output_sha256'])
            for metric in CLOCKS:
                grouped[row['id'], process['mode'], metric].append(row[metric])
    equal((records, len(trials), len(output_agreement), len(grouped)), (1064, 28, 38, 456),
          'Family-cost retained denominators')
    for actual, key in [(records, 'timed_case_records'), (len(trials), 'processes'),
                        (len(output_agreement), 'cases'), (len(grouped), 'metric_summaries_reconciled')]:
        equal(actual, variation[key], 'Family-cost ' + key)
    require(all(len(values) == 1 for values in output_agreement.values()), 'Different retained complete outputs')
    checked = 0
    for case in variation['records']:
        for method, metrics in case['methods'].items():
            for metric, reported in metrics.items():
                values = grouped[case['id'], method, metric]
                equal(len(values), 7, 'Family-cost repetitions')
                equal(values, reported['samples_ns'], 'Family-cost raw samples')
                q1, _, q3 = statistics.quantiles(values, n=4, method='inclusive')
                expected = {'median_ns': statistics.median(values), 'q1_ns': q1, 'q3_ns': q3,
                            'minimum_ns': min(values), 'maximum_ns': max(values)}
                for name, value in expected.items():
                    require(math.isclose(reported[name], value, rel_tol=1e-12), 'Incorrect family-cost ' + name)
                checked += 1
        product = grouped[case['id'], 'per-binding-product', 'diagnosis_wall_ns']
        indexed = grouped[case['id'], 'support-indexed', 'diagnosis_wall_ns']
        expected = {'median_ratio': statistics.median(product) / statistics.median(indexed),
                    'observed_envelope_lower': min(product) / max(indexed),
                    'observed_envelope_upper': max(product) / min(indexed)}
        for name, value in expected.items():
            require(math.isclose(case['product_over_indexed'][name], value, rel_tol=1e-12),
                    'Incorrect descriptive ratio envelope')
    equal(checked, 456, 'Family-cost metric summaries')
    return {'case_records': records, 'processes': len(trials), 'cases': len(output_agreement),
            'metric_summaries': checked, 'ratio_envelopes': len(variation['records']),
            'scope': 'Observed sample variation on the recorded host; no new measurement or confidence interval.'}


def protocol_grouping():
    base = 'results/protocol-grouping/'
    summary, domain = read(base + 'summary.json'), read(base + 'domain.json')
    outcomes, tiny_keys = Counter(), set()
    tiny_rows = 0
    for row in lines(base + 'one-request-cases.jsonl.gz'):
        key = (row['target'], row['caller'], tuple(row['references']))
        require(key not in tiny_keys, 'Repeated one-request case')
        tiny_keys.add(key)
        status = row.get('classification', row.get('admission'))
        outcomes[status] += 1
        if 'classification' in row:
            tiny_rows += len(row['lengths'])
            matches = sum(value is None for value in row['lengths'])
            expected = 'all' if matches == len(row['lengths']) else 'none' if matches == 0 else 'some'
            equal(status, expected, 'One-request classification')
            equal(row['replay_evaluations'], sum(value or 0 for value in row['lengths']), 'One-request replay count')
    equal({'family_cases': len(tiny_keys), 'classified_binding_rows': tiny_rows, 'outcomes': dict(outcomes)},
          summary['one_request'], 'One-request summary')
    equal((len(tiny_keys), tiny_rows), (18225, 17820), 'One-request denominators')
    outcomes, lengths, callers = Counter(), Counter(), defaultdict(Counter)
    contexts, unique = defaultdict(set), {}
    cases = rows = replays = 0
    for row in lines(base + 'overlap-cases.jsonl.gz'):
        cases += 1
        context = (row['target'], row['caller'])
        require(row['family_mask'] not in contexts[context], 'Repeated caller family')
        contexts[context].add(row['family_mask'])
        status = row.get('classification', row.get('admission'))
        outcomes[status] += 1
        callers[row['caller']][status] += 1
        if 'classification' not in row:
            require(status in {'missing', 'inactive'}, 'Unknown admission disposition')
            continue
        expected = [binding for index, binding in enumerate(domain['bindings'])
                    if row['family_mask'] & (1 << index)]
        equal([p['binding'] for p in row['profiles']], expected, 'Caller supplied family')
        equal(len(row['profiles']), row['bindings'], 'Caller binding count')
        equal(classification(row['profiles']), status, 'Caller classification')
        matches = [p['binding'] for p in row['profiles'] if p['equivalent']]
        equal(row['matching_family'], matches, 'Caller matching family')
        equal(row['matching_bindings'], len(matches), 'Caller matching count')
        equal(row['failing_bindings'], len(expected) - len(matches), 'Caller excluded count')
        local = Counter('infinity' if p['length'] is None else str(p['length']) for p in row['profiles'])
        equal(dict(local), row['strata'], 'Caller shortest strata')
        finite = [p['length'] for p in row['profiles'] if p['length'] is not None]
        equal(row['shortest_failure'], min(finite) if finite else None, 'Caller shortest family failure')
        lengths.update(local)
        rows += len(expected)
        for profile in row['profiles']:
            key = context + (encoded(profile['binding']),)
            serial = encoded(profile)
            equal(unique.setdefault(key, serial), serial, 'Fixed caller answer across supplied subfamilies')
            replays += profile_length(profile)
    expected_contexts = {(row['id'], caller) for row in domain['targets'] for caller in domain['callers']}
    equal(set(contexts), expected_contexts, 'Caller target/protocol domain')
    require(all(masks == set(range(1, 256)) for masks in contexts.values()), 'Incomplete caller subfamily domain')
    derived = {'target_tables': len(domain['targets']), 'caller_protocols': len(domain['callers']),
               'nonempty_subfamilies': 255, 'family_cases': cases,
               'classified_binding_rows_across_families': rows,
               'distinct_admitted_target_caller_binding_answers': len(unique),
               'replay_rows_across_families': replays, 'outcomes': dict(outcomes),
               'shortest_lengths_across_families': dict(lengths),
               'by_caller': {caller: dict(counts) for caller, counts in callers.items()}}
    equal(derived, summary['overlapping_supports'], 'Caller grouping complete summary')
    equal((cases, rows, replays, len(unique)), (123930, 371712, 572416, 2904), 'Caller grouping denominators')
    require(summary['all_comparisons_passed'] is True, 'Caller semantic comparisons failed')
    controls = summary['controls']
    equal({row['fault'] for row in controls}, {'omitted_support', 'stale_cell_result', 'erased_caller_history',
                                             'classify_before_full_admission'}, 'Caller fault controls')
    require(all(row['detected'] for row in controls), 'Undetected caller fault control')
    return {'one_request': summary['one_request'], 'overlapping_supports': derived,
            'executed_fault_controls': len(controls)}


def native_sessions():
    base = 'results/session-correspondence/'
    cases = read(base + 'inputs.json.gz')
    profiles = {row['id']: row for row in read(base + 'profiles.json.gz')}
    native = {row['sessions']: row for row in read(base + 'native-observations.json.gz')}
    replay = {row['id']: row for row in read(base + 'native-witness-replay.json.gz')}
    requests = {row['id']: row for row in read(base + 'native-replay-inputs.json')}
    diagnosis, replay_summary = read(base + 'diagnosis.json'), read(base + 'native-replay-summary.json')
    summaries = {row['id']: row for row in diagnosis['cases']}
    replay_summaries = {row['id']: row for row in replay_summary['cases']}
    equal(len(cases), 10, 'Native study case count')
    equal(set(native), set(range(2, 7)), 'Native study session counts')
    ids = {row['id'] for row in cases}
    require(len(ids) == 10, 'Duplicate native case')
    for collection in (profiles, replay, requests, summaries, replay_summaries):
        equal(set(collection), ids, 'Native case coverage')
    comparisons = anchor_profiles = anchor_bindings = words = operations = excluded = 0
    baseline_states = baseline_edges = control_edges = 0
    for case in cases:
        name, size, arm = case['id'], case['sessions'], case['arm']
        graph, result, summary = native[size][arm], profiles[name], summaries[name]
        family = [dict(zip([f'credential-for-row-{i}' for i in range(1, size + 1)], values))
                  for values in itertools.permutations([f'credential-{i}' for i in range(1, size + 1)])]
        equal(case['family'], family, 'Explicit permutation family')
        equal(result['profiles'], case['expected'], 'Native retained complete profiles')
        equal(set(result['profiles']), set(METHODS), 'Native profile methods')
        equal(case['machine'], graph['machine'], 'Native source table supplied to diagnosis')
        equal(set(graph['states']), set(range(1 << size)) if arm == 'baseline' else {(1 << size) - 1},
              'Native reached store states')
        alphabet = graph['machine']['alphabet']
        edges = {(edge['from_state'], edge['input_index']): edge for edge in graph['edges']}
        equal(len(edges), len(graph['edges']), 'Distinct acquired table cells')
        equal(set(edges), {(state, index) for state in graph['states'] for index in range(len(alphabet))},
              'Complete native table cells')
        prefix_count = 0
        for edge in graph['edges']:
            prefix_count += len(edge['prefix'])
            equal(len(edge['prefix']), len(edge['prefix_observations']), 'Native reaching-prefix records')
            observation = edge['observation']
            equal(observation['before_state'], edge['from_state'], 'Native cell source state')
            equal(observation['request'], alphabet[edge['input_index']], 'Native cell request')
            expected_edge = [observation['decision'], graph['states'].index(observation['after_state'])]
            equal(graph['machine']['transitions'][graph['states'].index(edge['from_state'])][edge['input_index']],
                  expected_edge, 'Native observation/table correspondence')
            state = (1 << size) - 1
            for index, observed in zip(edge['prefix'] + [edge['input_index']],
                                       edge['prefix_observations'] + [observation]):
                equal(observed['before_state'], state, 'Native acquisition prefix continuity')
                equal(observed['request'], alphabet[index], 'Native acquisition prefix request')
                equal(sum(1 << (row['id'] - 1) for row in observed['before_rows']), state, 'Native before-store encoding')
                state = observed['after_state']
                equal(sum(1 << (row['id'] - 1) for row in observed['after_rows']), state, 'Native after-store encoding')
        equal(prefix_count, graph['prefix_operations'], 'Native prefix-operation total')
        equal(graph['source_operations'], prefix_count + len(edges), 'Native source-operation total')
        for field, actual in [('family_members', len(family)), ('cartesian_family_members', size ** size),
                              ('native_states', len(graph['states'])), ('native_edges', len(edges)),
                              ('native_prefix_operations', prefix_count),
                              ('native_rich_record_checks', graph['source_operations'])]:
            equal(summary[field], actual, 'Native summary ' + field)
        if arm == 'baseline':
            baseline_edges += len(edges)
            baseline_states += len(graph['states'])
        else:
            equal(arm, 'omit-delete', 'Native control identity')
            control_edges += len(edges)
        for method, rows in result['profiles'].items():
            equal([row['binding'] for row in rows], family, 'Native complete-profile order')
            comparisons += len(rows)
            for row in rows:
                profile_length(row)
            if method in TOTAL:
                equal(rows, result['profiles']['shared-target'], 'Equal total-method output')
        for caller in CALLERS:
            rows = result['profiles']['protocol-grouped/' + caller]
            equal(rows, result['profiles']['protocol-scan/' + caller], 'Equal caller-method output')
            matching = sum(row['equivalent'] for row in rows)
            finite_lengths = {row['length'] for row in rows if not row['equivalent']}
            expected_matching = len(family) if caller == 'lookup-only' else int(arm == 'baseline')
            expected_length = None if caller == 'lookup-only' else 2 if arm == 'baseline' else 1
            equal(matching, expected_matching, 'Native caller viability')
            equal(finite_lengths, set() if expected_length is None else {expected_length}, 'Native caller failure lengths')
            equal(summary['caller_outcomes'][caller], {'matching': matching, 'excluded': len(family) - matching,
                                                       'shortest_excluded_length': expected_length}, 'Native caller summary')
            richer = result['selected_identity_profiles'][caller]
            equal([row['binding'] for row in richer], family, 'Selected-row profile family')
            richer_matches = sum(row['equivalent'] for row in richer)
            equal(richer_matches, 0 if arm == 'omit-delete' and caller != 'lookup-only' else 1,
                  'Selected-row observed identity viability')
            equal({row['length'] for row in richer if not row['equivalent']}, {1}, 'Selected-row failure length')
            equal(richer_matches, summary['selected_identity_matching'][caller], 'Selected-row summary')
        equal(len(result['anchored_family_profiles']), size, 'Anchored families per native case')
        anchor_summary = {row['name']: row for row in summary['anchored_families']}
        for anchor in result['anchored_family_profiles']:
            positions = [i for i, binding in enumerate(family)
                         if all(binding[key] == value for key, value in anchor['anchor'].items())]
            equal(set(anchor['profiles']), {'support-indexed', 'protocol-grouped/one-removal'}, 'Anchored methods')
            for method, rows in anchor['profiles'].items():
                equal(rows, [result['profiles'][method][position] for position in positions], 'Exact anchored restriction')
                anchor_profiles += 1
                anchor_bindings += len(rows)
            row = anchor_summary[anchor['name']]
            matches = sum(profile['equivalent'] for profile in anchor['profiles']['support-indexed'])
            equal(row, {'name': anchor['name'], 'anchor': anchor['anchor'], 'family_members': len(positions),
                        'matching': matches, 'excluded': len(positions) - matches, 'exact_restriction_check': True},
                  'Anchored summary')
        coverage = Counter(tuple(row['indices']) for row in result['profiles']['shared-target'] if not row['equivalent'])
        if arm == 'baseline':
            predicted_coverage = {
                (alphabet.index(['client', f'row-{i}', 'remove']),
                 alphabet.index(['client', f'credential-{i}', 'lookup'])):
                math.factorial(size - i + 1) - math.factorial(size - i)
                for i in range(1, size)
            }
            equal(dict(coverage), predicted_coverage, 'Native minimum short-test first-exclusion strata')
        equal(summary['witness_coverage'], [{'indices': list(word), 'requests': [alphabet[index] for index in word],
                                            'excluded_bindings': count} for word, count in sorted(coverage.items())],
              'Canonical first-witness buckets')
        equal(requests[name]['words'], [list(word) for word in sorted(coverage)], 'Requested distinct native words')
        native_words = replay[name]['words']
        equal([word['indices'] for word in native_words], requests[name]['words'], 'Executed distinct native words')
        case_operations = 0
        for word in native_words:
            equal(len(word['observations']), len(word['indices']), 'Native witness record count')
            equal(word['excluded_bindings_checked'], coverage[tuple(word['indices'])], 'Native witness bucket count')
            state = (1 << size) - 1
            for index, observation in zip(word['indices'], word['observations']):
                equal(observation, edges[state, index]['observation'], 'Native replay/acquisition observation agreement')
                state = observation['after_state']
            case_operations += len(word['observations'])
        equal(replay_summaries[name], {'id': name, 'distinct_native_words': len(native_words),
              'native_operations': case_operations, 'excluded_bindings_checked': sum(coverage.values()),
              'coverage': [{'indices': list(word), 'excluded_bindings': count} for word, count in sorted(coverage.items())]},
              'Native replay summary')
        words += len(native_words)
        operations += case_operations
        excluded += sum(coverage.values())
    equal((baseline_states, baseline_edges, control_edges), (124, 2808, 90), 'Native source denominators')
    equal((comparisons, anchor_profiles, anchor_bindings), (17440, 80, 1408), 'Native profile comparison denominators')
    for field, value in [('complete_profile_comparisons', comparisons), ('anchored_family_profiles', anchor_profiles),
                          ('anchored_binding_comparisons', anchor_bindings), ('baseline_edges', baseline_edges),
                          ('control_edges', control_edges)]:
        equal(diagnosis[field], value, 'Native diagnosis ' + field)
    equal((words, operations, excluded), (20, 35, 1739), 'Native witness denominators')
    for field, value in [('distinct_native_word_runs', words), ('native_operations', operations),
                          ('excluded_binding_replays_checked', excluded)]:
        equal(replay_summary[field], value, 'Native witness ' + field)
    acquisition, preparation = read(base + 'acquisition.json'), read(base + 'analysis-runtime.json')
    equal(sum(row['acquisition_wall_ns'] for row in acquisition['records']), acquisition['total_acquisition_wall_ns'],
          'Native acquisition duration arithmetic')
    for row in acquisition['records']:
        equal(row['source_operations'], sum(native[row['sessions']][arm]['source_operations']
                                            for arm in ('baseline', 'omit-delete')), 'Acquisition source-operation count')
    equal({row['sessions']: row['bindings'] for row in preparation['family_preparation']},
          {size: math.factorial(size) for size in range(2, 7)}, 'Separate family preparation')
    equal({row['id'] for row in preparation['case_preparation']}, ids, 'Separate case preparation')
    return {'applications': 1, 'selected_methods': 2, 'cases': len(cases), 'baseline_stores': baseline_states,
            'baseline_cells': baseline_edges, 'introduced_control_cells': control_edges,
            'complete_profile_binding_comparisons': comparisons, 'anchored_family_profiles': anchor_profiles,
            'anchored_binding_comparisons': anchor_bindings, 'distinct_native_word_runs': words,
            'native_witness_operations': operations, 'excluded_bindings_checked_against_native_words': excluded,
            'retained_acquisition_wall_ns': acquisition['total_acquisition_wall_ns'],
            'scope': 'One source interface at five cardinalities; overlapping cells are not pooled as new applications.'}


def session_short_test_bounds():
    """Reconcile the independent short-word matrices and their finite counts."""
    base = 'results/session-distinguishability/'
    summary = read(base + 'summary.json')
    matrices = read(base + 'complete-enumeration.json.gz')
    equal(summary['status'], 'passed', 'Independent session audit status')
    equal(summary['parameters']['sizes'], list(range(2, 7)), 'Independent session audit sizes')
    equal(summary['parameters']['production_modules_imported'], [], 'Independent audit module boundary')
    equal(summary['parameters']['native_executions'], 0, 'Independent audit execution denominator')
    equal([row['sessions'] for row in matrices], list(range(2, 7)), 'Short-word matrix case order')
    counts = {row['sessions']: row for row in summary['cases']}
    totals = Counter()
    for matrix in matrices:
        size = matrix['sessions']
        count = counts[size]
        permutations = matrix['row_to_credential_permutations']
        equal(permutations, [list(row) for row in itertools.permutations(range(1, size + 1))],
              'Complete independent permutation order')
        alphabet = matrix['requests']
        words = matrix['words']
        expected_words = [list(word) for length in range(3)
                          for word in itertools.product(range(len(alphabet)), repeat=length)]
        equal([row['request_indices'] for row in words], expected_words, 'Complete ordered short words')
        word_map = {tuple(row['request_indices']): row for row in words}
        for row in words:
            removals = sum(alphabet[index]['action'] == 'remove' for index in row['request_indices'])
            expected_callers = ['unrestricted']
            if removals <= 1:
                expected_callers.append('one-removal')
            if removals == 0:
                expected_callers.append('lookup-only')
            equal(row['admitted_callers'], expected_callers, 'Short-word caller membership')
            for observation in ('decision_presence_excluded', 'selected_row_excluded'):
                values = row[observation]
                require(values == sorted(set(values)) and all(0 < i < len(permutations) for i in values),
                        'Invalid short-word exclusion set')
        covered = set()
        equal(len(matrix['standard_covers']), size - 1, 'Constructive short-test cover size')
        for number, cover in enumerate(matrix['standard_covers'], 1):
            expected_count = math.factorial(size - number + 1) - math.factorial(size - number)
            projected = set(word_map[tuple(cover['decision_presence_word'])]['decision_presence_excluded'])
            richer = set(word_map[tuple(cover['selected_row_word'])]['selected_row_excluded'])
            equal(projected, richer, 'Equal exclusion sets for the two observations')
            equal(cover['newly_excluded_permutation_indices'], sorted(projected - covered),
                  'Independent first-exclusion membership')
            equal((cover['test_number'], cover['new_exclusions'], cover['factorial_difference']),
                  (number, expected_count, expected_count), 'Independent factorial strata')
            covered.update(projected)
        equal(covered, set(range(1, len(permutations))), 'Complete constructive exclusion cover')
        equal(len(matrix['profiles']), len(permutations), 'Independent complete profile rows')
        for index, profile in enumerate(matrix['profiles']):
            equal((profile['permutation_index'], profile['row_to_credential']),
                  (index, permutations[index]), 'Independent fixed binding')
            for observation, column, length in (
                    ('decision-presence', 'decision_presence_excluded', 2),
                    ('selected-row', 'selected_row_excluded', 1)):
                for caller in ('unrestricted', 'one-removal', 'lookup-only'):
                    result = profile[observation + '/' + caller]
                    candidates = [row['request_indices'] for row in words
                                  if caller in row['admitted_callers'] and index in row[column]]
                    expected = candidates[0] if candidates else None
                    equal(result['shortest_word'], expected, 'Independent canonical shortest word')
                    equal(result['matching'], expected is None, 'Independent profile classification')
                    equal(result['shortest_length'], None if expected is None else length,
                          'Independent shortest-word length')
        derived = {
            'permutations': len(permutations), 'excluded_permutations': len(permutations) - 1,
            'all_short_words': len(words), 'binding_word_comparisons': len(permutations) * len(words),
            'observation_comparisons': 2 * len(permutations) * len(words),
            'lookup_only_closure_cells': len(permutations) * (2 * size + 1),
            'identity_all_store_cells': (1 << size) * len(alphabet),
            'projected_cover_subsets_checked': sum(math.comb(size * size, k) for k in range(size - 1)),
            'identity_cover_subsets_checked': sum(math.comb(size, k) for k in range(size - 1)),
        }
        for field, value in derived.items():
            equal(count[field], value, 'Independent session count ' + field)
            totals[field] += value
        equal((count['minimum_projected_short_test_cover'], count['minimum_identity_single_test_cover']),
              (size - 1, size - 1), 'Independent minimum-cover bounds')
    for field, value in totals.items():
        equal(summary['totals'][field], value, 'Independent session total ' + field)
    return {'sizes': list(range(2, 7)), **dict(totals),
            'scope': 'Reconciles complete short-word matrices and profile fields. The separate direct-equation audit verifies all smaller covers; the proof establishes the result for arbitrary n. No native source executions are added.'}


def session_operation_cost():
    """Reconcile retained constructions and invariant domains, without running an oracle."""
    base = 'results/session-operation-cost/'
    summary = read(base + 'summary.json')
    evidence = read(base + 'complete-evidence.json.gz')
    bfs = read(base + 'bfs.json')
    native = read(base + 'native-edge-reconciliation.json')
    sizes = list(range(2, 7))
    equal(summary['status'], 'passed', 'Session operation-cost audit status')
    equal(summary['parameters']['sizes'], sizes, 'Operation-cost sizes')
    equal(summary['parameters']['bfs_sizes'], [2, 3, 4], 'Operation-cost BFS sizes')
    equal(summary['parameters']['production_modules_imported'], [], 'Operation-cost independent imports')
    equal(summary['parameters']['binding_direction'], 'row to credential', 'Operation-cost binding direction')
    equal(summary['parameters']['all_correct_anchor_subsets'], True, 'Complete anchor-subset domain')
    equal(summary['parameters']['family'], 'every permutation fixing the supplied anchors',
          'Operation-cost complete residual family')
    equal(summary['parameters']['initial_store'],
          'all rows present, distinct unexpired tokens, one returned user', 'Operation-cost initial-store premise')
    equal(summary['results']['projected_minimum_requests'], '2 * max(n - k - 1, 0)',
          'Projected operation-cost formula')
    equal(summary['results']['selected_row_minimum_requests'], 'max(n - k - 1, 0)',
          'Selected-row operation-cost formula')
    equal(summary['results']['one_removal_minimum_nonempty_runs'], 'max(n - k - 1, 0)',
          'One-removal run-count formula')
    equal(evidence['scope_controls'], summary['scope_controls'], 'Operation-cost scope controls')
    expected_keys = [(n, mask) for n in sizes for mask in range(1 << n)]
    equal([(c['sessions'], c['anchor_mask']) for c in evidence['cases']], expected_keys,
          'Complete operation-cost case order')

    def request(action, coordinate):
        return {'action': action, 'resource': 'missing' if coordinate is None else
                f"{'row' if action == 'remove' else 'credential'}-{coordinate}"}

    def difference(left, right, rich=False):
        equal(len(left), len(right), 'Retained operation-cost trace length')
        for step in left + right:
            require(isinstance(step, list) and len(step) == 3 and step[0] in ('allow', 'deny')
                    and type(step[1]) is int and (step[2] is None or type(step[2]) is int),
                    'Malformed retained operation-cost observation')
        return next((i for i, (a, b) in enumerate(zip(left, right), 1)
                     if (a if rich else a[:2]) != (b if rich else b[:2])), None)

    certificate_counts = defaultdict(Counter)
    certificate_keys = set()
    for item in evidence['lower_bound_certificates']:
        n, anchors = item['sessions'], item['anchors']
        require(n in sizes and anchors == sorted(set(anchors))
                and all(type(i) is int and 1 <= i <= n for i in anchors),
                'Operation-cost certificate anchors')
        anchor_mask = sum(1 << (i - 1) for i in anchors)
        free = [i for i in range(1, n + 1) if i not in anchors]
        support = item['used_free_coordinates']
        require(support == sorted(set(support)) and set(support) <= set(free)
                and len(support) <= len(free) - 2, 'Operation-cost lower-bound support')
        kind = item['kind']
        require(kind in ('deletion-support', 'query-support'), 'Operation-cost certificate kind')
        key = (n, anchor_mask, kind, tuple(support))
        require(key not in certificate_keys, 'Repeated operation-cost invariant certificate')
        certificate_keys.add(key)
        swapped = [i for i in free if i not in support][:2]
        alternate = list(range(1, n + 1))
        alternate[swapped[0] - 1], alternate[swapped[1] - 1] = swapped[1], swapped[0]
        equal(item['untouched_transposition'], swapped, 'Operation-cost fixed untouched pair')
        equal(item['alternative_row_to_credential'], alternate, 'Operation-cost fixed alternative')
        touched = sorted(set(anchors) | set(support))
        if kind == 'deletion-support':
            required = sum(1 << (i - 1) for i in free if i not in support)
            stores = [h for h in range(1 << n) if h & required == required]
            requests = ([request('remove', i) for i in touched] +
                        [request('lookup', i) for i in range(1, n + 1)])
            observation = 'decision-presence'
        else:
            stores = list(range(1 << n))
            requests = ([request('remove', i) for i in range(1, n + 1)] +
                        [request('lookup', i) for i in touched])
            observation = 'selected-row'
        requests += [request('remove', None), request('lookup', None)]
        equal(item['store_masks'], stores, 'Complete certificate store domain')
        equal(item['requests'], requests, 'Complete certificate request domain')
        equal(item['observation'], observation, 'Certificate observation strength')
        equal(item['closed_under_fresh_store_reset'], True, 'Certificate reset condition')
        transitions = len(stores) * len(requests)
        equal(item['transition_comparisons'], transitions, 'Certificate Cartesian transition count')
        certificate_counts[n, anchor_mask][kind] += 1
        certificate_counts[n, anchor_mask]['transitions'] += transitions

    derived_cases, constructions = [], []
    expected_certificate_keys = set()
    totals = Counter()
    unanchored = {}
    for case in evidence['cases']:
        n, anchor_mask = case['sessions'], case['anchor_mask']
        anchors = [i for i in range(1, n + 1) if anchor_mask & (1 << (i - 1))]
        free = [i for i in range(1, n + 1) if i not in anchors]
        m, pairs = len(free), max(len(free) - 1, 0)
        equal(case['anchors'], anchors, 'Operation-cost case anchors')
        equal(case['initial_store_mask'], (1 << n) - 1, 'Operation-cost complete starting store')
        family = []
        for values in itertools.permutations(free):
            binding = list(range(1, n + 1))
            for row, credential in zip(free, values):
                binding[row - 1] = credential
            family.append(binding)
        equal([p['row_to_credential'] for p in case['profiles']], family,
              'Complete anchored permutation family')
        reset_words = [[request('remove', i), request('lookup', i)] for i in free[:pairs]]
        continuous = [r for word in reset_words for r in word]
        rich_word = [request('lookup', i) for i in free[:pairs]]
        equal(case['continuous_word'], continuous, 'Continuous operation-cost construction')
        equal(case['reset_words'], reset_words, 'Fresh-pair operation-cost construction')
        equal(case['selected_row_word'], rich_word, 'Selected-row construction')
        present = (1 << n) - 1
        physical = []
        for i in free[:pairs]:
            present &= ~(1 << (i - 1))
            physical += [['allow', present, None], ['deny', present, None]]
        rich_physical = [['allow', (1 << n) - 1, i] for i in free[:pairs]]
        pair_physical = [[['allow', ((1 << n) - 1) & ~(1 << (i - 1)), None],
                          ['deny', ((1 << n) - 1) & ~(1 << (i - 1)), None]]
                         for i in free[:pairs]]
        equal(case['continuous_physical_observations'], physical, 'Constructed physical cumulative trace')
        equal(case['selected_row_physical_observations'], rich_physical, 'Constructed physical identity trace')
        equal(case['reset_physical_observations'], pair_physical, 'Constructed physical reset traces')
        first_counts = Counter()
        for index, profile in enumerate(case['profiles']):
            binding = family[index]
            equal(profile['permutation_index'], index, 'Operation-cost permutation index')
            first = difference(profile['continuous_reference_observations'], physical)
            rich_first = difference(profile['selected_row_reference_observations'], rich_physical, True)
            equal(len(profile['reset_pair_reference_observations']), pairs, 'Recorded reset-pair count')
            failures = [number for number, (source, target) in enumerate(
                        zip(profile['reset_pair_reference_observations'], pair_physical), 1)
                        if difference(source, target) is not None]
            first_pair = min(failures) if failures else None
            first_moved = next((i for i, row in enumerate(free, 1) if binding[row - 1] != row), None)
            equal(first, None if first_moved is None else 2 * first_moved,
                  'Cumulative first-exclusion location')
            equal((rich_first, first_pair), (first_moved, first_moved), 'Observation-specific first stratum')
            equal((profile['continuous_first_difference'], profile['selected_row_first_difference'],
                   profile['first_reset_test']), (first, rich_first, first_pair), 'Retained first-difference fields')
            equal((profile['individual_shortest_projected_length'], profile['individual_shortest_selected_row_length']),
                  (None, None) if first is None else (2, 1), 'Individual shortest lengths versus cumulative positions')
            if first is not None:
                first_counts[first] += 1
        strata = [{'request_position': 2 * i, 'bindings': math.factorial(m - i + 1) - math.factorial(m - i)}
                  for i in range(1, m)]
        equal(dict(first_counts), {s['request_position']: s['bindings'] for s in strata},
              'Cumulative factorial first-exclusion counts')
        equal([r['removed_row'] for r in case['maximal_one_removal_words']], list(range(1, n + 1)),
              'Maximal one-removal word coverage')
        for record in case['maximal_one_removal_words']:
            removed = record['removed_row']
            equal(record['word'], [request('remove', removed)] +
                  [request('lookup', i) for i in range(1, n + 1)], 'Maximal one-removal word')
            survivors = [i for i, binding in enumerate(family) if binding[removed - 1] == removed]
            equal(record['surviving_permutation_indices'], survivors, 'Maximal one-removal stabilizer')
        for used in range(max(m - 1, 0)):
            for support in itertools.combinations(free, used):
                for kind in ('deletion-support', 'query-support'):
                    expected_certificate_keys.add((n, anchor_mask, kind, support))
        cert = certificate_counts[n, anchor_mask]
        derived = {'sessions': n, 'anchor_mask': anchor_mask, 'anchors': anchors,
                   'free_coordinates': m, 'family_members': len(family),
                   'minimum_projected_requests': len(continuous),
                   'minimum_selected_row_requests': len(rich_word),
                   'minimum_one_removal_runs': len(reset_words),
                   'continuous_first_exclusions': strata,
                   'short_pair_binding_comparisons': len(family) * len(reset_words),
                   'maximal_one_removal_binding_comparisons': len(family) * len(case['maximal_one_removal_words']),
                   'deletion_support_certificates': cert['deletion-support'],
                   'query_support_certificates': cert['query-support'],
                   'certificate_transition_comparisons': cert['transitions']}
        derived_cases.append(derived)
        totals['anchored_cases'] += 1
        totals['anchored_binding_cases'] += len(family)
        for field in ('short_pair_binding_comparisons', 'maximal_one_removal_binding_comparisons',
                      'deletion_support_certificates', 'query_support_certificates', 'certificate_transition_comparisons'):
            totals[field] += derived[field]
        if not anchors:
            unanchored[n] = case
            constructions.append({'sessions': n, 'continuous_requests': len(continuous),
                                  'projected_one_removal_runs': len(reset_words),
                                  'selected_row_requests': len(rich_word), 'first_exclusions': strata,
                                  'individual_projected_shortest_length': 2,
                                  'individual_selected_row_shortest_length': 1})
    equal(certificate_keys, expected_certificate_keys, 'Complete lower-bound certificate support domain')
    equal(summary['cases'], derived_cases, 'Operation-cost complete case summary')
    with (ARTIFACT / base / 'case-counts.csv').open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        csv_rows = list(reader)
    equal(fields, ['sessions', 'anchor_mask', 'free_coordinates', 'family_members',
                   'minimum_projected_requests', 'minimum_selected_row_requests',
                   'minimum_one_removal_runs', 'deletion_support_certificates',
                   'query_support_certificates', 'certificate_transition_comparisons'],
          'Operation-cost complete CSV schema')
    equal(csv_rows, [{field: str(row[field]) for field in fields} for row in derived_cases],
          'Operation-cost CSV values and case order')

    equal([r['sessions'] for r in bfs], [2, 3, 4], 'Operation-cost finite BFS coverage')
    for record in bfs:
        n, length = record['sessions'], record['minimum_requests']
        equal(record['witness'], unanchored[n]['continuous_word'], 'BFS recorded optimal construction')
        equal(length, len(record['witness']), 'BFS recorded request length')
        equal(record['reset_allowed'], False, 'BFS uninterrupted scope')
        equal(record['all_smaller_depths_exhausted'], True, 'BFS smaller-depth assertion')
        expanded = {int(k): v for k, v in record['expanded_by_depth'].items()}
        discovered = {int(k): v for k, v in record['discovered_by_depth'].items()}
        equal(sum(expanded.values()), record['states_expanded'], 'BFS expanded count')
        equal(sum(discovered.values()), record['states_discovered'], 'BFS discovered count')
        require(all(expanded.get(i, 0) == discovered.get(i, 0) for i in range(length))
                and max(expanded) == length, 'BFS retained layers do not exhaust shorter depths')

    raw_native = {row['sessions']: row['baseline'] for row in
                  read('results/session-correspondence/native-observations.json.gz')}
    equal(native['status'], 'passed', 'Retained native-edge reconciliation status')
    equal([r['sessions'] for r in native['cases']], sizes, 'Retained native-edge size coverage')
    native_uses = 0
    for record in native['cases']:
        n = record['sessions']
        graph = raw_native[n]
        word = unanchored[n]['continuous_word']
        target = unanchored[n]['continuous_physical_observations']
        equal(len(record['retained_edges']), len(word), 'Retained native cumulative word length')
        equal(record['constructed_requests'], len(word), 'Retained native word request count')
        equal(record['full_row_continuity'], True, 'Retained native continuity assertion')
        present, previous_rows = (1 << n) - 1, None
        for position, (edge, operation, expected) in enumerate(zip(record['retained_edges'], word, target), 1):
            raw = graph['edges'][edge['retained_edge_index']]
            observed = edge['observation']
            equal(edge['request_position'], position, 'Retained native request position')
            equal((edge['from_store_mask'], edge['input_index'], edge['acquired_prefix_indices']),
                  (raw['from_state'], raw['input_index'], raw['prefix']), 'Native-edge raw record pointer')
            equal(observed, raw['observation'], 'Native-edge full original observation')
            equal(observed['request'], ['client', operation['resource'], operation['action']],
                  'Native-edge cumulative request')
            equal(observed['before_state'], present, 'Native-edge cumulative starting store')
            if previous_rows is not None:
                equal(observed['before_rows'], previous_rows, 'Native-edge full row continuity')
            selected = None if observed['selected_record'] is None else observed['selected_record']['id']
            equal([observed['decision'], observed['after_state'], selected], expected,
                  'Native-edge physical constructed observation')
            present, previous_rows = observed['after_state'], observed['after_rows']
            native_uses += 1
    equal(native['retained_edge_uses'], native_uses, 'Retained native edge-use count')
    equal(native['constructed_words'], len(native['cases']), 'Retained native word count')
    equal(native['new_native_executions'], 0, 'Native reconciliation does not execute application code')
    totals.update({'lower_bound_certificates': len(certificate_keys), 'bfs_searches': len(bfs),
                   'native_constructed_words': len(native['cases']), 'retained_native_edge_uses': native_uses,
                   'new_native_executions': 0})
    equal(dict(totals), summary['totals'], 'Operation-cost complete derived totals')
    equal((totals['anchored_cases'], totals['anchored_binding_cases'], totals['lower_bound_certificates'],
           totals['certificate_transition_comparisons'], native_uses),
          (124, 2369, 1290, 458854, 30), 'Operation-cost published denominators')
    return {'sizes': sizes, **dict(totals), 'unanchored_constructions': constructions,
            'bfs_minimum_requests': {str(r['sessions']): r['minimum_requests'] for r in bfs},
            'scope': 'Offline reconciliation of complete retained profiles, constructed words, invariant-domain descriptions, CSV, BFS layers and original native-edge pointers. The independent audit checks transition equations and runs the finite BFS; the proof establishes arbitrary-length adaptive/reset bounds. No production checker or native source is executed here.'}


def native_timing():
    base = 'results/session-correspondence/'
    cases = {row['id']: row for row in read(base + 'inputs.json.gz')}
    diagnosis = {row['id']: row for row in read(base + 'diagnosis.json')['cases']}
    trials, summary = read(base + 'timing-processes.json'), read(base + 'timing.json')
    grouped, process_keys = defaultdict(list), set()
    equal(len(trials), 70, 'Native timing processes')
    for trial in trials:
        key = (trial['repeat'], trial['method'])
        require(key not in process_keys, 'Repeated native timing process')
        process_keys.add(key)
        filename = f"repeat-{trial['repeat']}-{trial['method'].replace('/', '-')}.json"
        raw = read(base + 'timing-trials/' + filename)
        equal(raw, {'method': trial['method'], 'records': trial['records']}, 'Retained native process output')
        equal({row['id'] for row in trial['records']}, set(cases), 'Native timing case coverage')
        equal(len(trial['records']), len(cases), 'Native timing duplicate cases')
        for row in trial['records']:
            require(row['complete_output_equal'] is True, 'Timed complete profile disagrees')
            equal(row['output_bytes'], len(encoded(cases[row['id']]['expected'][trial['method']])), 'Timed complete output size')
            for field, value in diagnosis[row['id']]['work'][trial['method']].items():
                equal(row[field], value, 'Timed deterministic work ' + field)
            grouped[row['id'], trial['method']].append(row)
    equal(process_keys, {(repeat, method) for repeat in range(1, 8) for method in METHODS}, 'Native timing repetitions')
    metric_count = 0
    for case in summary['cases']:
        for method, reported in case['methods'].items():
            values = grouped[case['id'], method]
            equal(len(values), 7, 'Native timing samples')
            fixed = {key: value for key, value in values[0].items() if key not in CLOCKS}
            for row in values:
                equal({key: value for key, value in row.items() if key not in CLOCKS}, fixed, 'Native repeated work/output')
            for clock in CLOCKS:
                samples = [row[clock] for row in values]
                fixed[clock] = {'samples': samples, 'median': statistics.median(samples),
                                'minimum': min(samples), 'maximum': max(samples)}
                metric_count += 1
            equal(reported, fixed, 'Native timing full summary')
    equal((summary['fresh_processes'], summary['case_records'], summary['repeats'], metric_count),
          (70, 700, 7, 300), 'Native timing denominators')
    six = next(row for row in summary['cases'] if row['id'] == 'sessions-6-baseline')['methods']
    return {'processes': len(trials), 'case_records': 700, 'metric_summaries': metric_count,
            'six_session_medians_ns': {method: row['diagnosis_wall_ns']['median'] for method, row in six.items()},
            'scope': 'Diagnosis excludes separately recorded permutation preparation and native acquisition; ranges are observed extrema.'}


def retained_source_records():
    family = read('source_study/data/credential-family.json.gz')['cases']
    equal(len(family), 8, 'Credential profiles')
    equal(len({context for row in family for context in row['measured_cases']}), 1260, 'Credential contexts')
    equal(sum(row['diagnosis']['bindings'] for row in family), 112, 'Credential supplied hypotheses')
    equal(sum(row['diagnosis']['matching_bindings'] for row in family), 8, 'Credential viable hypotheses')
    equal(sum(row['diagnosis']['strata'].get('1', 0) for row in family), 104, 'Credential length-one exclusions')
    require(all(row['policy']['state'] == [] and row['machine']['state_names'] == []
                and row['machine']['observations'] == [0] and len(row['machine']['transitions']) == 1
                for row in family), 'Credential projection contains decoded application state')
    paired = read('results/direct-observation-pairs.json')
    equal({name: len(rows) for name, rows in paired['profiles'].items()},
          {'healthchecks_read': 54, 'healthchecks_resume': 24, 'pretix_read': 192, 'wger_creation': 2}, 'Paired observer cohorts')
    equal(sum(typed_equal(row['direct'], row['retained']) for rows in paired['profiles'].values() for row in rows),
          272, 'Retained typed observer agreement')
    prospective = {}
    for arm, complete, unknown in [('primary', 5, 55), ('secondary', 9, 0)]:
        rows = read('prospective_study/' + arm + '.json.gz')['rows']
        values = {'boundaries': len(rows), 'contexts': sum(row['contexts'] for row in rows),
                  'unknown_contexts': sum(row['unknown_contexts'] for row in rows),
                  'complete_boundaries': sum(row['status'] == 'contract_agreement' for row in rows)}
        equal(values, {'boundaries': 9, 'contexts': 78, 'unknown_contexts': unknown, 'complete_boundaries': complete},
              'Prospective retained ' + arm)
        prospective[arm] = values
    return {'credential_profiles': 8, 'credential_contexts': 1260, 'credential_bindings': 112,
            'credential_empty_decoded_state': True, 'paired_observer_rows': 272, 'prospective': prospective,
            'scope': 'Retained scoped observations and declared projections; no universal source-extraction conclusion.'}


def complete_symbolic_comparison():
    """Reconcile every measured output and clock without running a backend."""
    base = 'results/symbolic-comparison/'
    report, trials = read(base + 'summary.json'), read(base + 'trials.json')
    inputs, expected = read(base + 'inputs.json.gz'), read(base + 'profiles.json.gz')
    equal([r['id'] for r in inputs], [r['id'] for r in expected], 'Symbolic input/profile order')
    profiles = {row['id']: row['profiles'] for row in expected}
    tasks = {row['id']: row for row in inputs}
    equal(len(tasks), 158, 'Unified comparison task count')
    equal(dict(Counter(r['cohort'] for r in inputs)),
          {'family-cost': 38, 'session-correspondence': 40, 'native-policy-store': 80},
          'Unified comparison task cohorts')
    methods = ('per-binding-product', 'per-binding-target', 'scan', 'support-indexed', 'finite-domain', 'cudd')
    matrix, grouped = set(), defaultdict(list)
    for trial in trials:
        key = trial['repeat'], trial['method']
        require(key not in matrix, 'Duplicated unified comparison process')
        matrix.add(key)
        equal(trial['exit_code'], 0, 'Unified comparison worker exit')
        require(trial['complete_outputs_compared'] is True, 'Unchecked complete symbolic output')
        raw = read(base + trial['stdout'])
        require(all(trial[k] == v for k, v in raw.items()), 'Raw symbolic worker differs')
        equal((ARTIFACT / base / trial['stderr']).read_bytes(), b'', 'Symbolic worker stderr')
        selected = [r['id'] for r in inputs if r['protocol'] is None or trial['method'] in methods[2:]]
        equal([r['id'] for r in trial['records']], selected, 'Unified process task order')
        for row in trial['records']:
            payload = encoded(profiles[row['id']])
            equal(row['output_sha256'], hashlib.sha256(payload).hexdigest(), 'Unified complete replay identity')
            equal(row['output_bytes'], len(payload), 'Unified complete output bytes')
            equal(row['bindings'], len(profiles[row['id']]), 'Unified legal family size')
            equal(row['matching'], sum(r['equivalent'] for r in profiles[row['id']]), 'Unified matching count')
            equal(row['failure_lengths'], sorted({r['length'] for r in profiles[row['id']] if not r['equivalent']}),
                  'Unified shortest failure strata')
            grouped[row['id'], trial['method']].append(row)
    equal(matrix, {(repeat, method) for repeat in range(7) for method in methods}, 'Unified process matrix')
    equal((len(trials), len(grouped), sum(len(t['records']) for t in trials)),
          (42, 760, 5320), 'Unified measurement denominators')
    equal([r['id'] for r in report['records']], list(tasks), 'Unified summary order')
    for task in report['records']:
        expected_methods = methods if tasks[task['id']]['protocol'] is None else methods[2:]
        equal(set(task['methods']), set(expected_methods), 'Applicable methods in unified task')
        for method, summary in task['methods'].items():
            rows = grouped[task['id'], method]
            equal(len(rows), 7, 'Unified repetition count')
            for metric in CLOCKS:
                values = [r[metric] for r in rows]
                require(all(type(v) is int and v >= 0 for v in values), 'Unified timing units')
                equal(summary[metric], {'median': statistics.median(values), 'min': min(values),
                                        'max': max(values), 'samples': values}, 'Unified timing summary')
            for metric, value in summary.items():
                if metric in CLOCKS:
                    continue
                values = [r[metric] for r in rows]
                expected_value = ({'min': min(values), 'max': max(values), 'samples': values}
                                  if metric in ('symbolic_nodes', 'symbolic_peak_nodes') else values[0])
                if metric not in ('symbolic_nodes', 'symbolic_peak_nodes'):
                    require(all(v == values[0] for v in values), 'Unified deterministic work')
                equal(value, expected_value, 'Unified work summary')
    ratio_counts = {}
    for cohort in ('family-cost', 'session-correspondence', 'native-policy-store'):
        records = [r for r in report['records'] if r['cohort'] == cohort]
        ratio_counts[cohort] = {method: {
            'tasks': len(records),
            'lower_median_than_indexed': sum(r['methods'][method]['diagnosis_wall_ns']['median'] <
                                            r['methods']['support-indexed']['diagnosis_wall_ns']['median'] for r in records),
            'median_ratio_to_indexed': statistics.median(
                r['methods'][method]['diagnosis_wall_ns']['median'] /
                r['methods']['support-indexed']['diagnosis_wall_ns']['median'] for r in records)}
            for method in ('scan', 'finite-domain', 'cudd')}
    return {'tasks': 158, 'method_task_pairs': 760, 'processes': 42, 'timed_records': 5320,
            'cohorts': ratio_counts,
            'scope': 'The fixed tasks reuse source interfaces and caller languages; task fractions are not population estimates. All diagram construction and individual replay costs are timed.'}


def additional_native_records():
    identity = read('results/session-observation/identity-profiles.json.gz')
    rows = [r for case in identity for records in case['callers'].values() for r in records]
    excluded = [r for r in rows if not r['equivalent']]
    equal((len(identity), len(rows), len(excluded)), (10, 5232, 5212), 'Richer observation profile count')
    equal(sum(not r['trace'][-1]['identity_equal'] for r in excluded), 5202, 'Identity-determined exclusions')
    require(all(r['length'] == 1 and len(r['indices']) == len(r['trace']) == 1 and
                r['trace'][-1]['compared_equal'] is False for r in excluded), 'Richer first-failure evidence')
    identity_summary = read('results/session-observation/summary.json')
    equal((identity_summary['excluded_by_identity'], identity_summary['excluded_by_decision_or_state'],
           identity_summary['distinct_native_word_runs'], identity_summary['native_identity_operations']),
          (5202, 10, 35, 35), 'Richer observation native counts')
    native = read('results/native-policy-store/native-observations.json.gz')
    equal(len(native), 16, 'Native file-policy cases')
    equal(sum(len(g['edges']) for g in native), 3072, 'Native file-policy measured edges')
    equal(sum(sum(len(e['prefix']) for e in g['edges']) for g in native), 7440, 'Native file-policy prefix operations')
    require(all(len(g['states']) == 16 and len(g['edges']) == 192 for g in native), 'Native file-policy graph sizes')
    result = read('results/native-policy-store/validation.json')
    equal((result['native_witness_words'], result['native_witness_operations'], result['native_witness_binding_contract_checks']),
          (69, 101, 544), 'Native file-policy witness counts')
    return {'identity_binding_rows': len(rows), 'identity_excluded': len(excluded),
            'identity_only_exclusions': 5202, 'state_exclusions': 10,
            'richer_native_case_words': 35, 'policy_file_cases': len(native),
            'policy_file_edges': 3072, 'policy_file_prefix_operations': 7440,
            'policy_file_native_case_words': 69, 'policy_file_native_witness_operations': 101,
            'scope': 'Counts are retained native executions and repeated fixed-binding checks. Source methods and observation predicates are independently verified by their study commands.'}


def native_healthchecks_records():
    base = 'results/native-healthchecks/'
    summary = read(base + 'summary.json')
    protocol = read(base + 'protocol.json')
    reports = read(base + 'profiles.json.gz')
    controls = read(base + 'source-controls.json')
    replays = read(base + 'native-replay.json')
    arms = [row['arm'] for row in controls]
    equal(len(set(arms)), 5, 'Native HTTP source arms')
    equal(summary['status'], 'PASS', 'Native HTTP study status')
    require(summary['shared_target_correspondence_family'] is False and
            summary['complete_physical_reachability_claim'] is False,
            'Native HTTP scope changed')
    cases = [case for arm in arms for case in read(base + 'native/' + arm + '/observations.json.gz')['cases']]
    expected_grid = {(arm, form, api, config) for arm in arms
                     for form in protocol['key_formats'] for api in protocol['api_versions']
                     for config in protocol['configurations']}
    key = lambda row: (row['arm'], row['format'], row['api_version'], row['configuration'])
    equal({key(case) for case in cases}, expected_grid, 'Native HTTP configuration grid')
    equal([key(row) for row in reports], [key(case) for case in cases], 'Native HTTP report/source alignment')
    equal(len(cases), len(expected_grid), 'Native HTTP distinct cases')
    counts = Counter(native_cases=len(cases))
    first_lengths = defaultdict(list)
    for case, report in zip(cases, reports, strict=True):
        equal([row['operation'] for row in case['records']], protocol['operations'], 'Native HTTP request order')
        previous = case['initial']
        for row in case['records']:
            equal(row['before'], previous, 'Native HTTP physical store continuity')
            previous = row['after']
            counts['native_operations'] += 1
            counts['native_http_requests' if row['operation']['kind'] == 'http' else 'native_key_rotations'] += 1
            counts['native_sql_statements'] += len(row['sql'])
        expected_profiles = {(caller, mode) for caller in protocol['callers'] for mode in ('complete', 'http_status')}
        equal({(row['caller'], row['mode']) for row in report['profiles']}, expected_profiles,
              'Native HTTP observation/caller coverage')
        equal(len(report['profiles']), len(expected_profiles), 'Native HTTP unique profiles')
        for profile in report['profiles']:
            counts['configuration_profile_results'] += 1
            length = profile['length']
            require(profile['equivalent'] is (length is None), 'Native HTTP first-prefix classification')
            equal(profile['indices'], [] if length is None else list(range(length)),
                  'Native HTTP fixed-word prefix indices')
            equal(profile['admitted_operations'], protocol['callers'][profile['caller']],
                  'Native HTTP caller length')
            for component in profile['components']:
                equal(set(component['methods']), {'protocol-scan', 'protocol-grouped'},
                      'Native HTTP production methods')
                counts['production_component_comparisons'] += len(component['methods'])
            if case['configuration'] == 'identity' and profile['caller'] == 'lifecycle':
                first_lengths[case['arm'], profile['mode']].append(length)
    expected_first = {'original': (None, None), 'omit_readonly_context': (1, None),
                      'wrong_project_context': (1, 2), 'omit_pause_persistence': (15, 18),
                      'reject_readonly_get': (1, 1)}
    for arm, pair in expected_first.items():
        for mode, value in zip(('complete', 'http_status'), pair, strict=True):
            equal(first_lengths[arm, mode], [value] * 6, 'Native HTTP identity first-difference table')
    negative = {index for index, report in enumerate(reports) if any(not p['equivalent'] for p in report['profiles'])}
    equal({row['case_index'] for row in replays}, negative, 'Native HTTP replay coverage')
    equal(len(replays), len(negative), 'Native HTTP replay uniqueness')
    for replay in replays:
        case = read(base + replay['native_record'])['cases'][0]
        equal(key(case), key(cases[replay['case_index']]), 'Native HTTP fresh replay configuration')
        counts['native_replay_cases'] += 1
        counts['native_replay_operations'] += len(case['records'])
        counts['native_replay_http_requests'] += sum(r['operation']['kind'] == 'http' for r in case['records'])
        counts['native_replayed_witnesses'] += len(replay['checked_witnesses'])
    for field, value in counts.items():
        equal(summary[field], value, 'Native HTTP summary ' + field)
    equal((counts['native_cases'], counts['native_operations'], counts['native_http_requests'],
           counts['native_key_rotations'], counts['configuration_profile_results'],
           counts['production_component_comparisons'], counts['native_replay_cases'],
           counts['native_replay_operations'], counts['native_replayed_witnesses']),
          (120, 4440, 4200, 240, 720, 2400, 114, 480, 600), 'Native HTTP reported denominators')
    return {**dict(counts), 'identity_first_differences': {arm: list(pair) for arm, pair in expected_first.items()},
            'scope': 'One native API interface with separate targets for each concrete routing. Reconciles raw event counts, caller profiles and actual replay records; the source-study and independent audit commands additionally verify complete observations, encodings and physical SQLite files.'}


def native_healthchecks_tree_records():
    """Reconcile the complete bounded histories without importing the collector.

    Raw JSON observations, the stored constant reference tables, production
    witnesses and fresh-instance replays are independently cross-checked. The
    checkpoint inventory is checked here; the separate native-tree audit reads
    the complete SQLite byte images. Only fresh Flip clock literals are projected.
    """
    base = 'results/native-healthchecks-tree/'
    summary, language = read(base + 'summary.json'), read(base + 'language.json')
    arms = ['original', 'omit_readonly_context', 'wrong_project_context',
            'omit_pause_persistence', 'reject_readonly_get']
    symbols, modes = ['get', 'pause', 'resume'], ['complete', 'http_status']
    forms, apis, initials = ['legacy', 'hashed'], [1, 2, 3], ['new', 'paused']
    words = [()] + [word for length in range(1, 4)
                    for word in itertools.product(symbols, repeat=length)]
    name = lambda word: '-'.join(word) if word else 'root'
    ordered = lambda values: sorted(values, key=lambda word: (len(word), word))
    key = lambda row: (row['arm'], row['format'], row['api_version'], row['initial_status'])

    def same(actual, expected, message):
        require(typed_equal(actual, expected), 'Native tree ' + message)

    operations = {symbol: dict(name=symbol, kind='http', route='single' if symbol == 'get' else symbol,
                              target='alice', key='alice_ro' if symbol == 'get' else 'alice_rw',
                              method='GET' if symbol == 'get' else 'POST', body=None)
                  for symbol in symbols}
    for field, value in dict(depth=3, source_arms=arms, key_formats=forms, api_versions=apis,
                             initial_statuses=initials, operations=operations, configuration='identity',
                             words=[list(word) for word in words], one_physical_node_per_history=True,
                             state_quotient_used=False, complete_unbounded_physical_reachability=False).items():
        same(language[field], value, 'declared language ' + field)

    def headers(raw):
        result = {field.lower(): value for field, value in raw.items()}
        same(len(result), len(raw), 'distinct response header names')
        if 'access-control-allow-methods' in result:
            result['access-control-allow-methods'] = sorted(
                item.strip() for item in result['access-control-allow-methods'].split(','))
        return result

    def store(raw):
        tables = dict(raw['tables'])
        flips = []
        for raw_row in tables['api_flip']:
            row = dict(raw_row)
            created, processed = row.pop('created'), row.pop('processed')
            row.update(created_present=created is not None, processed_present=processed is not None,
                       processed_at_creation=typed_equal(created, processed))
            flips.append(row)
        tables['api_flip'] = flips
        return dict(raw, tables=tables)

    def observed(row):
        wire_headers = headers(row['response_headers'])
        is_json = wire_headers.get('content-type', '').startswith('application/json')
        same(json.loads(row['response_text']) if is_json else None, row['response'],
             'parsed response agrees with wire text, including JSON value types')
        same(wire_headers.get('content-length'), str(len(row['response_text'].encode())),
             'wire Content-Length')
        return dict(store=store(row['after']), http_status=row['http_status'],
                    project_id=row['request_project_id'], project_class=row['request_project_class'],
                    readonly=row['request_readonly'], api_version=row['request_api_version'],
                    manager_returns=row['source_manager_returns'],
                    manager_result_is_request_project=row['manager_result_is_request_project'],
                    response=dict(json=row['response'], text=None if is_json else row['response_text'],
                                  headers=wire_headers, cookies=row['response_cookies']),
                    client_cookies_before=row['client_cookies_before'],
                    client_cookies_after=row['client_cookies_after'])

    def reference(case, word):
        # This three-symbol lifecycle is evaluated from the initial fixture, never
        # from an observed response or a control's possibly corrupted next store.
        status, flips, code = case['initial_status'], [], 200
        for symbol in word:
            code = 409 if symbol == 'resume' and status != 'paused' else 200
            next_status = 'paused' if symbol == 'pause' else 'new' if symbol == 'resume' and code == 200 else status
            if next_status != status:
                flips.append((status, next_status))
            status = next_status
        owner = case['owners']['alice']
        persistent = store(case['initial'])
        tables = persistent['tables']
        tables['api_check'] = [dict(row, status=status if row['id'] == owner['check_id'] else 'new',
                                    last_start=None, last_ping=None, alert_after=None)
                               for row in tables['api_check']]
        tables['api_flip'] = [dict(__rowid__=i, id=i, owner_id=owner['check_id'], old_status=old,
                                  new_status=new, reason='', created_present=True, processed_present=True,
                                  processed_at_creation=True)
                             for i, (old, new) in enumerate(flips, 1)]
        if flips:
            sequence = [dict(row) for row in tables['sqlite_sequence']]
            require(not any(row['name'] == 'api_flip' for row in sequence), 'Native tree fresh initial Flip sequence')
            sequence.append(dict(__rowid__=1 + max((row['__rowid__'] for row in sequence), default=0),
                                 name='api_flip', seq=len(flips)))
            tables['sqlite_sequence'] = sequence
        readonly = word[-1] == 'get'
        document = None
        if code == 200:
            document = dict(name='alice check', slug='', tags='', desc='', n_pings=0, manual_resume=False,
                            methods='', start_kw='', success_kw='', failure_kw='', filter_subject=False,
                            filter_body=False, filter_http_body=False, filter_default_fail=False,
                            grace=3600, status=status, started=False, last_ping=None, next_ping=None,
                            subject='', subject_fail='', badge_url='http://testserver/b/2/' + owner['badge_uuid'] + '.svg',
                            timeout=86400)
            if readonly:
                document['unique_key'] = hashlib.sha1(owner['check_uuid'].replace('-', '')[:16].encode()).hexdigest()
            else:
                url = 'http://testserver/api/v' + str(case['api_version']) + '/checks/' + owner['check_uuid']
                document.update(uuid=owner['check_uuid'], ping_url='http://testserver/ping/' + owner['check_uuid'],
                                update_url=url, pause_url=url + '/pause', resume_url=url + '/resume',
                                channels=owner['channel_uuid'])
        text = None if document is not None else 'check is not paused'
        wire = json.dumps(document) if document is not None else text
        response_headers = {'content-type': 'application/json' if document is not None else 'text/html; charset=utf-8',
                            'content-length': str(len(wire.encode())), 'x-content-type-options': 'nosniff',
                            'referrer-policy': 'same-origin', 'cross-origin-opener-policy': 'same-origin',
                            'access-control-allow-origin': '*', 'access-control-allow-headers': 'X-Api-Key',
                            'access-control-allow-methods': ['DELETE', 'GET', 'OPTIONS', 'POST'] if readonly else ['OPTIONS', 'POST'],
                            'access-control-max-age': '600'}
        return dict(store=persistent, http_status=code, project_id=owner['project_id'],
                    project_class='hc.accounts.models.Project', readonly=readonly, api_version=case['api_version'],
                    manager_returns=[dict(native_class='hc.accounts.models.Project', project_id=owner['project_id'])],
                    manager_result_is_request_project=True,
                    response=dict(json=document, text=text, headers=response_headers, cookies={}),
                    client_cookies_before={}, client_cookies_after={})

    counts = Counter()
    uuid_population = set()
    checkpoint_paths, raw_paths = set(), set()

    def raw_case(relative, expected_key, replay_word=None):
        case = read(base + relative)
        same(list(key(case)), list(expected_key), 'case configuration')
        same(case['replay_word'], None if replay_word is None else list(replay_word), 'replay declaration')
        raw_paths.add(relative)
        declared = words[1:] if replay_word is None else [replay_word[:length] for length in range(1, len(replay_word) + 1)]
        actual_words = [tuple(row['word']) for row in case['records']]
        same(len(actual_words), len(declared), 'unique raw edge count')
        require(set(actual_words) == set(declared), 'Native tree complete raw language')
        same(set(case['owners']), {'alice', 'bob'}, 'initial owner domain')
        checks = {row['id']: row for row in case['initial']['tables']['api_check']}
        same(len(checks), 2, 'initial check count')
        same(case['initial']['tables']['api_flip'], [], 'initial empty Flip log')
        for owner_name, owner in case['owners'].items():
            require(owner['check_uuid'] not in uuid_population, 'Native tree and replay fixtures must be fresh')
            uuid_population.add(owner['check_uuid'])
            initial_check = checks[owner['check_id']]
            same(initial_check['project_id'], owner['project_id'], 'initial object ownership')
            same(initial_check['status'], case['initial_status'] if owner_name == 'alice' else 'new', 'initial Check status')
            for field in ('last_start', 'last_ping', 'alert_after'):
                same(initial_check[field], None, 'initial Check timestamp')
        directory = Path(relative).parent
        same(set(case['checkpoints']), {name(word) for word in [()] + declared}, 'checkpoint manifest coverage')
        for word in [()] + declared:
            checkpoint = case['checkpoints'][name(word)]
            same(checkpoint['path'], 'checkpoints/' + name(word) + '.sqlite.gz', 'checkpoint history path')
            require(type(checkpoint['sqlite_bytes']) is int and checkpoint['sqlite_bytes'] > 0, 'Native checkpoint declared byte count')
            path = directory / checkpoint['path']
            require((ARTIFACT / base / path).is_file(), 'Native tree checkpoint is absent')
            checkpoint_paths.add(path.as_posix())
        prefix = 'main' if replay_word is None else 'replay'
        counts['main_physical_checkpoints' if replay_word is None else 'replay_physical_checkpoints'] += len(case['checkpoints'])
        rows = {tuple(row['word']): row for row in case['records']}
        actual, expected = {}, {}
        for word in ordered(rows):
            row = rows[word]
            parent = rows.get(word[:-1])
            same(row['before'], case['initial'] if parent is None else parent['after'], prefix + ' raw parent continuity')
            same(row['client_cookies_before'], {} if parent is None else parent['client_cookies_after'], prefix + ' cookie continuity')
            same(row['checkpoint_exact_copy'], True, prefix + ' restored parent checkpoint')
            same(row['operation'], operations[word[-1]], prefix + ' operation')
            owner = case['owners']['alice']
            same(row['request'], dict(body='', header_key=owner['ro' if word[-1] == 'get' else 'rw'],
                                      method='GET' if word[-1] == 'get' else 'POST',
                                      path='/api/v' + str(case['api_version']) + '/checks/' + owner['check_uuid'] +
                                           ('' if word[-1] == 'get' else '/' + word[-1])), prefix + ' actual request')
            actual[word], expected[word] = observed(row), reference(case, word)
            counts['native_http_edges' if replay_word is None else 'native_replay_http_requests'] += 1
            counts['native_sql_statements' if replay_word is None else 'replay_sql_statements'] += len(row['sql'])
        return case, actual, expected

    def project(values, mode):
        return values if mode == 'complete' else {word: {'http_status': value['http_status']} for word, value in values.items()}

    def differences(actual, expected):
        result = {word: sorted(field for field in expected[word]
                               if not typed_equal(actual[word][field], expected[word][field]))
                  for word in ordered(expected) if not typed_equal(actual[word], expected[word])}
        minimal = [word for word in result if not any(word[:i] in result for i in range(1, len(word)))]
        return result, minimal

    def component_check(component, actual, expected):
        inputs = component['inputs']
        first = inputs['first_operation']
        require(first in symbols, 'Native tree root branch symbol')
        paths = [()] + [word for word in words[1:] if word[0] == first]
        internal = [word for word in paths if len(word) < 3]
        principals = {name(word): 'history_' + str(i).zfill(2) for i, word in enumerate(internal)}
        machine, caller, policy, book = inputs['machine'], inputs['caller'], inputs['policy'], inputs['codebook']
        fields = machine['state_names']
        same(fields, ['outcome_bit_' + str(i) for i in range(len(fields))], 'branch outcome fields')
        same(inputs['history_principals'], principals, 'branch history principals')
        same(inputs['target_histories'], [list(word) for word in paths], 'branch target histories')
        same(inputs['caller_histories'], [list(word) for word in internal] + [None], 'branch caller histories')
        same(inputs['capture_is_access_grant'], False, 'capture is an observation encoding')
        same(inputs['physical_histories_merged'], False, 'distinct physical histories')
        same(policy['state'], [[field, False] for field in fields], 'branch initial source state')
        same(policy['principals'], sorted(principals.values()), 'branch principal domain')
        same(policy['resources'], symbols, 'branch resource domain')
        same(policy['actions'], ['capture'], 'branch action domain')
        for field in ('roles', 'members', 'aliases'):
            same(policy[field], [], 'branch empty ' + field)
        same(machine['initial'], 0, 'branch initial target')
        same(caller['initial'], 0, 'branch initial caller')
        same(book[0], None, 'reserved initial code')
        same(len(machine['observations']), len(paths), 'complete target observation table')
        same(machine['observations'][0], 0, 'initial observation code')
        same(len(book) - 1, len({encoded(value) for word in paths[1:] for value in (actual[word], expected[word])}), 'distinct outcome codes')
        same(len({encoded(value) for value in book[1:]}), len(book) - 1, 'injective outcome codebook')
        same(len(fields), max(1, (len(book) - 1).bit_length()), 'outcome encoding width')
        alphabet = [[principal, symbol, 'capture'] for principal in policy['principals'] for symbol in symbols]
        same(machine['alphabet'], alphabet, 'branch encoded alphabet')
        rules = {}
        for rule in policy['rules']:
            same(rule['decision'], 'allow', 'constant capture decision')
            guard = rule['guard']
            same([item['field'] for item in guard], ['principal', 'resource'], 'constant reference guard fields')
            same([item['negated'] for item in guard], [False, False], 'positive reference guards')
            rule_key = (guard[0]['name'], guard[1]['name'])
            require(rule_key not in rules, 'Native tree duplicate reference rule')
            same([item['name'] for item in rule['updates']], fields, 'full reference update')
            require(all(type(item['value']) is bool for item in rule['updates']), 'Native tree reference bits are Boolean constants')
            rules[rule_key] = sum(1 << bit for bit, item in enumerate(rule['updates']) if item['value'])
        same(len(rules), len(paths) - 1, 'complete reference rules')
        target_rows = [[None] * len(alphabet) for _ in paths]
        caller_rows = [[None] * len(alphabet) for _ in range(len(internal) + 1)]
        for word in paths[1:]:
            principal = principals[name(word[:-1])]
            request = alphabet.index([principal, word[-1], 'capture'])
            target_rows[paths.index(word[:-1])][request] = ['allow', paths.index(word)]
            caller_rows[internal.index(word[:-1])][request] = internal.index(word) if word in internal else len(internal)
            source_code, target_code = rules[(principal, word[-1])], machine['observations'][paths.index(word)]
            require(type(source_code) is int and type(target_code) is int and 0 < source_code < len(book) and 0 < target_code < len(book),
                    'Native tree noninitial outcome code')
            same(book[source_code], expected[word], 'decoded reference versus independently reconstructed lifecycle')
            same(book[target_code], actual[word], 'decoded target versus complete raw observation')
        same(machine['transitions'], target_rows, 'entire branch target transition matrix')
        same(caller['transitions'], caller_rows, 'entire branch caller transition matrix')
        bounds = dict(target_states=len(paths), caller_states=len(caller_rows), state_bits=len(fields),
                      ast_nodes=sum(1 + len(rule['guard']) + len(rule['updates']) for rule in policy['rules']),
                      reference_rules=len(rules), rich_codes=len(book) - 1, enabled_edges=len(paths) - 1)
        same(inputs['bounds'], bounds, 'branch dimensions')
        require(bounds['state_bits'] <= 5 and bounds['caller_states'] <= 6 and bounds['ast_nodes'] <= 104, 'Native tree admitted branch bounds')
        bad, minimal = differences({word: actual[word] for word in paths[1:]},
                                   {word: expected[word] for word in paths[1:]})
        first_bad = minimal[0] if minimal else None
        same(set(component['methods']), {'protocol-scan', 'protocol-grouped'}, 'two retained production methods')
        for method, result in component['methods'].items():
            counts['production_method_comparisons'] += 1
            same(result['bindings'], 1, 'singleton binding family')
            same(result['accepted'], first_bad is None, 'production acceptance')
            same(result['classification'], 'all' if first_bad is None else 'none', 'production classification')
            same(result['matching_family'], [{}] if first_bad is None else [], 'production matching family')
            same(result['matching_bindings'], int(first_bad is None), 'production matching count')
            same(result['failing_bindings'], int(first_bad is not None), 'production failing count')
            same(result['shortest_failure'], None if first_bad is None else len(first_bad), 'production shortest length')
            same(result['graph_enabled_edges'], len(paths) - 1, 'production graph edge denominator')
            same(result['target_protocol_reachable_states'], len(paths), 'production product state denominator')
            same(len(result['profiles']), 1, 'one production profile')
            profile = result['profiles'][0]
            same(profile['binding'], {}, 'fixed singleton binding')
            same(profile['equivalent'], first_bad is None, 'production profile equivalence')
            profile_length(profile)
            if first_bad is None:
                continue
            same(profile['length'], len(first_bad), 'production profile length')
            q = t = source_state = 0
            decoded = ()
            for index, step in zip(profile['indices'], profile['trace'], strict=True):
                require(type(index) is int and 0 <= index < len(alphabet), 'Native tree valid saved witness index')
                edge, next_t = machine['transitions'][q][index], caller['transitions'][t][index]
                require(edge is not None and next_t is not None, 'Native tree saved witness admitted')
                request = alphabet[index]
                decoded += (request[1],)
                source_code = rules[(request[0], request[1])]
                target_code = machine['observations'][edge[1]]
                expected_step = dict(binding={}, compared_equal=source_code == target_code, decision_equal=True,
                                     protocol_state=t, request=request, source=['allow', source_code],
                                     source_state=source_state, state_equal=source_code == target_code,
                                     target=['allow', target_code], target_state=q)
                same(step, expected_step, 'every retained witness replay field')
                q, t, source_state = edge[1], next_t, source_code
            same(list(decoded), list(first_bad), 'decoded branch shortest history')
        counts['root_branch_components'] += 1

    index = read(base + 'profiles.json')
    grid = list(itertools.product(arms, forms, apis, initials))
    same([list(key(row)) for row in index], [list(item) for item in grid], 'complete unique collection/profile grid')
    for arm in arms:
        collection = read(base + 'native/' + arm + '/collection.json')
        same(collection['arm'], arm, 'collection arm')
        same(collection['source_imports_replaced'], False, 'native source imports')
        same(collection['complete_sqlite_checkpoints'], True, 'complete checkpoint collection')
        same(collection['cookie_state_preserved'], True, 'cookie preservation')
        same(collection['cases'], [dict(api_version=api, directory=form + '-api-' + str(api) + '-' + status,
                                        edges=len(words) - 1, format=form, initial_status=status, word=None)
                                   for form, api, status in itertools.product(forms, apis, initials)], 'native acquisition grid')
    expected_plans, expected_replay_fields, strata = defaultdict(dict), {}, {}
    for entry in index:
        arm, form, api, initial_status = key(entry)
        stem = form + '-api-' + str(api) + '-' + initial_status
        same(entry['source_record'], 'native/' + arm + '/' + stem + '/observations.json.gz', 'source record path')
        same(entry['profile'], 'profiles/' + arm + '/' + stem + '.json.gz', 'profile record path')
        case, full_actual, full_expected = raw_case(entry['source_record'], key(entry))
        counts['native_trees'] += 1
        profiles = read(base + entry['profile'])
        same([profile['mode'] for profile in profiles], modes, 'observation projection coverage')
        for profile in profiles:
            mode = profile['mode']
            actual, expected = project(full_actual, mode), project(full_expected, mode)
            bad, minimal = differences(actual, expected)
            first_bad = minimal[0] if minimal else None
            scientific = dict(mode=mode, equivalent=not bad, shortest_word=None if first_bad is None else list(first_bad),
                              shortest_length=None if first_bad is None else len(first_bad),
                              first_bad_prefixes=[dict(word=list(word), fields=bad[word]) for word in minimal],
                              differing_edges=len(bad), admitted_edges=len(words) - 1, complete_bounded_language=True,
                              language_words=len(words), singleton_configuration=True, shared_correspondence_family=False)
            same({field: value for field, value in profile.items() if field != 'components'}, scientific, 'all outer profile scientific fields')
            same([component['inputs']['first_operation'] for component in profile['components']], symbols, 'complete root-branch cover')
            for component in profile['components']:
                component_check(component, actual, expected)
            counts['global_profiles'] += 1
            counts['minimal_bad_prefix_results'] += len(minimal)
            stratum = dict(arm=arm, initial_status=initial_status, observation=mode, equivalent=not bad,
                           shortest_length=scientific['shortest_length'], shortest_word=scientific['shortest_word'],
                           differing_edges=len(bad), minimal_bad_prefixes=len(minimal))
            stratum_key = (arm, initial_status, mode)
            previous, repeats = strata.get(stratum_key, (stratum, 0))
            same(stratum, previous, 'agreement across key format and API strata')
            strata[stratum_key] = (stratum, repeats + 1)
            for word in minimal:
                expected_plans[arm].setdefault((form, api, initial_status, word), []).append(mode)
                expected_replay_fields[(arm, form, api, initial_status, word, mode)] = bad[word]
    for arm in arms:
        plans = read(base + 'replay-plans/' + arm + '.json')
        remaining = dict(expected_plans[arm])
        collection = read(base + 'native-replay/' + arm + '/collection.json') if plans else None
        if collection is not None:
            same(collection['arm'], arm, 'fresh replay collection arm')
            same(collection['source_imports_replaced'], False, 'fresh replay original imports')
            same(collection['complete_sqlite_checkpoints'], True, 'fresh replay complete checkpoints')
            same(collection['cookie_state_preserved'], True, 'fresh replay cookie continuity')
            same(collection['cases'], [dict(api_version=plan['api_version'], directory=plan['directory'],
                                            edges=len(plan['word']), format=plan['format'],
                                            initial_status=plan['initial_status'], word=plan['word']) for plan in plans],
                 'fresh native acquisition and replay-plan alignment')
        for position, plan in enumerate(plans):
            form, api, status, word = plan['format'], plan['api_version'], plan['initial_status'], tuple(plan['word'])
            plan_key = (form, api, status, word)
            require(plan_key in remaining, 'Native tree duplicate or undeclared negative replay')
            same(plan['modes'], remaining.pop(plan_key), 'all replayed negative observation modes')
            same(plan['directory'], 'word-' + str(position).zfill(4), 'fresh replay unique directory')
            stem = form + '-api-' + str(api) + '-' + status
            same(plan['main_record'], 'native/' + arm + '/' + stem + '/observations.json.gz', 'fresh replay primary source pointer')
            same(plan['main_profile'], 'profiles/' + arm + '/' + stem + '.json.gz', 'fresh replay primary profile pointer')
            replay, full_actual, full_expected = raw_case('native-replay/' + arm + '/' + plan['directory'] + '/observations.json.gz',
                                                         (arm, form, api, status), replay_word=word)
            counts['native_replay_words'] += 1
            for mode in plan['modes']:
                bad, minimal = differences(project(full_actual, mode), project(full_expected, mode))
                same([list(value) for value in minimal], [list(word)], 'fresh-instance first failing prefix')
                same(bad[word], expected_replay_fields[(arm, form, api, status, word, mode)],
                     'fresh-instance first-failure fields agree with the primary tree')
                counts['native_replayed_negative_results'] += 1
        require(not remaining, 'Native tree some minimal bad prefixes have no fresh replay')
    same({path.relative_to(ARTIFACT / base).as_posix() for section in ('native', 'native-replay')
          for path in (ARTIFACT / base / section).glob('*/*/observations.json.gz')}, raw_paths, 'complete raw file inventory')
    same({path.relative_to(ARTIFACT / base).as_posix() for section in ('native', 'native-replay')
          for path in (ARTIFACT / base / section).glob('*/*/checkpoints/*.sqlite.gz')}, checkpoint_paths, 'complete checkpoint file inventory')
    computed_strata = [dict(row, repeated_strata=repeats) for _, (row, repeats) in sorted(strata.items())]
    same(summary['strata'], computed_strata, 'recomputed shortest-history strata')
    for field, value in counts.items():
        if field != 'replay_sql_statements':
            same(summary[field], value, 'summary denominator ' + field)
    for field, value in dict(status='PASS', applications=1, source_arms=len(arms), key_formats=len(forms),
                             api_versions=len(apis), initial_statuses=initials, native_operations=symbols,
                             maximum_request_length=3, nodes_per_tree=len(words), edges_per_tree=len(words) - 1,
                             complete_bounded_word_language=True, complete_unbounded_physical_state_graph=False,
                             physical_histories_merged=False, shared_correspondence_family=False).items():
        same(summary[field], value, 'summary scope ' + field)
    return {**dict(counts), 'distinct_fresh_check_uuids': len(uuid_population),
            'shortest_history_strata': computed_strata,
            'scope': 'One application, fixed identity credential routing, all words of length at most three over get/pause/resume, two initial Check statuses, and separate singleton targets. Recomputes the full raw observation comparison, constant-table encoding, saved production witness and fresh negative-prefix replay. Counts complete SQLite inventories without rereading their contents; the independent native-tree audit supplies that physical-image check. Flip clock literals remain in the raw records and are compared by presence and equality-at-creation only.'}


def session_initial_state():
    """Reconcile all fresh initial-store histories with the independent oracle."""
    if str(ARTIFACT) not in sys.path:
        sys.path.insert(0, str(ARTIFACT))
    from source_study.session_initial_state.validation import verify as verify_histories
    base = 'results/session-initial-state/'
    native = verify_histories(ARTIFACT / base)
    require(typed_equal(native, read(base + 'validation.json.gz')),
            'Initial-store complete-history validation differs')
    finite = read(base + 'finite-audit.json.gz')
    require(finite['status'] == 'PASS' and type(finite['new_native_executions']) is int
            and finite['new_native_executions'] == 0,
            'Initial-store finite audit status or execution scope')
    contexts = {(n, anchors, initial) for n in range(2, 7)
                for anchors in range(1 << n) for initial in range(1 << n)}
    expected_contexts = [dict(n=n, anchors=anchors, initial=initial,
                             free_rows=n-anchors.bit_count(),
                             absent_free_rows=(((1 << n)-1) & ~anchors & ~initial).bit_count())
                         for n, anchors, initial in sorted(contexts)]
    require(typed_equal(finite['contexts'], expected_contexts),
            'Initial-store complete initial/anchor domain differs')
    survivor = finite['surviving_family_audit']
    require(len(survivor['rows']) == len(contexts), 'Initial-store survivor-domain size')
    for context, row in zip(expected_contexts, survivor['rows']):
        n, anchors, initial = (context[key] for key in ('n', 'anchors', 'initial'))
        m, d = context['free_rows'], context['absent_free_rows']
        expected_profiles = {
            'projected_lookup': math.factorial(m-d) * math.factorial(d),
            'projected_mutating': math.factorial(d),
            'selected_row_lookup': math.factorial(d),
            'selected_row_mutating': math.factorial(d),
        }
        expected_row = dict(n=n, anchors=anchors, initial=initial, free_present=m-d,
                            free_absent=d, profiles={key: dict(survivors=value, exact_family_checked=True)
                                                    for key, value in expected_profiles.items()})
        require(typed_equal(row, expected_row), 'Initial-store exact survivor strata differ')
    search_keys = {(n, initial, observed, reset) for n in range(1, 5)
                   for initial in range(1 << n)
                   for observed in ('projected', 'row')
                   for reset in ('none', 'initial', 'complete')}
    actual_keys = [(row['n'], row['initial'], row['observed'], row['reset']) for row in finite['search']]
    require(len(actual_keys) == len(search_keys) and set(actual_keys) == search_keys,
            'Initial-store independent optimal-search domain differs')
    native_summary = {key: value for key, value in native.items() if key != 'cases'}
    return {'native': native_summary,
            'finite_constructions': finite['totals'],
            'finite_survivor_languages': {key: value for key, value in survivor.items() if key != 'rows'},
            'independent_optimal_search_cases': len(actual_keys),
            'scope': 'Recomputes complete native histories and exact finite survivor counts from retained evidence. The separate finite-audit command reruns every belief-state search and full-language product traversal. No new application request or timing sample is acquired here.'}


def derive():
    return {'status': 'PASS', 'overlapping_supports': overlapping_supports(),
            'retained_family_cost': retained_family_cost(), 'protocol_grouping': protocol_grouping(),
            'native_session_correspondence': native_sessions(), 'native_timing': native_timing(),
            'session_short_test_bounds': session_short_test_bounds(),
            'session_operation_cost': session_operation_cost(),
            'session_initial_state': session_initial_state(),
            'complete_symbolic_comparison': complete_symbolic_comparison(),
            'additional_native_records': additional_native_records(),
            'native_healthchecks_records': native_healthchecks_records(),
            'native_healthchecks_tree_records': native_healthchecks_tree_records(),
            'retained_source_records': retained_source_records(),
            'scope': 'Offline reconciliation of the supplied raw records, full profiles, counts and descriptive timing statistics. Semantic oracle tests and native reruns are separate commands in the claim ledger.'}


def verify(write=False):
    report = derive()
    destination = HERE / 'claim-checks.json'
    if write:
        destination.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    else:
        equal(json.loads(destination.read_text()), report, 'Current claim reconciliation report')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.write), indent=2))


if __name__ == '__main__':
    main()
