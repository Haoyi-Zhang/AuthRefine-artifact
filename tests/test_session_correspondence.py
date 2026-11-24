"""Correlated multi-session families, source records and independent diagnosis."""
import asyncio
from copy import deepcopy
import importlib.metadata
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from source_study.session_correspondence import fixtures, oracle
from source_study.session_correspondence.run import check_native_cells, semantic_rows


def equation_machine(size, target_binding=None):
    """A unit-test table; the experiment obtains its tables from native SQLite."""
    target_binding = target_binding or fixtures.family(size)[0]
    requests = fixtures.alphabet(size)
    return {"state_names": [name for name, _ in fixtures.contract(size)["state"]],
            "alphabet": requests, "observations": list(range(1 << size)),
            "initial": (1 << size) - 1,
            "transitions": [[list(oracle.step(size, state, request, target_binding))
                             for request in requests] for state in range(1 << size)]}


class SessionCorrespondenceTests(unittest.TestCase):
    def test_supplied_family_preserves_bijections(self):
        for size in range(2, 7):
            family = fixtures.family(size)
            self.assertEqual(len(family), math.factorial(size))
            self.assertLess(len(family), size ** size)
            self.assertEqual(len({tuple(row.items()) for row in family}), len(family))
            self.assertTrue(all(set(binding.values()) == set(fixtures.credentials(size)) for binding in family))

    def test_alphabet_and_policy_remain_canonical(self):
        from checker import inspect_machine, inspect_policy
        for size in range(2, 7):
            policy = fixtures.contract(size)
            inspect_policy(policy)
            inspect_machine(policy, equation_machine(size))
            self.assertEqual(len(fixtures.alphabet(size)), 2 * (2 * size + 1))

    def test_fixed_correspondence_requires_removal_then_lookup(self):
        machine = equation_machine(3)
        family = fixtures.family(3)
        profiles = [oracle.profile(3, machine, binding) for binding in family]
        self.assertEqual(sum(row["equivalent"] for row in profiles), 1)
        for row in profiles[1:]:
            self.assertEqual(row["length"], 2)
            self.assertEqual(machine["alphabet"][row["indices"][0]][2], "remove")
            self.assertEqual(machine["alphabet"][row["indices"][1]][2], "lookup")
            self.assertTrue(row["trace"][0]["compared_equal"])
            self.assertFalse(row["trace"][1]["compared_equal"])

    def test_lookup_only_retains_every_bijection(self):
        machine = equation_machine(3)
        caller = fixtures.callers(machine["alphabet"])["lookup-only"]
        self.assertTrue(all(oracle.profile(3, machine, binding, caller)["equivalent"]
                            for binding in fixtures.family(3)))

    def test_one_removal_retains_exactly_the_target_correspondence(self):
        family = fixtures.family(3)
        for target_binding in family:
            machine = equation_machine(3, target_binding)
            caller = fixtures.callers(machine["alphabet"])["one-removal"]
            survivors = [binding for binding in family if oracle.profile(3, machine, binding, caller)["equivalent"]]
            self.assertEqual(survivors, [target_binding])

    def test_identity_observation_changes_the_shortest_question(self):
        machine = equation_machine(3)
        identity = fixtures.family(3)[0]
        selected = {(state, index): oracle.selected_row(3, state, request, identity)
                    for state in machine["observations"] for index, request in enumerate(machine["alphabet"])}
        caller = fixtures.callers(machine["alphabet"])["lookup-only"]
        rows = [oracle.profile(3, machine, binding, caller, selected) for binding in fixtures.family(3)]
        self.assertEqual(sum(row["equivalent"] for row in rows), 1)
        self.assertEqual({row["length"] for row in rows if not row["equivalent"]}, {1})

    def test_oracle_detects_forged_replay_binding(self):
        machine = equation_machine(3)
        wrong = oracle.profile(3, machine, fixtures.family(3)[1])
        observations = [{"request": row["request"], "decision": row["target"][0],
                         "after_state": row["target"][1]} for row in wrong["trace"]]
        oracle.check_native_witness(3, wrong["binding"], wrong["indices"], observations)
        with self.assertRaisesRegex(ValueError, "first disagree"):
            oracle.check_native_witness(3, fixtures.family(3)[0], wrong["indices"], observations)


