"""Source-acquired lifecycle tables, supplied correspondence contracts, oracles."""
from collections import deque
from itertools import product
from pathlib import Path
import sys

from .fixtures import alphabet

ART = Path(__file__).resolve().parents[2]
if str(ART / "src") not in sys.path:
    sys.path.insert(0, str(ART / "src"))
from extensions import binding_profile, switching_oracle
from family_diagnosis import support_indexed_profile
from language import normalize
from protocol_profile import protocol_binding_profile


IDENTITY = {"credential-for-row-a": "credential-a", "credential-for-row-b": "credential-b"}
SWAPPED = {"credential-for-row-a": "credential-b", "credential-for-row-b": "credential-a"}
FAMILY = [IDENTITY, SWAPPED]


def policy():
    def name(field, value):
        return {"field": field, "name": value, "negated": False}
    def alias(value):
        return {"field": "resource", "alias": value, "negated": False}
    def state(value):
        return {"field": "state", "name": value, "value": True}
    def rule(guard, updates=None):
        return {"guard": guard, "updates": updates or [], "decision": "allow"}
    return normalize({"principals": ["client"], "resources": [r for _, r, a in alphabet() if a == "lookup"],
                      "actions": ["lookup", "remove"], "roles": [], "members": [],
                      "state": [["session-a-present", True], ["session-b-present", True]],
                      "aliases": [{"name": key, "kind": "resource", "candidates": ["credential-a", "credential-b"]}
                                  for key in IDENTITY],
                      "rules": [
                          rule([name("action", "remove"), name("resource", "row-a")],
                               [{"name": "session-a-present", "value": False}]),
                          rule([name("action", "remove"), name("resource", "row-b")],
                               [{"name": "session-b-present", "value": False}]),
                          rule([name("action", "remove")]),
                          rule([name("action", "lookup"), alias("credential-for-row-a"), state("session-a-present")]),
                          rule([name("action", "lookup"), alias("credential-for-row-b"), state("session-b-present")])]})


def contract_step(state, request, binding):
    """Direct contract equations; no compiler, rule evaluator or saved result."""
    _, resource, action = request
    if action == "remove":
        if resource == "row-a":
            state &= ~1
        elif resource == "row-b":
            state &= ~2
        return "allow", state
    active = ((resource == binding["credential-for-row-a"] and bool(state & 1))
              or (resource == binding["credential-for-row-b"] and bool(state & 2)))
    return ("allow" if active else "deny"), state


def oracle(machine, binding, decisions_only=False, selected_identity=None, protocol=None):
    """Independent explicit reference×target×caller BFS using direct equations."""
    protocol = protocol or {"initial": 0, "transitions": [[0] * len(alphabet())]}
    initial = (3, machine["initial"], protocol["initial"])
    waiting, paths = deque([initial]), {initial: []}
    compared = 0
    while waiting:
        ref, target, caller = current = waiting.popleft()
        for index, request in enumerate(machine["alphabet"]):
            next_caller = protocol["transitions"][caller][index]
            if next_caller is None:
                continue
            expected, next_ref = contract_step(ref, request, binding)
            actual, next_target = machine["transitions"][target][index]
            compared += 1
            different = expected != actual or (not decisions_only and next_ref != machine["observations"][next_target])
            # At this richer boundary, the selected existing row itself is an
            # observable. This deliberately stronger mode is separate from the
            # decision+presence-state finite contract used by AuthRefine here.
            if selected_identity is not None and request[2] == "lookup":
                resource = request[1]
                expected_row = next((row for row, key in ((1, "credential-for-row-a"), (2, "credential-for-row-b"))
                                     if resource == binding[key] and ref & (1 << (row - 1))), None)
                actual_row = selected_identity[(machine["observations"][target], index)]
                different = different or expected_row != actual_row
            if different:
                indices = paths[current] + [index]
                return {"equivalent": False, "length": len(indices), "indices": indices,
                        "visited_products": len(paths), "compared_cells": compared}
            following = (next_ref, next_target, next_caller)
            if following not in paths:
                paths[following] = paths[current] + [index]
                waiting.append(following)
    return {"equivalent": True, "length": None, "indices": None,
            "visited_products": len(paths), "compared_cells": compared}


def proper_prefixes(machine, binding, length, decisions_only=False):
    count = 0
    for size in range(length):
        for word in product(range(len(machine["alphabet"])), repeat=size):
            ref, target = 3, machine["initial"]
            count += 1
            for index in word:
                expected, ref = contract_step(ref, machine["alphabet"][index], binding)
                actual, target = machine["transitions"][target][index]
                if expected != actual or (not decisions_only and ref != machine["observations"][target]):
                    raise ValueError("claimed shortest lifecycle witness has a shorter word")
    return count


def signature(profile):
    return [(row["binding"], row["equivalent"], row["length"]) for row in profile["profiles"]]


