"""Failure-directed controls for binding-family diagnosis with caller state."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ARTIFACT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT / "src"))
from checker import Rejected
from extensions import binding_profile
from language import normalize
from protocol_check import verify_protocol
from protocol_profile import protocol_binding_profile

_SPEC = importlib.util.spec_from_file_location("protocol_family_audit", ARTIFACT / "proofs/protocol_family_audit.py")
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


def phase_example():
    policy = normalize({
        "principals": ["caller"], "resources": ["object"], "actions": ["a", "b"],
        "roles": ["administrator", "outsider"], "members": [["caller", "administrator"]],
        "state": [], "aliases": [{"kind": "role", "name": "mode",
                                     "candidates": ["administrator", "outsider"]}],
        "rules": [
            {"decision": "allow", "guard": [{"field": "action", "name": "a", "negated": False}], "updates": []},
            {"decision": "allow", "guard": [{"field": "role", "alias": "mode", "negated": False}], "updates": []},
        ],
    })
    machine = {"state_names": [], "alphabet": [["caller", "object", "a"], ["caller", "object", "b"]],
               "observations": [0], "initial": 0,
               "transitions": [[["allow", 0], ["allow", 0]]]}
    protocol = {"initial": 0, "transitions": [[1, None], [2, None], [None, 3], [None, None]]}
    return policy, machine, protocol


class ProtocolProfileTests(unittest.TestCase):
    def test_one_graph_classifies_family_and_retains_shortest_caller_history(self):
        policy, machine, protocol = phase_example()
        result = protocol_binding_profile(policy, machine, protocol)
        self.assertEqual(result["classification"], "some")
        self.assertEqual(result["matching_family"], [{"mode": "administrator"}])
        self.assertEqual(result["strata"], {"infinity": 1, "3": 1})
        self.assertEqual(result["graph_traversals"], 1)
        self.assertEqual(result["target_reachable_states"], 1)
        self.assertEqual(result["target_protocol_reachable_states"], 4)
        self.assertEqual(result["graph_enabled_edges"], 3)
        witness = result["profiles"][1]
        self.assertEqual(witness["indices"], [0, 0, 1])
        self.assertEqual([row["protocol_state"] for row in witness["trace"]], [0, 1, 2])
        self.assertEqual({tuple(row["binding"].items()) for row in witness["trace"]},
                         {(("mode", "outsider"),)})
        self.assertTrue(all(row["compared_equal"] for row in witness["trace"][:-1]))
        self.assertFalse(witness["trace"][-1]["compared_equal"])
        self.assertEqual(binding_profile(policy, machine)["shortest_failure"], 1)

    def test_all_enabled_caller_reduces_to_existing_binding_profile(self):
        left = (("allow", 1), ("deny", 1))
        right = (("allow", 0), ("allow", 1))
        policy, machine, _ = audit.inputs(left, right, left, (0, 0))
        protocol = {"initial": 0, "transitions": [[0]]}
        new = protocol_binding_profile(policy, machine, protocol)
        old = binding_profile(policy, machine)
        for key in ("classification", "matching_bindings", "failing_bindings", "strata", "transition_evaluations"):
            self.assertEqual(new[key], old[key])
        for new_row, old_row in zip(new["profiles"], old["profiles"], strict=True):
            for key in ("binding", "equivalent", "length", "indices"):
                self.assertEqual(new_row[key], old_row[key])

    def test_two_events_carry_policy_state_before_a_binding_is_distinguished(self):
        policy, _, _ = phase_example()
        policy["state"] = [["ready", False]]
        policy["rules"] = [
            {"decision": "allow", "guard": [{"field": "action", "name": "a", "negated": False}],
             "updates": [{"name": "ready", "value": True}]},
            {"decision": "allow", "guard": [
                {"field": "state", "name": "ready", "value": True},
                {"field": "role", "alias": "mode", "negated": False}], "updates": []},
        ]
        machine = {"state_names": ["ready"],
                   "alphabet": [["caller", "object", "a"], ["caller", "object", "b"]],
                   "observations": [0, 1], "initial": 0,
                   "transitions": [[["allow", 1], ["deny", 0]],
                                   [["allow", 1], ["allow", 1]]]}
        protocol = {"initial": 0, "transitions": [[1, None], [0, 1]]}
        result = protocol_binding_profile(policy, machine, protocol)
        self.assertEqual(result["strata"], {"infinity": 1, "2": 1})
        row = result["profiles"][1]
        self.assertEqual(row["indices"], [0, 1])
        self.assertEqual([step["source_state"] for step in row["trace"]], [0, 1])
        self.assertEqual(row["trace"][0]["source"], ["allow", 1])
        self.assertEqual(row["trace"][1]["source"], ["deny", 1])
        self.assertEqual(row["trace"][1]["target"], ["allow", 1])

    def test_initial_disagreement_precedes_inactive_or_missing_event_admission(self):
        table = (("deny", 0), ("deny", 1))
        policy, machine, protocol = audit.inputs(table, table, (None, None), (None, None))
        machine["initial"] = 1
        result = protocol_binding_profile(policy, machine, protocol)
        self.assertEqual(result["classification"], "none")
        self.assertEqual(result["strata"], {"0": 2})
        self.assertEqual(result["graph_traversals"], 0)
        self.assertEqual(result["transition_evaluations"], 0)
        self.assertTrue(all(row["indices"] == [] and row["trace"] == [] for row in result["profiles"]))

    def test_no_admitted_event_is_inconclusive_with_equal_initials(self):
        policy, machine, _ = phase_example()
        with self.assertRaises(Rejected) as caught:
            protocol_binding_profile(policy, machine, {"initial": 0, "transitions": [[None, None]]})
        self.assertEqual(caught.exception.kind, "inconclusive")

    def test_missing_enabled_edge_is_not_completed_with_a_denial(self):
        policy, machine, protocol = phase_example()
        machine["transitions"][0][1] = None
        with self.assertRaises(Rejected) as caught:
            protocol_binding_profile(policy, machine, protocol)
        self.assertEqual(caught.exception.kind, "inconclusive")
        self.assertEqual(caught.exception.details["indices"], [0, 0, 1])

    def test_missing_later_edge_prevents_a_partial_matching_family(self):
        # Even an early exclusion does not establish a complete family profile
        # if another admitted target transition is absent.
        policy, machine, _ = phase_example()
        machine["transitions"][0][0] = None
        protocol = {"initial": 0, "transitions": [[None, 1], [2, None], [None, None]]}
        with self.assertRaises(Rejected) as caught:
            protocol_binding_profile(policy, machine, protocol)
        self.assertEqual(caught.exception.kind, "inconclusive")
        self.assertEqual(caught.exception.details["indices"], [1, 0])

    def test_missing_disabled_cells_are_outside_the_declared_obligation(self):
        policy, machine, _ = phase_example()
        machine["transitions"][0][1] = None
        protocol = {"initial": 0, "transitions": [[0, None]]}
        result = protocol_binding_profile(policy, machine, protocol)
        self.assertEqual(result["classification"], "all")
        self.assertEqual(result["protocol_excluded_missing_cells"], 1)

    def test_post_state_difference_is_kept_when_decisions_agree(self):
        consumed = (("allow", 1), ("deny", 1))
        stutter = (("allow", 0), ("allow", 1))
        result = protocol_binding_profile(*audit.inputs(consumed, consumed, stutter, (0, 0)))
        self.assertEqual(result["strata"], {"1": 2})
        self.assertTrue(all(row["trace"][0]["decision_equal"] for row in result["profiles"]))
        self.assertTrue(all(not row["trace"][0]["state_equal"] for row in result["profiles"]))

    def test_explicit_correlated_family_is_not_cartesian_completed(self):
        policy, machine, protocol = phase_example()
        policy["aliases"].append({"kind": "role", "name": "unused", "candidates": ["administrator", "outsider"]})
        family = [{"mode": "administrator", "unused": "outsider"},
                  {"mode": "outsider", "unused": "administrator"}]
        result = protocol_binding_profile(policy, machine, protocol, family=family)
        self.assertEqual(result["bindings"], 2)
        self.assertEqual([row["binding"] for row in result["profiles"]], family)
        self.assertEqual(protocol_binding_profile(policy, machine, protocol)["bindings"], 4)

    def test_family_is_deduplicated_but_duplicate_inputs_consume_the_cap(self):
        inputs = phase_example()
        binding = {"mode": "administrator"}
        result = protocol_binding_profile(*inputs, family=[binding, binding])
        self.assertEqual(result["bindings"], 1)
        self.assertEqual(result["work_breakdown"]["family_members"], 2)
        with self.assertRaises(Rejected) as caught:
            protocol_binding_profile(*inputs, family=[binding, binding], family_limit=1)
        self.assertEqual(caught.exception.kind, "inconclusive")

    def test_cartesian_family_cap_is_checked_before_semantic_evaluation(self):
        with patch("protocol_profile.reference_step", side_effect=AssertionError("must not evaluate")):
            with self.assertRaises(Rejected) as caught:
                protocol_binding_profile(*phase_example(), family_limit=1)
        self.assertEqual(caught.exception.kind, "inconclusive")

    def test_empty_or_incomplete_bindings_and_invalid_protocol_are_rejected(self):
        for family in ([], [{}], [{"mode": "absent"}]):
            with self.subTest(family=family), self.assertRaises(Rejected) as caught:
                protocol_binding_profile(*phase_example(), family=family)
            self.assertEqual(caught.exception.kind, "invalid")
        policy, machine, protocol = phase_example()
        for invalid in ({"initial": False, "transitions": [[0, 0]]},
                        {"initial": 0, "transitions": [[True, 0]]},
                        {"initial": 0, "transitions": [[0]]},
                        {"initial": 0, "transitions": [[0, 17]]}):
            with self.subTest(protocol=invalid), self.assertRaises(Rejected) as caught:
                protocol_binding_profile(policy, machine, invalid)
            self.assertEqual(caught.exception.kind, "invalid")

    def test_budget_counts_graph_diagnosis_and_replay_separately(self):
        inputs = phase_example()
        result = protocol_binding_profile(*inputs)
        self.assertEqual(result["work_operations"], sum(result["work_breakdown"].values()))
        self.assertEqual(result["work_breakdown"], {"family_members": 2, "graph_cells": 8,
                                                    "semantic_steps": 6, "replay_steps": 3})
        self.assertEqual(protocol_binding_profile(*inputs, budget=19)["strata"], result["strata"])
        with self.assertRaises(Rejected) as caught:
            protocol_binding_profile(*inputs, budget=18)
        self.assertEqual(caught.exception.kind, "inconclusive")

    def test_inputs_remain_unchanged(self):
        inputs = phase_example()
        before = copy.deepcopy(inputs)
        protocol_binding_profile(*inputs)
        self.assertEqual(inputs, before)

    def test_single_binding_agrees_with_existing_fixed_protocol_checker(self):
        policy, machine, protocol = phase_example()
        for value in ("administrator", "outsider"):
            expected = protocol_binding_profile(policy, machine, protocol, family=[{"mode": value}])
            fixed = copy.deepcopy(policy)
            fixed["aliases"] = []
            for rule in fixed["rules"]:
                for atom in rule["guard"]:
                    if "alias" in atom:
                        atom.pop("alias")
                        atom["name"] = value
            result = verify_protocol(fixed, machine, protocol)
            self.assertEqual(result["accepted"], expected["accepted"])
            if not result["accepted"]:
                self.assertEqual(result["length"], expected["shortest_failure"])


class ProtocolFamilyAuditControls(unittest.TestCase):
    def test_declared_domain_tables_are_complete_and_unique(self):
        for generator, count in ((audit.reference_tables, 9), (audit.target_tables, 25), (audit.caller_tables, 9)):
            rows = list(generator())
            self.assertEqual(len(rows), count)
            self.assertEqual(len(set(rows)), count)

    def test_direct_oracle_detects_broken_shared_reference_evaluator(self):
        deny = (("deny", 0), ("deny", 1))
        allow = (("allow", 0), ("allow", 1))
        with patch("protocol_profile.reference_step", return_value=("allow", 0)):
            with self.assertRaises(AssertionError):
                audit.compare_case(deny, deny, allow, (0, 0))

    def test_direct_oracle_checks_witness_rows_not_only_lengths(self):
        deny = (("deny", 0), ("deny", 1))
        allow = (("allow", 0), ("allow", 1))
        result = protocol_binding_profile(*audit.inputs(deny, deny, allow, (0, 0)))
        result["profiles"][0]["trace"][0]["protocol_state"] = 1
        with patch.object(audit, "protocol_binding_profile", return_value=result):
            with self.assertRaises(AssertionError):
                audit.compare_case(deny, deny, allow, (0, 0))

    def test_direct_oracle_distinguishes_missing_inactive_and_classified(self):
        deny = (("deny", 0), ("deny", 1))
        self.assertEqual(audit.compare_case(deny, deny, (None, None), (0, 0))["admission"], "missing")
        self.assertEqual(audit.compare_case(deny, deny, (None, None), (None, None))["admission"], "inactive")
        self.assertEqual(audit.compare_case(deny, deny, deny, (0, 0))["classification"], "all")


if __name__ == "__main__":
    unittest.main()
