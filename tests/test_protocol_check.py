import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from checker import Rejected, verify_reachable
from language import normalize
from protocol_check import verify_protocol


def example():
    policy = normalize({"principals": ["api"], "resources": ["engine"], "actions": ["check", "prepare"],
                        "roles": [], "members": [], "state": [["ready", False]], "aliases": [],
                        "rules": [{"decision": "allow", "guard": [{"field": "action", "name": "prepare", "negated": False}],
                                   "updates": [{"name": "ready", "value": True}]}]})
    machine = {"state_names": ["ready"], "alphabet": [["api", "engine", "check"], ["api", "engine", "prepare"]],
               "observations": [0, 1], "initial": 0,
               "transitions": [[None, ["allow", 1]], [["deny", 1], ["allow", 1]]]}
    protocol = {"initial": 0, "transitions": [[None, 1], [0, None]]}
    return policy, machine, protocol


class ProtocolCheckTests(unittest.TestCase):
    def test_protocol_constrained_component_refinement(self):
        result = verify_protocol(*example())
        self.assertTrue(result["accepted"])
        self.assertGreater(result["protocol_excluded_missing_cells"], 0)
        self.assertFalse(result["unconditional_external_api_refinement"])

    def test_missing_reachable_edge_is_inconclusive(self):
        policy, machine, protocol = example()
        machine["transitions"][1][0] = None
        with self.assertRaises(Rejected) as caught:
            verify_protocol(policy, machine, protocol)
        self.assertEqual(caught.exception.kind, "inconclusive")

    def test_widened_protocol_cannot_turn_a_missing_cell_into_denial(self):
        policy, machine, protocol = example()
        protocol["transitions"][0][0] = 0
        with self.assertRaises(Rejected):
            verify_protocol(policy, machine, protocol)

    def test_shortest_protocol_admitted_witness(self):
        policy, machine, protocol = example()
        machine["transitions"][1][0] = ["allow", 1]
        result = verify_protocol(policy, machine, protocol)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["length"], 2)
        self.assertEqual([step["request"][2] for step in result["trace"]], ["prepare", "check"])

    def test_protocol_history_cannot_be_merged_by_target_state(self):
        # The target has one state, but the caller permits b only after k a's.
        # A target-only BFS would incorrectly return b or miss the later phase.
        policy = normalize({
            "principals": ["api"], "resources": ["engine"], "actions": ["a", "b"],
            "roles": [], "members": [], "state": [], "aliases": [],
            "rules": [{"decision": "allow", "guard": [
                {"field": "action", "name": "a", "negated": False}], "updates": []}],
        })
        machine = {"state_names": [], "alphabet": [["api", "engine", "a"], ["api", "engine", "b"]],
                   "observations": [0], "initial": 0,
                   "transitions": [[["allow", 0], ["allow", 0]]]}
        self.assertEqual(verify_reachable(policy, machine)["length"], 1)
        for k in (1, 2, 5, 14):
            with self.subTest(allowed_a_prefix=k):
                protocol = {"initial": 0,
                            "transitions": [[i + 1, None] for i in range(k)]
                                           + [[None, k + 1], [None, None]]}
                result = verify_protocol(policy, machine, protocol)
                self.assertEqual(result["status"], "mismatch")
                self.assertEqual(result["length"], k + 1)
                self.assertGreater(result["length"], len(machine["observations"]))
                self.assertEqual([step["request"][2] for step in result["trace"]], ["a"] * k + ["b"])
                self.assertEqual([step["protocol_state"] for step in result["trace"]], list(range(k + 1)))
                self.assertTrue(all(step["source"] == step["target"] for step in result["trace"][:-1]))
                self.assertNotEqual(result["trace"][-1]["source"], result["trace"][-1]["target"])

    def test_empty_language_and_zero_budget_are_not_clean_results(self):
        policy, machine, protocol = example()
        for p, budget in [({"initial": 0, "transitions": [[None, None]]}, 100), (protocol, 0)]:
            with self.assertRaises(Rejected) as caught:
                verify_protocol(policy, machine, p, budget)
            self.assertEqual(caught.exception.kind, "inconclusive")

    def test_inputs_are_not_modified(self):
        inputs = example()
        before = copy.deepcopy(inputs)
        verify_protocol(*inputs)
        self.assertEqual(inputs, before)


if __name__ == "__main__":
    unittest.main()
