"""Read-only verification of raw native histories and every reported profile."""
from collections import Counter
from pathlib import Path

from source_study.native_policy_store import fixtures, oracle
from source_study.native_policy_store.run import (case_csv, case_from, check_observation, compare_previous_table, encoded,
    read, snapshot)


def verify(directory):
    directory = Path(directory)
    from source_study.native_policy_store.native import MODEL, SOURCE, source_material
    _, candidate, source = source_material()
    if read(directory / "fixtures.json") != fixtures.document():
        raise ValueError("supplied experiment fixture/family differs")
    if read(directory / "source-identity.json") != source:
        raise ValueError("recorded native source identity differs")
    if (directory / "source-candidate/policy.py").read_text() != candidate:
        raise ValueError("recorded executed repair source differs")
    for name, relative in (("policy_model.conf", MODEL), ("LICENSE", "LICENSE"), ("NOTICE", "NOTICE")):
        if (directory / "source-candidate" / name).read_bytes() != (SOURCE / relative).read_bytes():
            raise ValueError("recorded executed repair model/license differs")
    native = read(directory / "native-observations.json.gz")
    previous = compare_previous_table(native)
    if read(directory / "previous-table-comparison.json.gz") != previous:
        raise ValueError("prior/native table correspondence record differs")
    inputs = read(directory / "inputs.json.gz")
    profiles = read(directory / "profiles.json.gz")
    diagnosis = read(directory / "diagnosis.json")
    tasks = read(directory / "native-replay-inputs.json.gz")
    replays = read(directory / "native-witness-replay.json.gz")
    replay_summary = read(directory / "native-replay-summary.json")
    if (directory / "case-summary.csv").read_text() != case_csv(diagnosis["cases"]):
        raise ValueError("publication CSV differs from the checked diagnosis records")
    expected_ids = [f"{arm}-initial-{mask}" for arm in fixtures.ARMS for mask in range(8)]
    for records in (native, inputs, profiles, diagnosis["cases"], tasks, replays, replay_summary["cases"]):
        if [row["id"] for row in records] != expected_ids:
            raise ValueError("retained native cohort/record order differs")
    distinct_physical = {arm: set() for arm in fixtures.ARMS}
    distinct_membership = {arm: set() for arm in fixtures.ARMS}
    physical_words = word_operations = checked_consumers = measured = prefixes = 0
    source_calls = Counter()
    case_summaries = []
    for position, graph in enumerate(native):
        case, summary, profile, consumers = case_from(graph, check_algorithms=False)
        retained_summary = diagnosis["cases"][position]
        if case != inputs[position]:
            raise ValueError("supplied family, model or complete algorithm profiles differ")
        if profile != profiles[position]:
            raise ValueError("independent full or decision-only profile differs")
        if {k: v for k, v in summary.items() if k != "algorithm_counts"} != {k: v for k, v in retained_summary.items() if k != "algorithm_counts"}:
            raise ValueError("diagnosis counts or shortest witness strata differ")
        task = {"id": case["id"], "arm": case["arm"], "initial_mask": case["initial_mask"], "consumers": consumers}
        if task != tasks[position]:
            raise ValueError("native replay requests do not cover all excluded bindings")
        expected_words = sorted({tuple(consumer["indices"]) for consumer in consumers})
        recorded = replays[position]["words"]
        if [tuple(row["indices"]) for row in recorded] != expected_words:
            raise ValueError("native replay word set differs")
        by_word = {}
        replay_calls = Counter({"PolicyEngine.__init__": 1 + len(recorded),
            "PolicyEngine.list_policy_rules": 1 + len(recorded) + 2 * sum(len(word["indices"]) for word in recorded)})
        for word in recorded:
            if len(word["indices"]) != len(word["observations"]):
                raise ValueError("native replay operation count differs")
            before = graph["states"][0]
            target = 0
            for index, observed in zip(word["indices"], word["observations"]):
                replay_calls[observed["source_method"]] += 1
                before = check_observation(observed, before, case["arm"], fixtures.alphabet()[index])
                decision, target = case["machine"]["transitions"][target][index]
                if before != graph["states"][target] or decision != observed["decision"]:
                    raise ValueError("native replay differs from the acquired complete target")
            by_word[tuple(word["indices"])] = word["observations"]
        if dict(replay_calls) != replays[position]["source_method_calls"]:
            raise ValueError("native replay source method count differs")
        for consumer in consumers:
            oracle.check_native_witness(case["initial_mask"], consumer["binding"], consumer["indices"],
                by_word[tuple(consumer["indices"])], observe_state=not consumer["contract"].startswith("decision-only"))
        counts = {"id": case["id"], "physical_words": len(recorded),
            "word_operations": sum(len(row["indices"]) for row in recorded), "checked_consumers": len(consumers)}
        if replay_summary["cases"][position] != counts:
            raise ValueError("native witness summary differs")
        physical_words += counts["physical_words"]
        word_operations += counts["word_operations"]
        checked_consumers += counts["checked_consumers"]
        measured += graph["measured_cells"]
        prefixes += graph["prefix_operations"]
        source_calls.update(graph["source_method_calls"])
        for edge in graph["edges"]:
            observed = edge["observation"]
            distinct_physical[case["arm"]].add((encoded(observed["before"]), edge["input_index"]))
            distinct_membership[case["arm"]].add((observed["before"]["state"], edge["input_index"]))
        # These are designed positive/negative controls, recomputed rather than
        # copied from saved labels. A withheld store changes the question.
        expected_matching = 0 if case["arm"] == "original" else 1
        if summary["full_observation"]["total"]["matching"] != expected_matching:
            raise ValueError("original/actual-source-repair comparison did not close as specified")
        identity = fixtures.family()[0]
        identity_full = next(row for row in profile["independent"]["total"] if row["binding"] == identity)
        identity_boolean = next(row for row in profile["decision_only"] if row["binding"] == identity)
        if case["arm"] == "original" and (identity_full["length"] != 1 or identity_boolean["length"] != 3):
            raise ValueError("the full-store and Boolean-only witness questions were conflated")
        case_summaries.append({"id": case["id"], "full_observation": summary["full_observation"],
                               "decision_only": summary["decision_only"],
                               "decision_only_workflow": summary["decision_only_workflow"]})
    method_comparisons = len(native) * len(fixtures.family()) * len(fixtures.METHODS)
    if diagnosis["method_binding_comparisons"] != method_comparisons:
        raise ValueError("algorithm comparison denominator differs")
    for key, value in (("physical_words", physical_words), ("word_operations", word_operations), ("checked_consumers", checked_consumers)):
        if replay_summary[key] != value:
            raise ValueError("aggregate native witness count differs")
    return {"status": "PASS", "application": "Conet", "native_cases": len(native),
        "original_initial_files": 8, "repaired_initial_files": 8,
        "measured_edges": measured, "prefix_operations": prefixes,
        "distinct_physical_state_request_pairs": {arm: len(values) for arm, values in distinct_physical.items()},
        "distinct_membership_request_pairs": {arm: len(values) for arm, values in distinct_membership.items()},
        "source_method_calls": dict(source_calls), "family_members_per_case": len(fixtures.family()),
        "method_binding_comparisons": method_comparisons,
        "native_witness_words": physical_words, "native_witness_operations": word_operations,
        "native_witness_binding_contract_checks": checked_consumers,
        "full_store_identity_failure_length": 1, "boolean_only_identity_failure_length": 3,
        "prior_source_lowering": {key: value for key, value in previous.items() if key != "records"},
        "algorithm_samples_are_not_independent_source_samples": True,
        "cases": case_summaries}
