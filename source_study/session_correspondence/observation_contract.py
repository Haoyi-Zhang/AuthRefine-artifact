"""Record obligations for identity observations and proposed bijection families.

These equations inspect the actual stored rows and call records. They do not
import a production policy evaluator or diagnostic traversal. A failed proposal
precondition does not reject an explicitly supplied contract family.
"""
from collections import Counter
from datetime import datetime
from itertools import permutations

from . import fixtures


def require(condition, message):
    if not condition:
        raise ValueError(message)


def row_mask(rows, size):
    identifiers = [row["id"] for row in rows]
    require(all(type(value) is int and 1 <= value <= size for value in identifiers),
            "record identity lies outside the declared row set")
    require(len(set(identifiers)) == len(identifiers), "duplicate record identities")
    return sum(1 << (value - 1) for value in identifiers)


def credential_arguments(size):
    return {name: fixtures.token_for(size, ["client", name, "lookup"])
            for name in fixtures.credentials(size)}


def propose_bijections(rows, arguments):
    """Propose a family shape only when the records support its prerequisites.

The proposal preserves all correspondences allowed by the stated review
hypothesis. It is not a claim that those alternatives were observed in a field
study, or that available token values leave the physical mapping unknown.
    """
    require(isinstance(arguments, dict) and arguments, "credential arguments are required")
    labels = sorted(arguments)
    require(all(isinstance(label, str) and label for label in labels), "invalid credential label")
    require(all(isinstance(value, str) and value for value in arguments.values()), "invalid credential argument")
    identifiers = [row["id"] for row in rows]
    tokens = [row["token"] for row in rows]
    issues = []
    if len(identifiers) != len(set(identifiers)):
        issues.append("row-identities-not-unique")
    if len(tokens) != len(set(tokens)):
        issues.append("row-token-values-not-unique")
    if len(arguments.values()) != len(set(arguments.values())):
        issues.append("credential-arguments-not-distinct")
    if len(rows) != len(labels):
        issues.append("row-and-credential-cardinalities-differ")
    if set(tokens) != set(arguments.values()):
        issues.append("credential-arguments-do-not-cover-row-tokens")
    family = None
    recorded_mapping = None
    if not issues:
        aliases = [f"credential-for-row-{value}" for value in sorted(identifiers)]
        family = [dict(zip(aliases, values)) for values in permutations(labels)]
        labels_by_token = {value: label for label, value in arguments.items()}
        recorded_mapping = {f"credential-for-row-{row['id']}": labels_by_token[row["token"]]
                            for row in sorted(rows, key=lambda row: row["id"])}
    return {"status": "supported-bijection-shape" if not issues else "unsupported-bijection-shape",
            "row_count": len(rows), "credential_count": len(labels), "issues": issues,
            "family": family, "recorded_mapping": recorded_mapping,
            "explicit_family_may_still_be_diagnosed": True,
            "scope": "Record-based prerequisites for the supplied all-bijections review hypothesis. The same token records identify the physical mapping; this proposal does not infer field ambiguity. An explicitly supplied one-to-one contract remains a separate input when these prerequisites fail."}


def check_record(size, observed, arm="baseline"):
    """Check the source operations on the declared fixed-clock fixtures."""
    require(arm in {"baseline", "omit-delete"}, "unknown observation arm")
    required = {"request", "token_argument", "returned_user_id", "selected_record", "decision",
                "before_state", "after_state", "before_rows", "after_rows", "removed_ids", "store_changed"}
    require(required <= set(observed), "native observation lacks required fields")
    request = observed["request"]
    require(request in fixtures.alphabet(size), "native request is outside the declared alphabet")
    require(observed["token_argument"] == fixtures.token_for(size, request), "native argument differs from request")
    before, after = observed["before_rows"], observed["after_rows"]
    require(row_mask(before, size) == observed["before_state"], "native before-store encoding differs")
    require(row_mask(after, size) == observed["after_state"], "native after-store encoding differs")
    token, selected = observed["token_argument"], observed["selected_record"]
    require(type(observed["before_state"]) is int and type(observed["after_state"]) is int,
            "native store encodings must be integers")
    if request[2] == "lookup":
        candidates = [row for row in before if row["token"] == token]
        if candidates:
            require(isinstance(selected, dict), "lookup did not record its selected row")
            matching = [row for row in candidates if selected == {key: row[key] for key in ("id", "token", "user_id")}]
            require(len(matching) == 1, "selected record does not match a stored token row")
            row = matching[0]
            live = (datetime.fromisoformat(row["expiry_date"]) > fixtures.NOW and
                    datetime.fromisoformat(row["max_expiry_date"]) > fixtures.NOW)
            expected_return = row["user_id"] if live else None
        else:
            require(selected is None, "missing token unexpectedly selected a row")
            expected_return = None
        require(after == before, "lookup changed a nonrenewing store")
        require(observed["returned_user_id"] == expected_return, "lookup returned the wrong user")
        require(observed["decision"] == ("allow" if expected_return is not None else "deny"), "lookup decision differs")
    else:
        require(selected is None and observed["returned_user_id"] is None and observed["decision"] == "allow",
                "removal return or selected identity differs")
        expected_after = before if arm == "omit-delete" else [row for row in before if row["token"] != token]
        require(after == expected_after, "native deletion differs from all matching token rows")
    require(observed["removed_ids"] == sorted(set(row["id"] for row in before) - set(row["id"] for row in after)),
            "native removed-row identities differ")
    require(type(observed["store_changed"]) is bool and observed["store_changed"] == (before != after),
            "native store-change observation differs")


