"""Complete-output, legal-family and caller controls for both symbolic backends."""
from copy import deepcopy
import importlib.util
from itertools import product
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from checker import Rejected
from compiler import compile_policy
from diagnostic_example import example
from extensions import binding_profile
from language import normalize
from protocol_profile import protocol_binding_profile
from symbolic_family import symbolic_family_profile
import symbolic_family as symbolic

_SPEC = importlib.util.spec_from_file_location("symbolic_overlap_checks", ROOT / "proofs/audit_support_overlap.py")
overlap = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(overlap)


def semantic(result):
    return [{key: row[key] for key in ("binding", "equivalent", "length", "indices", "trace")}
            for row in result["profiles"]]


def has_cudd():
    try:
        return importlib.util.find_spec("dd.cudd") is not None
    except ModuleNotFoundError:
        return False


class CompleteSymbolicChecks:
    backend = "finite-domain"

    def run_profile(self, policy, machine, **kwargs):
        return symbolic_family_profile(policy, machine, backend=self.backend, **kwargs)

    def same(self, policy, machine, family=None, protocol=None):
        original = deepcopy((policy, machine, family, protocol))
        expected = (binding_profile(policy, machine, family=family) if protocol is None else
                    protocol_binding_profile(policy, machine, protocol, family=family))
        actual = self.run_profile(policy, machine, family=family, protocol=protocol)
        self.assertEqual(semantic(actual), semantic(expected))
        for key in ("classification", "bindings", "matching_bindings", "strata"):
            self.assertEqual(actual[key], expected[key], key)
        self.assertEqual((policy, machine, family, protocol), original)
        return actual

    def test_full_two_stage_profile_and_every_replay_field(self):
        actual = self.same(*example())
        self.assertEqual(actual["strata"], {"infinity": 1, "2": 1, "1": 2})

    def test_all_255_nonempty_correlated_subfamilies(self):
        policy, machine = overlap.policy(), overlap.baseline_target()
        for mask in range(1, 256):
            with self.subTest(mask=mask):
                self.same(policy, machine, family=overlap.family(mask))

    def test_only_legal_matching_member_keeps_no_illegal_failure_region(self):
        result = self.same(overlap.policy(), overlap.baseline_target(), family=overlap.family(1))
        self.assertEqual(result["classification"], "all")
        self.assertEqual(result["symbolic"]["first_bad_regions"], 0)

    def test_caller_history_and_disabled_missing_transitions(self):
        p, m = overlap.policy(), overlap.baseline_target()
        caller = {"initial": 0, "transitions": [[None, None, None, 1],
                                                  [None, None, None, 2],
                                                  [None, None, None, 3], [3, 3, 3, None]]}
        result = self.same(p, m, family=overlap.family(255), protocol=caller)
        self.assertEqual(result["strata"], {"infinity": 1, "4": 7})
        for row in result["profiles"][1:]:
            self.assertEqual([step["protocol_state"] for step in row["trace"]], [0, 1, 2, 3])
        for row in m["transitions"]:
            row[3] = None
        caller = {"initial": 0, "transitions": [[0, 0, 0, None]]}
        self.assertEqual(self.same(p, m, protocol=caller)["classification"], "all")

    def test_graph_admission_precedes_early_universal_failure(self):
        p, m = overlap.policy(), overlap.baseline_target()
        m["transitions"][0][0][0] = "deny"
        m["transitions"][3][1] = None
        caller = {"initial": 0, "transitions": [[0, 0, 0, 0]]}
        with patch.object(symbolic, "_mismatch", side_effect=AssertionError("admit first")):
            with self.assertRaises(Rejected) as caught:
                self.run_profile(p, m, protocol=caller)
        self.assertEqual(caught.exception.kind, "inconclusive")
        self.assertEqual(caught.exception.details["indices"], [3, 3, 3, 1])

    def test_initial_mismatch_needs_no_nonempty_event_or_diagram(self):
        p, m = overlap.policy(), overlap.baseline_target()
        m["initial"] = 1
        m["transitions"] = [[None] * 4 for _ in range(4)]
        caller = {"initial": 0, "transitions": [[None] * 4]}
        with patch.object(symbolic, "_reachable_product", side_effect=AssertionError("no traversal")):
            result = self.run_profile(p, m, protocol=caller, operation_limit=0)
        self.assertEqual(result["strata"], {"0": 8})
        self.assertTrue(all(row["trace"] == [] for row in result["profiles"]))

    def test_explicit_family_does_not_enumerate_huge_cartesian_domain(self):
        p, _ = example()
        p["roles"] = ["r", "s"]
        p["members"] = []
        p["aliases"] = [{"name": f"alias-{i:02d}", "kind": "role", "candidates": ["r", "s"]}
                        for i in range(16)]
        p["rules"] = [{"decision": "allow", "guard": [], "updates": []}]
        p = normalize(p)
        m = compile_policy(p)
        family = [{alias["name"]: value for alias in p["aliases"]} for value in ("r", "s")]
        result = self.run_profile(p, m, family=family, family_limit=2)
        self.assertEqual(result["bindings"], 2)
        self.assertEqual(result["classification"], "all")
        with self.assertRaises(Rejected):
            self.run_profile(p, m, family_limit=2)

    def test_three_value_domains_have_no_fourth_binary_value(self):
        p, _ = example()
        p["roles"] = ["r", "s", "t"]
        for alias in p["aliases"]:
            alias["candidates"] = ["r", "s", "t"]
        p = normalize(p)
        m = compile_policy(p)
        family = [{p["aliases"][0]["name"]: a, p["aliases"][1]["name"]: b}
                  for a, b in product(["r", "s", "t"], repeat=2) if a != b]
        self.assertEqual(self.same(p, m)["bindings"], 9)
        self.assertEqual(self.same(p, m, family=family)["bindings"], 6)

    def test_simultaneous_copy_negation_and_first_matching_rule(self):
        p = normalize({"principals": ["u"], "resources": ["o"], "actions": ["flip", "probe"],
                       "roles": ["r", "s"], "members": [["u", "r"]],
                       "state": [["x", False], ["y", True]],
                       "aliases": [{"name": "role", "kind": "role", "candidates": ["r", "s"]}],
                       "rules": [
                           {"decision": "allow", "guard": [{"field": "action", "name": "flip", "negated": False}],
                            "updates": [{"name": "x", "from": "y", "negated": False},
                                        {"name": "y", "from": "x", "negated": True}]},
                           {"decision": "allow", "guard": [{"field": "role", "alias": "role", "negated": False}], "updates": []},
                           {"decision": "deny", "guard": [], "updates": []}]})
        self.same(p, compile_policy(p))

    def test_zero_alias_and_single_candidate_domains(self):
        p, _ = example()
        p["aliases"] = []
        p["rules"] = [{"decision": "allow", "guard": [], "updates": []}]
        p = normalize(p)
        self.same(p, compile_policy(p), family=[{}])
        p, _ = example()
        for alias in p["aliases"]:
            alias["candidates"] = ["r"]
        p = normalize(p)
        self.same(p, compile_policy(p))

    def test_duplicate_order_and_invalid_families(self):
        p, m = example()
        family = list(reversed([row["binding"] for row in binding_profile(p, m)["profiles"]]))
        result = self.same(p, m, family=family + family)
        self.assertEqual([row["binding"] for row in result["profiles"]], family)
        for illegal in ([], [{}], [{**family[0], "foreign": "r"}]):
            with self.assertRaises(Rejected):
                self.run_profile(p, m, family=illegal)
        with self.assertRaises(Rejected) as caught:
            self.run_profile(p, m, family=family + family, family_limit=len(family))
        self.assertEqual(caught.exception.kind, "inconclusive")

    def test_work_and_symbolic_caps_never_return_partial_profiles(self):
        p, m = example()
        actual = self.run_profile(p, m)
        self.assertEqual(semantic(self.run_profile(p, m, budget=actual["work_operations"])), semantic(actual))
        for limits in ({"budget": actual["work_operations"] - 1}, {"operation_limit": 0}, {"node_limit": 2}):
            with self.assertRaises(Rejected) as caught:
                self.run_profile(p, m, **limits)
            self.assertEqual(caught.exception.kind, "inconclusive")
        caller = {"initial": 0, "transitions": [[None] * len(m["alphabet"])]}
        with self.assertRaises(Rejected) as caught:
            self.run_profile(p, m, protocol=caller)
        self.assertEqual(caught.exception.kind, "inconclusive")


class FiniteDiagramFamilyTests(CompleteSymbolicChecks, unittest.TestCase):
    pass


@unittest.skipUnless(has_cudd(), "install requirements-symbolic.txt for the compiled CUDD backend")
class CuddFamilyTests(CompleteSymbolicChecks, unittest.TestCase):
    backend = "cudd"


if __name__ == "__main__":
    unittest.main()