def diagnose(acquired):
    p = policy()
    full_protocol = {"initial": 0, "transitions": [[0] * len(alphabet())]}
    # This caller admits every lookup from the start and at most one removal.
    # It does not create the two-step witness; the unrestricted machine already
    # has that minimum. It exercises composition with a real lifecycle scope.
    one_removal = {"initial": 0, "transitions": [
        [1 if request[2] == "remove" else 0 for request in alphabet()],
        [None if request[2] == "remove" else 1 for request in alphabet()]]}
    result = {"policy": p, "supplied_family": FAMILY, "profiles": {}}
    for name in ("baseline", "omit_delete"):
        m = acquired[name]["machine"]
        local = binding_profile(p, m, family=FAMILY)
        indexed = support_indexed_profile(p, m, family=FAMILY)
        if local["profiles"] != indexed["profiles"]:
            raise ValueError("support-indexed lifecycle profile differs from complete-family scan")
        combined = protocol_binding_profile(p, m, full_protocol, family=FAMILY)
        restricted = protocol_binding_profile(p, m, one_removal, family=FAMILY)
        if signature(local) != signature(combined) or signature(local) != signature(restricted):
            raise ValueError("lifecycle family and caller results disagree")
        independent = []
        selected_rows = {(edge["from_state"], edge["input_index"]):
                         None if edge["observation"]["selected_record"] is None else edge["observation"]["selected_record"]["id"]
                         for edge in acquired[name]["edges"]}
        for row in local["profiles"]:
            binding = row["binding"]
            exact = oracle(m, binding)
            admitted = oracle(m, binding, protocol=one_removal)
            if (row["equivalent"], row["length"]) != (exact["equivalent"], exact["length"]):
                raise ValueError("lifecycle direct-equation oracle disagrees")
            if (exact["equivalent"], exact["length"]) != (admitted["equivalent"], admitted["length"]):
                raise ValueError("restricted caller oracle disagrees")
            decision = switching_oracle(p, m, family=[binding], decisions_only=True)
            direct_decision = oracle(m, binding, decisions_only=True)
            if (decision["equivalent"], decision["length"]) != (direct_decision["equivalent"], direct_decision["length"]):
                raise ValueError("decision-only product oracle disagrees")
            independent.append({"binding": binding, "full": exact, "decision_only": direct_decision,
                                "richer_selected_identity": oracle(m, binding, selected_identity=selected_rows),
                                "full_shorter_words": 0 if exact["length"] is None else proper_prefixes(m, binding, exact["length"]),
                                "decision_shorter_words": 0 if decision["length"] is None else proper_prefixes(m, binding, decision["length"], True),
                                "decision_product_replay": decision})
        result["profiles"][name] = {"binding_profile": local, "all_enabled_protocol": combined,
                                    "support_indexed_profile": indexed,
                                    "one_removal_protocol": restricted, "independent": independent}
    result["caller_protocols"] = {"all_enabled": full_protocol, "one_removal": one_removal}
    expected = {"baseline": [(True, None), (False, 2)], "omit_delete": [(False, 1), (False, 1)]}
    for name, values in expected.items():
        if [(r["equivalent"], r["length"]) for r in result["profiles"][name]["binding_profile"]["profiles"]] != values:
            raise ValueError("source lifecycle does not realize the stated diagnostic distinction")
    if any(row["decision_only"]["length"] != 2 for row in result["profiles"]["omit_delete"]["independent"]):
        raise ValueError("omitted delete must be distinguishable on the second decision")
    return result


async def replay_native(diagnosis):
    from .native import NativeSession
    output = []
    for name, profile in diagnosis["profiles"].items():
        session = NativeSession(None if name == "baseline" else name)
        try:
            await session.initialize()
            for row in profile["binding_profile"]["profiles"]:
                if row["equivalent"]:
                    continue
                await session.reset()
                observations = []
                ref = 3
                for index in row["indices"]:
                    request = alphabet()[index]
                    observed = await session.invoke(request)
                    decision, ref = contract_step(ref, request, row["binding"])
                    observations.append({"observation": observed, "reference_decision": decision,
                                         "reference_state": ref,
                                         "equal": decision == observed["decision"] and ref == observed["after_state"]})
                if not observations or any(not item["equal"] for item in observations[:-1]) or observations[-1]["equal"]:
                    raise ValueError("native witness replay does not first diverge at its final step")
                output.append({"profile": name, "mode": "full", "binding": row["binding"], "observations": observations})
            for row in profile["independent"]:
                diagnostic = row["decision_only"]
                if diagnostic["equivalent"]:
                    continue
                await session.reset()
                observations, ref = [], 3
                for index in diagnostic["indices"]:
                    request = alphabet()[index]
                    observed = await session.invoke(request)
                    decision, ref = contract_step(ref, request, row["binding"])
                    observations.append({"observation": observed, "reference_decision": decision,
                                         "reference_state": ref, "equal": decision == observed["decision"]})
                if any(not item["equal"] for item in observations[:-1]) or observations[-1]["equal"]:
                    raise ValueError("native decision witness does not first diverge at its final step")
                output.append({"profile": name, "mode": "decision_only", "binding": row["binding"], "observations": observations})
        finally:
            session.close()
    return output