def check_graph(size, graph, initial_rows, arm="baseline"):
    """Verify every acquired cell, prefix and source-to-table transition."""
    machine, states = graph["machine"], graph["states"]
    alphabet = fixtures.alphabet(size)
    require(machine["alphabet"] == alphabet and machine["observations"] == states, "native graph interface differs")
    require(len(set(states)) == len(states), "duplicate native graph state")
    initial = row_mask(initial_rows, size)
    require(states[machine["initial"]] == initial, "native graph initial store differs")
    cells, prefixes = {}, 0
    for edge in graph["edges"]:
        key = (edge["from_state"], edge["input_index"])
        require(key not in cells, "duplicate native graph cell")
        cells[key] = edge["observation"]
        require(len(edge["prefix"]) == len(edge["prefix_observations"]), "native prefix length differs")
        store = initial_rows
        records = edge["prefix_observations"] + [edge["observation"]]
        indices = edge["prefix"] + [edge["input_index"]]
        for index, observed in zip(indices, records):
            require(type(index) is int and 0 <= index < len(alphabet), "native request index is invalid")
            require(observed["request"] == alphabet[index], "native recorded word differs")
            require(observed["before_rows"] == store, "native full-store prefix continuity differs")
            check_record(size, observed, arm)
            store = observed["after_rows"]
        observed = edge["observation"]
        require(observed["before_state"] == edge["from_state"], "native cell starts at another store")
        target_row = machine["transitions"][states.index(edge["from_state"])][edge["input_index"]]
        require(target_row == [observed["decision"], states.index(observed["after_state"])], "source-to-table cell differs")
        prefixes += len(edge["prefix"])
    require(set(cells) == {(state, index) for state in states for index in range(len(alphabet))},
            "native graph is not complete over its reached states")
    reached = {initial}
    while True:
        expanded = reached | {cells[state, index]["after_state"] for state in reached for index in range(len(alphabet))}
        if expanded == reached:
            break
        reached = expanded
    require(reached == set(states), "native graph contains unreachable or omitted states")
    require(prefixes == graph["prefix_operations"] and len(cells) + prefixes == graph["source_operations"],
            "native graph operation counts differ")
    return cells


def selected_map(graph):
    states = graph["states"]
    return {(states.index(edge["from_state"]), edge["input_index"]):
            None if edge["observation"]["selected_record"] is None else edge["observation"]["selected_record"]["id"]
            for edge in graph["edges"]}


def reference_output(size, state, request, binding):
    """Independent direct equation, including the selected-row observation."""
    resource, action = request[1:]
    present = {row for row in range(1, size + 1) if state & (1 << (row - 1))}
    if action == "remove":
        remaining = present - {row for row in present if resource == f"row-{row}"}
        return "allow", sum(1 << (row - 1) for row in remaining), None
    selected = sorted(row for row in present if binding[f"credential-for-row-{row}"] == resource)
    return ("allow" if selected else "deny"), state, selected[0] if selected else None


def native_replay_rows(case, binding, caller_name, indices, observations, *, identity=True):
    """Derive a complete reference/native comparison from the physical records."""
    size, machine = case["sessions"], case["machine"]
    caller = case["callers"][caller_name]
    source, target, call = (1 << size) - 1, machine["initial"], caller["initial"]
    require(len(indices) == len(observations), "native replay record count differs")
    result = []
    for index, observed in zip(indices, observations):
        require(type(index) is int and 0 <= index < len(machine["alphabet"]), "native replay index is invalid")
        request = machine["alphabet"][index]
        require(observed["request"] == request, "native replay request differs from declared word")
        next_call = caller["transitions"][call][index]
        require(next_call is not None, "native replay word is not admitted by the caller")
        require(observed["before_state"] == machine["observations"][target], "native replay target-state continuity differs")
        check_record(size, observed, case["arm"])
        decision, successor = machine["transitions"][target][index]
        require((observed["decision"], observed["after_state"]) == (decision, machine["observations"][successor]),
                "native replay disagrees with acquired table")
        reference_decision, reference_state, reference_identity = reference_output(size, source, request, binding)
        actual = [reference_decision, reference_state]
        expected = [observed["decision"], observed["after_state"]]
        row = {"request": list(request), "binding": dict(binding), "source": actual, "target": expected,
               "decision_equal": actual[0] == expected[0], "state_equal": actual[1] == expected[1],
               "compared_equal": actual == expected, "source_state": source, "target_state": target,
               "protocol_state": call}
        if identity:
            recorded = observed["selected_record"]
            observed_identity = None if recorded is None else recorded["id"]
            row.update(reference_selected_row=reference_identity, observed_selected_row=observed_identity,
                       identity_equal=reference_identity == observed_identity,
                       compared_equal=actual == expected and reference_identity == observed_identity)
        result.append(row)
        source, target, call = reference_state, successor, next_call
    require(result and all(row["compared_equal"] for row in result[:-1]) and not result[-1]["compared_equal"],
            "native complete replay does not first disagree at its final request")
    return result


def summarize_profiles(records):
    return {"bindings": len(records), "matching": sum(row["equivalent"] for row in records),
            "excluded": sum(not row["equivalent"] for row in records),
            "shortest_lengths": dict(sorted(Counter("infinity" if row["length"] is None else str(row["length"])
                                                     for row in records).items()))}
