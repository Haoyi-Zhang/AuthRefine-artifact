"""Semantic and admission controls for active grouping with caller history."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from checker import Rejected
from protocol_profile import protocol_binding_profile
from protocol_grouped import support_indexed_protocol_profile
import protocol_grouped as grouped

_SPEC = importlib.util.spec_from_file_location("overlap_protocol_tests", ROOT / "proofs/audit_support_overlap.py")
overlap = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(overlap)


def example():
    return overlap.policy(), overlap.baseline_target(), {"initial": 0, "transitions": [[0, 0, 0, 0]]}


class GroupedCallerTests(unittest.TestCase):
    def check_same(self, policy, machine, protocol, family=None):
        scan = protocol_binding_profile(policy, machine, protocol, family=family)
        result = support_indexed_protocol_profile(policy, machine, protocol, family=family)
        for key in ("profiles", "matching_family", "classification", "strata", "shortest_failure",
                    "target_protocol_reachable_states", "protocol_disabled_cells",
                    "protocol_excluded_missing_cells"):
            self.assertEqual(result[key], scan[key], key)
        self.assertEqual(result["work_operations"], sum(result["work_breakdown"].values()))
        return result, scan

    def test_overlap_indexes_reused_after_retirement_under_caller_product(self):
        result, scan = self.check_same(*example())
        self.assertEqual(result["strata"], {"infinity": 1, "2": 6, "3": 1})
        self.assertEqual(result["cached_supports"], 4)
        self.assertEqual(result["index_memberships_created"], 32)
        self.assertEqual(result["index_memberships_removed"], 28)
        self.assertLess(result["transition_evaluations"], scan["transition_evaluations"])
        self.assertEqual(result["replay_evaluations"], scan["replay_evaluations"])

    def test_correlated_family_all_nonempty_subsets_keep_exact_members(self):
        for mask in range(1, 256):
            with self.subTest(mask=mask):
                self.check_same(*example(), family=overlap.family(mask))

    def test_protocol_delays_first_difference_and_carries_same_binding(self):
        policy, machine, _ = example()
        # Three ticks are required before any probe is permitted.
        protocol = {"initial": 0, "transitions": [[None, None, None, 1],
                                                     [None, None, None, 2],
                                                     [None, None, None, 3],
                                                     [3, 3, 3, None]]}
        result, _ = self.check_same(policy, machine, protocol)
        self.assertEqual(result["strata"], {"infinity": 1, "4": 7})
        for row in result["profiles"][1:]:
            self.assertEqual(row["indices"][:3], [3, 3, 3])
            self.assertEqual([r["protocol_state"] for r in row["trace"]], [0, 1, 2, 3])
            self.assertTrue(all(r["binding"] == row["binding"] for r in row["trace"]))

    def test_initial_mismatch_does_not_attempt_graph_or_support(self):
        policy, machine, _ = example()
        machine["initial"] = 1
        machine["transitions"] = [[None] * 4 for _ in range(4)]
        protocol = {"initial": 0, "transitions": [[None] * 4]}
        with patch.object(grouped, "_reachable_product", side_effect=AssertionError("no graph")), \
             patch.object(grouped, "support", side_effect=AssertionError("no support")):
            result = support_indexed_protocol_profile(policy, machine, protocol)
        self.assertEqual(result["strata"], {"0": 8})
        self.assertEqual(result["graph_traversals"], 0)
        self.assertEqual(result["cached_supports"], 0)

    def test_admission_completes_before_even_an_early_universal_failure(self):
        policy, machine, protocol = example()
        machine["transitions"][0][0][0] = "deny"  # All bindings would fail here.
        machine["transitions"][3][1] = None       # A later admitted edge is missing.
        with patch.object(grouped, "reference_step", side_effect=AssertionError("admit first")):
            with self.assertRaises(Rejected) as caught:
                support_indexed_protocol_profile(policy, machine, protocol)
        self.assertEqual(caught.exception.kind, "inconclusive")
        self.assertEqual(caught.exception.details["indices"], [3, 3, 3, 1])

    def test_disabled_missing_edges_do_not_constrain_the_family(self):
        policy, machine, _ = example()
        for row in machine["transitions"]:
            row[3] = None
        protocol = {"initial": 0, "transitions": [[0, 0, 0, None]]}
        result, _ = self.check_same(policy, machine, protocol)
        self.assertEqual(result["classification"], "all")
        self.assertEqual(result["protocol_excluded_missing_cells"], 1)

    def test_empty_caller_and_family_caps_are_inconclusive(self):
        policy, machine, _ = example()
        with self.assertRaises(Rejected) as caught:
            support_indexed_protocol_profile(policy, machine, {"initial": 0, "transitions": [[None] * 4]})
        self.assertEqual(caught.exception.kind, "inconclusive")
        binding = overlap.family(1)[0]
        with self.assertRaises(Rejected) as caught:
            support_indexed_protocol_profile(*example(), family=[binding, binding], family_limit=1)
        self.assertEqual(caught.exception.kind, "inconclusive")

    def test_exact_work_budget_has_no_partial_family_below_boundary(self):
        result = support_indexed_protocol_profile(*example())
        exact = support_indexed_protocol_profile(*example(), budget=result["work_operations"])
        self.assertEqual(exact["profiles"], result["profiles"])
        with self.assertRaises(Rejected) as caught:
            support_indexed_protocol_profile(*example(), budget=result["work_operations"] - 1)
        self.assertEqual(caught.exception.kind, "inconclusive")

    def test_grouping_fault_changes_answer_and_independent_profile_exposes_it(self):
        # A broken dependency set groups all legal interpretations together.
        with patch.object(grouped, "support", return_value=[]):
            broken = support_indexed_protocol_profile(*example())
        correct = protocol_binding_profile(*example())
        self.assertEqual(broken["matching_bindings"], 8)
        self.assertEqual(correct["matching_bindings"], 1)
        self.assertNotEqual(broken["profiles"], correct["profiles"])

    def test_inputs_are_unchanged_and_duplicate_family_inputs_do_not_change_results(self):
        inputs = example()
        before = copy.deepcopy(inputs)
        family = overlap.family(129)
        result, _ = self.check_same(*inputs, family=family + family)
        self.assertEqual(result["bindings"], 2)
        self.assertEqual(result["work_breakdown"]["family_members"], 4)
        self.assertEqual(inputs, before)


if __name__ == "__main__":
    unittest.main()
