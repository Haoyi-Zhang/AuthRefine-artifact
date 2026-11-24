"""Acquire, diagnose and replay complete Conet policy-store executions."""
import argparse
import ast
from collections import Counter
import csv
import gzip
import io
import json
from pathlib import Path
import platform
import sys
import time

ART = Path(__file__).resolve().parents[2]
for directory in (ART, ART / "src"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
sys.dont_write_bytecode = True

from source_study.native_policy_store import fixtures, oracle

SEMANTIC_FIELDS = ("binding", "equivalent", "length", "indices", "trace")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def write(path, value):
    raw = encoded(value)
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else
                     (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def semantic_rows(result):
    return [{key: row[key] for key in SEMANTIC_FIELDS} for row in result["profiles"]]


def run_method(case, method):
    from benchmarks.stateful_family import run_method as total
    from protocol_profile import protocol_binding_profile
    from protocol_grouped import support_indexed_protocol_profile
    if method in fixtures.TOTAL_METHODS:
        return total(case, method)
    algorithm, caller = method.split("/")
    function = protocol_binding_profile if algorithm == "protocol-scan" else support_indexed_protocol_profile
    return function(case["policy"], case["machine"], case["callers"][caller], family=case["family"])


def acquire(output):
    from source_study.native_policy_store import native
    if output.exists():
        raise ValueError("acquisition requires a fresh output directory")
    dependencies = native.dependency_record()
    output.mkdir(parents=True)
    records, runtimes = [], []
    with native.modules(output / "source-candidate") as (modules, manifest):
        for arm in fixtures.ARMS:
            for mask in range(8):
                started = time.perf_counter_ns()
                graph = native.graph(modules[arm], mask)
                elapsed = time.perf_counter_ns() - started
                identifier = f"{arm}-initial-{mask}"
                records.append({"id": identifier, "arm": arm, **graph})
                runtimes.append({"id": identifier, "acquisition_wall_ns": elapsed})
                print(f"{identifier}: {len(graph['states'])} physical states, {graph['measured_cells']} native edges", flush=True)
    # No production checker/evaluator has been imported before these records.
    write(output / "native-observations.json.gz", records)
    write(output / "fixtures.json", fixtures.document())
    write(output / "source-identity.json", manifest)
    write(output / "native-dependencies.json", dependencies)
    write(output / "acquisition.json", {"status": "PASS", "python": platform.python_version(),
        "platform": platform.platform(), "records": runtimes,
        "scope": "Per-case native acquisition includes owned-file setup, complete source method calls, reaching-prefix replay, raw file and ordered-row reads, and graph construction; common dependency/source checks, module imports and output serialization are separate.",
        "source_module_imported_complete": True, "source_imports_replaced": False,
        "observation_written_before_policy_evaluation": True})


def snapshot(memory, disk, text):
    rows = [list(row) for row in fixtures.ROWS]
    if any(row not in rows for row in memory + disk) or len({tuple(r) for r in memory}) != len(memory) or len({tuple(r) for r in disk}) != len(disk):
        raise ValueError("rich record includes a duplicate or foreign row")
    disk_mask = sum(1 << rows.index(row) for row in disk)
    memory_mask = sum(1 << rows.index(row) for row in memory)
    parsed = list(csv.reader(io.StringIO(text), skipinitialspace=True))
    if any(len(row) != 4 or row[0] != "p" for row in parsed) or [row[1:] for row in parsed] != disk:
        raise ValueError("raw disk text does not describe the reported rows")
    return {"memory_rows": memory, "disk_rows": disk, "disk_text": text,
            "state": disk_mask | (memory_mask << len(fixtures.ROWS))}


def check_observation(observed, before, arm, request):
    if observed["before"] != before or observed["request"] != request:
        raise ValueError("native record does not continue the actual preceding store")
    memory = [list(row) for row in before["memory_rows"]]
    disk = [list(row) for row in before["disk_rows"]]
    text = before["disk_text"]
    row = list(fixtures.ROWS[fixtures.resources().index(request[1])])
    action = request[2]
    result = True
    if action == "restart":
        memory = [list(value) for value in disk]
        method, arguments = "PolicyEngine.__init__", None
        native_return = {"kind": "instance", "class": "PolicyEngine"}
    else:
        result = row not in memory if action == "add" else row in memory
        method = "PolicyEngine." + {"add": "add_policy_rule", "remove": "remove_policy_rule", "authorize": "authorize"}[action]
        arguments = row
        native_return = {"kind": "boolean", "value": result}
        if result and action != "authorize":
            if action == "add":
                memory.append(row)
            else:
                memory.remove(row)
            if arm == "repaired":
                disk = [list(value) for value in memory]
                text = "\n".join("p, " + ", ".join(value) for value in disk)
    expected = {"request": request, "native_arguments": arguments, "source_method": method,
                "interface_result": result, "native_return": native_return, "decision": "allow" if result else "deny",
                "before": before, "after": snapshot(memory, disk, text)}
    if observed != expected:
        raise ValueError("native rich record disagrees with independent ordered-set equations")
    return expected["after"]


def check_graph(graph):
    mask, arm = graph["initial_mask"], graph["arm"]
    rows = [list(row) for i, row in enumerate(fixtures.ROWS) if mask & (1 << i)]
    initial = snapshot(rows, [list(row) for row in rows], "\n".join("p, " + ", ".join(row) for row in rows))
    states, machine = graph["states"], graph["machine"]
    requests = fixtures.alphabet()
    if (states[0] != initial or machine["initial"] != 0 or machine["alphabet"] != requests
            or machine["state_names"] != fixtures.state_names()
            or machine["observations"] != [state["state"] for state in states]
            or len(states) != 16 or len({encoded(state) for state in states}) != len(states)):
        raise ValueError("native reachable ordered-store domain differs")
    paths = {row["state"]: row["indices"] for row in graph["paths"]}
    if len(paths) != len(states) or paths.get(0) != []:
        raise ValueError("native reaching paths are incomplete")
    cells, prefix_steps, projected = {}, 0, {}
    for edge in graph["edges"]:
        source, index = edge["from_state"], edge["input_index"]
        if (source, index) in cells or edge["prefix"] != paths[source] or len(edge["prefix"]) != len(edge["prefix_observations"]):
            raise ValueError("native prefix/cell record count differs")
        before = initial
        current = 0
        for word_index, observed in zip(edge["prefix"], edge["prefix_observations"]):
            before = check_observation(observed, before, arm, requests[word_index])
            current = machine["transitions"][current][word_index][1]
            if before != states[current]:
                raise ValueError("native prefix differs from its measured graph")
        if before != states[source] or current != source:
            raise ValueError("actual prefix does not reach the complete target state")
        after = check_observation(edge["observation"], before, arm, requests[index])
        decision, successor = machine["transitions"][source][index]
        if after != states[successor] or decision != edge["observation"]["decision"]:
            raise ValueError("finite target table differs from raw native records")
        projection = decision, after["state"]
        key = before["state"], index
        if key in projected and projected[key] != projection:
            raise ValueError("row order affects the claimed membership interface")
        projected[key] = projection
        cells[source, index] = edge
        prefix_steps += len(edge["prefix"])
    if (set(cells) != {(s, i) for s in range(len(states)) for i in range(len(requests))}
            or graph["measured_cells"] != len(cells) or graph["prefix_operations"] != prefix_steps):
        raise ValueError("native graph does not cover every reachable enabled cell")
    if len(projected) != 96:
        raise ValueError("expected all eight membership states and twelve operations")
    calls = Counter({"PolicyEngine.__init__": 1 + len(cells),
                     "PolicyEngine.list_policy_rules": 2 + 4 * len(cells) + 2 * prefix_steps})
    for edge in graph["edges"]:
        for observed in edge["prefix_observations"] + [edge["observation"]]:
            calls[observed["source_method"]] += 1
    if dict(calls) != graph["source_method_calls"]:
        raise ValueError("native source method count differs from recorded operations")
    return {"physical_states": len(states), "membership_states": len({s["state"] for s in states}),
            "measured_cells": len(cells), "distinct_membership_cells": len(projected),
            "prefix_operations": prefix_steps}


def outcome(rows):
    lengths = Counter("infinity" if row["equivalent"] else str(row["length"]) for row in rows)
    words = Counter(tuple(row["indices"]) for row in rows if not row["equivalent"])
    return {"bindings": len(rows), "matching": lengths.get("infinity", 0), "strata": dict(lengths),
            "canonical_words": [{"indices": list(word), "excluded_bindings": count} for word, count in sorted(words.items())]}


def compare_previous_table(graphs, previous=None):
    declaration = ast.parse((ART / "source_study/repair_profiles.py").read_text())
    selected = [node.value for node in ast.walk(declaration) if isinstance(node, ast.Assign)
                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "rows"]
    if len(selected) != 1 or ast.literal_eval(selected[0]) != [list(row) for row in fixtures.ROWS]:
        raise ValueError("prior Conet fixture row identities differ")
    if previous is None:
        previous = read(ART / "source_study/data/repair-profiles.json.gz")["Conet"]
    comparisons, totals = {}, Counter()
    for graph in graphs:
        arm = graph["arm"]
        old = previous[arm]["machine"]
        if old["state_names"] != [f"{layer}_{i}" for layer in ("disk", "memory") for i in range(3)]:
            raise ValueError("prior table observation encoding differs")
        positions = {value: i for i, value in enumerate(old["observations"])}
        for edge in graph["edges"]:
            observed = edge["observation"]
            request = observed["request"]
            old_request = [request[0], f"permission_{fixtures.resources().index(request[1])}", request[2]]
            old_index = old["alphabet"].index(old_request)
            old_source = positions[observed["before"]["state"]]
            decision, successor = old["transitions"][old_source][old_index]
            actual = [observed["decision"], observed["after"]["state"]]
            expected = [decision, old["observations"][successor]]
            if actual != expected:
                raise ValueError("complete-module native execution differs from the prior source-lowered table")
            key = arm, observed["before"]["state"], edge["input_index"]
            if key not in comparisons:
                comparisons[key] = {"arm": arm, "before_membership": key[1], "native_request": request,
                    "prior_request": old_request, "native_outcome": actual, "prior_outcome": expected,
                    "first_native_record": {"id": graph["id"], "from_state": edge["from_state"], "input_index": edge["input_index"]},
                    "native_occurrences": 0}
            comparisons[key]["native_occurrences"] += 1
            totals[arm] += 1
    return {"source": "source_study/data/repair-profiles.json.gz", "row_declaration": "source_study/repair_profiles.py",
        "observation_map": "disk_0..2,memory_0..2 correspond to disk-1..3,memory-1..3; permission_i corresponds to row-(i+1).",
        "compared_fields": ["method outcome", "before membership", "after membership"],
        "native_cell_comparisons": dict(totals),
        "distinct_prior_cells_compared": {arm: sum(key[0] == arm for key in comparisons) for arm in fixtures.ARMS},
        "prior_table_cells_per_arm": 768,
        "unreached_prior_repaired_cells": 672,
        "differences": 0, "records": [comparisons[key] for key in sorted(comparisons)]}


def case_from(graph, *, check_algorithms):
    checked = check_graph(graph)
    case = {"id": graph["id"], "arm": graph["arm"], "initial_mask": graph["initial_mask"],
            "policy": fixtures.contract(graph["initial_mask"]), "machine": graph["machine"],
            "family": fixtures.family(), "callers": fixtures.callers(), "expected": {}}
    mask, machine, family = case["initial_mask"], case["machine"], case["family"]
    direct = [oracle.profile(mask, machine, binding) for binding in family]
    expected = {method: direct for method in fixtures.TOTAL_METHODS}
    independent = {"total": direct}
    for caller in fixtures.CALLERS:
        rows = [oracle.profile(mask, machine, binding, case["callers"][caller]) for binding in family]
        independent[caller] = rows
        for algorithm in ("scan", "grouped"):
            expected[f"protocol-{algorithm}/{caller}"] = rows
    counts = {}
    for method, rows in expected.items():
        if check_algorithms:
            result = run_method(case, method)
            if semantic_rows(result) != rows:
                raise ValueError("independent complete-profile disagreement: " + case["id"] + ", " + method)
            counts[method] = {key: result[key] for key in ("transition_evaluations", "replay_evaluations", "work_operations") if key in result}
        case["expected"][method] = rows
    decision_only = [oracle.profile(mask, machine, binding, observe_state=False) for binding in family]
    boolean_workflow = [oracle.profile(mask, machine, binding, case["callers"]["mutation-restart-query"],
                                      observe_state=False) for binding in family]
    summary = {"id": case["id"], "arm": case["arm"], "initial_mask": mask, **checked,
        "full_observation": {name: outcome(rows) for name, rows in independent.items()},
        "decision_only": outcome(decision_only), "decision_only_workflow": outcome(boolean_workflow),
        "identity_full_shortest": direct[0]["length"],
        "identity_boolean_shortest": decision_only[0]["length"],
        "identity_boolean_workflow_shortest": boolean_workflow[0]["length"],
        "algorithm_counts": counts}
    profile = {"id": case["id"], "independent": independent, "decision_only": decision_only,
               "decision_only_workflow": boolean_workflow}
    consumers = []
    for name, rows in {**independent, "decision-only": decision_only,
                      "decision-only/workflow": boolean_workflow}.items():
        for row in rows:
            if not row["equivalent"]:
                consumers.append({"contract": name, "binding": row["binding"], "indices": row["indices"]})
    return case, summary, profile, consumers


def case_csv(summaries):
    output = io.StringIO(newline="")
    fields = ["id", "arm", "initial_mask", "physical_states", "membership_states", "measured_cells", "prefix_operations",
              "family_members", "matching_full", "matching_query_only", "matching_one_mutation", "matching_workflow",
              "matching_boolean_only", "matching_boolean_workflow", "identity_full_shortest", "identity_boolean_shortest",
              "identity_boolean_workflow_shortest"]
    writer = csv.DictWriter(output, fields, lineterminator="\n")
    writer.writeheader()
    for summary in summaries:
        row = {key: summary[key] for key in fields if key in summary}
        full = summary["full_observation"]
        row.update(family_members=full["total"]["bindings"], matching_full=full["total"]["matching"],
                   matching_query_only=full["query-only"]["matching"], matching_one_mutation=full["one-mutation"]["matching"],
                   matching_workflow=full["mutation-restart-query"]["matching"],
                   matching_boolean_only=summary["decision_only"]["matching"],
                   matching_boolean_workflow=summary["decision_only_workflow"]["matching"])
        writer.writerow(row)
    return output.getvalue()


def analyze(output):
    source_path = output / "native-observations.json.gz"
    frozen = source_path.read_bytes()
    records = read(source_path)
    expected_ids = [f"{arm}-initial-{mask}" for arm in fixtures.ARMS for mask in range(8)]
    if [row["id"] for row in records] != expected_ids:
        raise ValueError("the native cohort must retain both arms and all initial files")
    inputs, summaries, profiles, replays = [], [], [], []
    for graph in records:
        case, summary, profile, consumers = case_from(graph, check_algorithms=True)
        inputs.append(case); summaries.append(summary); profiles.append(profile)
        replays.append({"id": case["id"], "arm": case["arm"], "initial_mask": case["initial_mask"], "consumers": consumers})
    if source_path.read_bytes() != frozen:
        raise ValueError("native observations changed during diagnosis")
    write(output / "inputs.json.gz", inputs)
    write(output / "profiles.json.gz", profiles)
    write(output / "native-replay-inputs.json.gz", replays)
    write(output / "previous-table-comparison.json.gz", compare_previous_table(records))
    write(output / "diagnosis.json", {"cases": summaries,
        "method_binding_comparisons": len(fixtures.METHODS) * len(fixtures.family()) * len(records),
        "comparison_unit": "Repeated per-binding algorithm comparisons of the same native source cases, not independent source samples.",
        "decision_only_contract": "Separate direct product search comparing API Booleans while withholding store observations; it is not an instance of the full-observation diagnosis theorem.",
        "physical_state": "Both ordered native policy sets and raw disk text. Membership-equivalent physical nodes remain distinct in the target.",
        "all_canonical_witnesses_are_shortest": True})
    (output / "case-summary.csv").write_text(case_csv(summaries))
    print(json.dumps({"cases": len(records), "method_binding_comparisons": len(fixtures.METHODS) * len(fixtures.family()) * len(records)}), flush=True)


def native_replay(output):
    from source_study.native_policy_store import native
    native.dependency_record()
    tasks = read(output / "native-replay-inputs.json.gz")
    records, summaries = [], []
    with native.modules() as (modules, _):
        for task in tasks:
            words = sorted({tuple(row["indices"]) for row in task["consumers"]})
            observations, counts = native.replay_words(modules[task["arm"]], task["initial_mask"], words)
            by_word = {tuple(row["indices"]): row["observations"] for row in observations}
            for consumer in task["consumers"]:
                oracle.check_native_witness(task["initial_mask"], consumer["binding"], consumer["indices"],
                    by_word[tuple(consumer["indices"])], observe_state=not consumer["contract"].startswith("decision-only"))
            records.append({"id": task["id"], "words": observations, "source_method_calls": counts})
            summaries.append({"id": task["id"], "physical_words": len(words),
                "word_operations": sum(len(word) for word in words), "checked_consumers": len(task["consumers"])})
    write(output / "native-witness-replay.json.gz", records)
    write(output / "native-replay-summary.json", {"cases": summaries,
        "physical_words": sum(row["physical_words"] for row in summaries),
        "word_operations": sum(row["word_operations"] for row in summaries),
        "checked_consumers": sum(row["checked_consumers"] for row in summaries),
        "consumer_unit": "A fixed binding under one of five full-observation profiles or two separately declared Boolean-only profiles; repeated methods are not counted again."})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("acquire", "analyze", "replay", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "verify":
        from source_study.native_policy_store.summarize import verify
        print(json.dumps(verify(args.output), indent=2))
    else:
        {"acquire": acquire, "analyze": analyze, "replay": native_replay}[args.command](args.output)


if __name__ == "__main__":
    main()