class SessionRecordValidationTests(unittest.TestCase):
    """Real record corruptions must fail the read-only publication-table gate."""
    results = Path(__file__).resolve().parents[1] / "results/session-correspondence"

    def reject_changed_record(self, filename, change, message):
        from source_study.session_correspondence import summarize
        original = summarize.read
        def altered(path):
            value = original(path)
            if path.name == filename:
                value = deepcopy(value)
                change(value)
            return value
        with patch.object(summarize, "read", side_effect=altered):
            with self.assertRaisesRegex(ValueError, message):
                summarize.verify(self.results)

    def test_source_selected_token_corruption_is_rejected(self):
        def change(values):
            edge = next(row for row in values[0]["baseline"]["edges"]
                        if row["observation"]["selected_record"] is not None)
            edge["observation"]["selected_record"]["token"] = "wrong-record-token"
        self.reject_changed_record("native-observations.json.gz", change, "rich record")

    def test_missing_native_prefix_record_is_rejected(self):
        def change(values):
            edge = next(row for row in values[0]["baseline"]["edges"] if row["prefix"])
            edge["prefix_observations"].clear()
        self.reject_changed_record("native-observations.json.gz", change, "record count")

    def test_changed_timing_summary_is_rejected(self):
        def change(value):
            value["cases"][0]["methods"]["per-binding-product"]["diagnosis_wall_ns"]["median"] += 1
        self.reject_changed_record("timing.json", change, "timing summary")

    def test_changed_supplied_family_is_rejected(self):
        def change(values):
            values[0]["family"].append(dict(values[0]["family"][0]))
        self.reject_changed_record("inputs.json.gz", change, "supplied family")

    def test_changed_identity_witness_length_is_rejected(self):
        def change(values):
            row = next(row for row in values[0]["selected_identity_profiles"]["lookup-only"] if not row["equivalent"])
            row["length"] += 1
        self.reject_changed_record("profiles.json.gz", change, "selected-identity profile")


def has_native_dependency():
    try:
        return importlib.metadata.version("piccolo") == "1.16.0"
    except importlib.metadata.PackageNotFoundError:
        return False


@unittest.skipUnless(has_native_dependency(), "install the supplied native session dependencies")
class NativeSessionCorrespondenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from source_study.session_correspondence.native import acquire
        cls.native = asyncio.run(acquire(3))

    def test_native_correspondence_and_grouped_caller_profile(self):
        from protocol_grouped import support_indexed_protocol_profile
        for arm in ("baseline", "omit-delete"):
            graph = self.native[arm]
            check_native_cells(3, graph, arm == "omit-delete")
            for caller in fixtures.callers(graph["machine"]["alphabet"]).values():
                expected = [oracle.profile(3, graph["machine"], binding, caller)
                            for binding in fixtures.family(3)]
                observed = support_indexed_protocol_profile(fixtures.contract(3), graph["machine"], caller,
                                                            family=fixtures.family(3))
                self.assertEqual(semantic_rows(observed), expected)

    def test_rich_record_and_prefix_corruption_are_detected(self):
        graph = deepcopy(self.native["baseline"])
        selected = next(edge for edge in graph["edges"] if edge["observation"]["selected_record"] is not None)
        selected["observation"]["selected_record"]["token"] = "wrong-token"
        with self.assertRaisesRegex(ValueError, "rich record"):
            check_native_cells(3, graph, False)
        graph = deepcopy(self.native["baseline"])
        edge = next(edge for edge in graph["edges"] if edge["prefix"])
        edge["prefix_observations"].clear()
        with self.assertRaisesRegex(ValueError, "record count"):
            check_native_cells(3, graph, False)


if __name__ == "__main__":
    unittest.main()
