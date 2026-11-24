"""Semantic and accounting controls for support-indexed family diagnosis."""
import copy
from itertools import repeat
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ARTIFACT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT / "src"))
from cases import chain_case, generated, width_case
from checker import Rejected
from compiler import compile_policy
from exhaustive_audit import direct_product
from extensions import binding_profile
from family_diagnosis import support_indexed_profile


def retiring_example():
    policy = width_case(3)
    machine = compile_policy(policy)
    for rule in policy["rules"]:
        if rule["guard"][1]["negated"]:
            rule["decision"] = "deny"
            rule["updates"] = []
    return policy, machine


def assert_profiles(test, policy, machine, family=None):
    expected = binding_profile(policy, machine, family=family)
    result = support_indexed_profile(policy, machine, family=family)
    for key in ("profiles", "classification", "strata", "bindings", "matching_bindings",
                "failing_bindings", "shortest_failure", "target_reachable_states"):
        test.assertEqual(result[key], expected[key], key)
    for row in result["profiles"]:
        length, indices = direct_product(policy, machine, row["binding"])
        test.assertEqual((row["length"], row["indices"]), (length, indices))
    return result, expected


class SupportIndexedProfileTests(unittest.TestCase):
    def test_full_profiles_equal_naive_and_independent_semantics_on_generated_cases(self):
        for index in range(128):
            policy = generated(index)
            machine = compile_policy(policy)
            if index % 3 == 0:
                decision, destination = machine["transitions"][machine["initial"]][0]
                machine["transitions"][machine["initial"]][0] = ["deny" if decision == "allow" else "allow", destination]
            with self.subTest(index=index):
                assert_profiles(self, policy, machine)

    def test_width_shares_semantics_without_erasing_family_index_cost(self):
        policy = width_case(8)
        result, naive = assert_profiles(self, policy, compile_policy(policy))
        self.assertEqual(naive["transition_evaluations"], 4096)
        self.assertEqual(result["transition_evaluations"], 32)
        self.assertEqual(result["family_projection_evaluations"], 2048)
        self.assertEqual(result["family_projection_coordinates"], 2048)
        self.assertEqual(result["index_memberships_created"], 2048)
        self.assertEqual(result["peak_cached_memberships"], 2048)
        self.assertEqual(result["work_breakdown"]["output_rows"], 256)

    def test_group_retirement_updates_all_previous_support_indexes(self):
        result, _ = assert_profiles(self, *retiring_example())
        self.assertEqual(result["matching_bindings"], 1)
        self.assertEqual(result["failing_bindings"], 7)
        self.assertEqual(result["cached_supports"], 3)
        self.assertEqual(result["index_memberships_created"], 14)
        self.assertEqual(result["index_memberships_removed"], 11)
        self.assertEqual(result["replay_evaluations"], 7)

    def test_each_failed_member_replays_its_own_unchanged_binding(self):
        policy, machine = retiring_example()
        result = support_indexed_profile(policy, machine)
        for row in result["profiles"]:
            if not row["equivalent"]:
                self.assertTrue(all(step["binding"] == row["binding"] for step in row["trace"]))
                self.assertTrue(all(step["compared_equal"] for step in row["trace"][:-1]))
                self.assertFalse(row["trace"][-1]["compared_equal"])

    def test_explicit_correlated_members_and_input_order_are_preserved(self):
        policy, machine = retiring_example()
        family = [{"x00": "s", "x01": "s", "x02": "s"},
                  {"x00": "r", "x01": "r", "x02": "r"}]
        result, _ = assert_profiles(self, policy, machine, family + [family[0]])
        self.assertEqual(result["bindings"], 2)
        self.assertEqual([row["binding"] for row in result["profiles"]], family)
        self.assertEqual(result["work_breakdown"]["family_members"], 3)

    def test_empty_support_shares_unused_aliases(self):
        policy = width_case(6)
        policy["actions"] = ["a"]
        policy["rules"] = [{"decision": "allow", "guard": [], "updates": []}]
        result, _ = assert_profiles(self, policy, compile_policy(policy))
        self.assertEqual(result["bindings"], 64)
        self.assertEqual(result["transition_evaluations"], 1)
        self.assertEqual(result["family_projection_coordinates"], 0)
        self.assertEqual(result["cached_supports"], 1)

    def test_syntactic_support_is_not_claimed_to_be_semantically_minimal(self):
        policy = width_case(2)
        policy["actions"] = ["a"]
        for rule in policy["rules"]:
            rule["guard"] = [rule["guard"][1]]
            rule["updates"] = []
        policy["rules"].insert(0, {"decision": "allow", "guard": [], "updates": []})
        result, naive = assert_profiles(self, policy, compile_policy(policy))
        self.assertEqual(result["transition_evaluations"], naive["transition_evaluations"])
        self.assertEqual(result["transition_evaluations"], 4)

    def test_initial_and_delayed_witnesses_preserve_existing_tie_break(self):
        for length in (1, 2, 3, 8, 16):
            policy, machine = chain_case(length)
            assert_profiles(self, policy, machine)
        policy, machine = retiring_example()
        machine["observations"][machine["initial"]] = 1
        result, _ = assert_profiles(self, policy, machine)
        self.assertEqual(result["strata"], {"0": 8})
        self.assertEqual(result["cached_supports"], 0)
        self.assertEqual(result["transition_evaluations"], 0)

    def test_work_envelope_covers_indexes_retirement_replay_and_output(self):
        inputs = retiring_example()
        result = support_indexed_profile(*inputs)
        self.assertEqual(result["work_operations"], sum(result["work_breakdown"].values()))
        required = {"family_members", "graph_edges", "support_queries", "support_guard_atoms",
                    "family_projections", "projection_coordinates", "index_memberships_created",
                    "index_memberships_removed", "active_group_visits", "semantic_steps",
                    "replay_steps", "output_rows"}
        self.assertEqual(set(result["work_breakdown"]), required)
        self.assertEqual(support_indexed_profile(*inputs, budget=result["work_operations"])["profiles"], result["profiles"])
        with self.assertRaises(Rejected) as caught:
            support_indexed_profile(*inputs, budget=result["work_operations"] - 1)
        self.assertEqual(caught.exception.kind, "inconclusive")

    def test_unbounded_duplicate_family_and_cartesian_oversize_are_capped(self):
        policy, machine = retiring_example()
        one = {alias["name"]: "r" for alias in policy["aliases"]}
        for options in ({"family": repeat(one), "family_limit": 3}, {"family_limit": 3}):
            with self.subTest(options=options), self.assertRaises(Rejected) as caught:
                support_indexed_profile(policy, machine, **options)
            self.assertEqual(caught.exception.kind, "inconclusive")

    def test_invalid_family_is_rejected_without_assuming_missing_alias_values(self):
        policy, machine = retiring_example()
        for family in ([], [{}], [{"x00": "r", "x01": "r", "x02": "unknown"}]):
            with self.subTest(family=family), self.assertRaises(Rejected) as caught:
                support_indexed_profile(policy, machine, family=family)
            self.assertEqual(caught.exception.kind, "invalid")

    def test_inputs_and_explicit_family_remain_unchanged(self):
        policy, machine = retiring_example()
        family = [{alias["name"]: "r" for alias in policy["aliases"]}]
        before = copy.deepcopy((policy, machine, family))
        support_indexed_profile(policy, machine, family)
        self.assertEqual((policy, machine, family), before)

    def test_independent_semantics_detects_a_missing_support_coordinate(self):
        policy, machine = retiring_example()
        with patch("family_diagnosis.support", return_value=[]):
            wrong = support_indexed_profile(policy, machine)
        self.assertEqual(wrong["matching_bindings"], 8)
        differences = [row for row in wrong["profiles"]
                       if direct_product(policy, machine, row["binding"])[0] is not None]
        self.assertEqual(len(differences), 7)


if __name__ == "__main__":
    unittest.main()
