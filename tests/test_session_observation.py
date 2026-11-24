"""Full identity observations, declared native words and family prerequisites.

The record-bearing fixtures below are retained native SQLite executions. The
negative controls deliberately corrupt one field or one declared request word.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from source_study.session_correspondence import fixtures, oracle, verify_observation
from source_study.session_correspondence.observation_contract import (
    check_record, credential_arguments, native_replay_rows, propose_bijections,
    selected_map)


ART = Path(__file__).resolve().parents[1]
OLD = ART / "results/session-correspondence"
RESULTS = ART / "results/session-observation"


class SessionObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.native = verify_observation.source_cases(OLD)
        cls.case = next(row for row in cls.cases if row["id"] == "sessions-2-baseline")
        cls.graph = cls.native[2]["baseline"]
        cls.cells = {(row["from_state"], row["input_index"]): row["observation"]
                     for row in cls.graph["edges"]}

    def test_selected_identity_is_present_in_complete_witness(self):
        case = self.case
        binding = case["family"][1]
        caller = case["callers"]["lookup-only"]
        rich = oracle.profile(2, case["machine"], binding, caller, selected_map(self.graph))
        self.assertFalse(rich["equivalent"])
        self.assertEqual((rich["length"], rich["indices"]), (1, [0]))
        row = rich["trace"][0]
        self.assertEqual(row["source"], row["target"])
        self.assertTrue(row["decision_equal"])
        self.assertTrue(row["state_equal"])
        self.assertEqual((row["observed_selected_row"], row["reference_selected_row"]), (1, 2))
        self.assertFalse(row["identity_equal"])
        self.assertFalse(row["compared_equal"])
        observed = [self.cells[3, 0]]
        self.assertEqual(rich["trace"], native_replay_rows(case, binding, "lookup-only", [0], observed))
        self.assertEqual(oracle.check_native_witness(2, binding, [0], observed, selected_identity=True), 1)

    def test_ordinary_complete_profile_shape_and_results_are_unchanged(self):
        for case in (row for row in self.cases if row["sessions"] == 2):
            for method, retained in case["expected"].items():
                caller = case["callers"][method.split("/")[1]] if "/" in method else None
                with self.subTest(case=case["id"], method=method):
                    actual = [oracle.profile(2, case["machine"], binding, caller) for binding in case["family"]]
                    self.assertEqual(actual, retained)
                    for row in actual:
                        for step in row["trace"] or []:
                            self.assertNotIn("identity_equal", step)
                            self.assertNotIn("observed_selected_row", step)

    def test_native_witness_must_follow_the_declared_request_word(self):
        binding = self.case["family"][1]
        observed = [self.cells[3, 9], self.cells[1, 2]]
        self.assertEqual(oracle.check_native_witness(2, binding, [9, 2], observed), 2)
        with self.assertRaisesRegex(ValueError, "declared word"):
            oracle.check_native_witness(2, binding, [7, 0], observed)

    def test_native_witness_rejects_broken_state_continuity(self):
        observed = deepcopy([self.cells[3, 9], self.cells[1, 2]])
        observed[1]["before_state"] = 3
        with self.assertRaisesRegex(ValueError, "continuity"):
            oracle.check_native_witness(2, self.case["family"][1], [9, 2], observed)

    def test_identity_mode_requires_actual_selected_record(self):
        observed = deepcopy(self.cells[3, 0])
        del observed["selected_record"]
        with self.assertRaisesRegex(ValueError, "selected-record observation"):
            oracle.check_native_witness(2, self.case["family"][1], [0], [observed], selected_identity=True)

    def test_selected_record_is_bound_to_the_stored_token_row(self):
        observed = deepcopy(self.cells[3, 0])
        observed["selected_record"]["id"] = 2
        with self.assertRaisesRegex(ValueError, "stored token row"):
            check_record(2, observed)

    def test_one_request_identity_word_is_not_a_decision_state_witness(self):
        with self.assertRaisesRegex(ValueError, "first disagree"):
            oracle.check_native_witness(2, self.case["family"][1], [0], [self.cells[3, 0]])

    def test_record_prerequisites_and_physical_mapping_are_distinct(self):
        rows = self.cells[3, 0]["before_rows"]
        proposed = propose_bijections(rows, credential_arguments(2))
        self.assertEqual(proposed["status"], "supported-bijection-shape")
        self.assertEqual(proposed["family"], self.case["family"])
        self.assertEqual(proposed["recorded_mapping"], self.case["family"][0])
        changed = deepcopy(rows)
        changed[1]["token"] = changed[0]["token"]
        unsupported = propose_bijections(changed, credential_arguments(2))
        self.assertEqual(unsupported["status"], "unsupported-bijection-shape")
        self.assertIn("row-token-values-not-unique", unsupported["issues"])
        self.assertIsNone(unsupported["family"])
        self.assertIsNone(unsupported["recorded_mapping"])
        self.assertTrue(unsupported["explicit_family_may_still_be_diagnosed"])

    def test_duplicate_token_input_is_stored_and_diagnosed_natively(self):
        raw = verify_observation.read(RESULTS / "duplicate-native.json.gz")
        diagnosis = verify_observation.read(RESULTS / "duplicate-diagnosis.json")
        self.assertFalse(raw["schema"]["token_unique"])
        self.assertFalse(raw["source_modified"])
        self.assertEqual([row["token"] for row in raw["initial_rows"]],
                         [raw["initial_rows"][0]["token"]] * 2)
        self.assertEqual(len(raw["graph"]["states"]), 2)
        self.assertEqual(len(raw["graph"]["edges"]), 20)
        deletion = next(edge["observation"] for edge in raw["graph"]["edges"]
                        if edge["from_state"] == 3 and edge["observation"]["request"] == ["client", "row-1", "remove"])
        self.assertEqual(deletion["removed_ids"], [1, 2])
        self.assertEqual(deletion["after_state"], 0)
        self.assertEqual(len(diagnosis["profiles"]), 10)
        self.assertTrue(all(len(rows) == 2 and all(not row["equivalent"] and row["length"] == 1 for row in rows)
                            for rows in diagnosis["profiles"].values()))


class SessionObservationRecordTests(unittest.TestCase):
    def reject_changed_record(self, filename, change, message):
        original = verify_observation.read
        def altered(path):
            value = original(path)
            if path.name == filename:
                value = deepcopy(value)
                change(value)
            return value
        with patch.object(verify_observation, "read", side_effect=altered):
            with self.assertRaisesRegex(ValueError, message):
                verify_observation.verify(RESULTS, OLD)

    def test_retained_identity_flags_cannot_hide_the_disagreement(self):
        for field in ("reference_selected_row", "observed_selected_row", "identity_equal", "compared_equal"):
            def change(values, field=field):
                row = next(row for row in values[0]["callers"]["lookup-only"] if not row["equivalent"])
                row["trace"][0][field] = True if field.endswith("equal") else 999
            with self.subTest(field=field):
                self.reject_changed_record("identity-profiles.json.gz", change, "complete identity profile")

    def test_recorded_native_selection_cannot_be_relabelled(self):
        def change(values):
            values[0]["words"][0]["observations"][0]["selected_record"]["id"] = 2
        self.reject_changed_record("native-witnesses.json.gz", change, "fresh identity execution")

    def test_native_word_indices_cannot_be_substituted(self):
        def change(values):
            values[0]["words"][0]["indices"] = [2]
        self.reject_changed_record("native-witnesses.json.gz", change, "physical identity words")

    def test_complete_observation_study_reconciles(self):
        summary = verify_observation.verify(RESULTS, OLD)
        self.assertEqual((summary["binding_rows"], summary["matching_binding_rows"], summary["excluded_binding_rows"]),
                         (5232, 20, 5212))
        self.assertEqual((summary["distinct_native_word_runs"], summary["native_identity_operations"]), (35, 35))
        self.assertEqual(summary["duplicate_token"]["explicit_contract_classification"], "none")


if __name__ == "__main__":
    unittest.main()
