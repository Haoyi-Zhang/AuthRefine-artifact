"""Portable native-audit checker regressions; these tests do not run Django."""
from copy import deepcopy
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import audit_credential_admission as audit


class CredentialAdmissionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = audit.source_check()
        cls.baseline = audit.source_read(audit.SOURCE_ROOT / "data/credential-observations.json")

    def controlled_record(self, mode):
        row = deepcopy(self.baseline["rows"][0])
        row["serializer_transfers"][0]["readonly" if mode == "readonly_integer" else "v"] = 0 if mode == "readonly_integer" else True
        row["IR_steps"] -= 1
        return {"rows": [row], "producer_records": [],
                "totals": {"contexts": 1, "actual_SELECTs": 2, "native_mac_calls": 0,
                           "exact_project_identity_transfers": 1, "serializer_transfers": 1, "differences": 0, "status_200": 1},
                "original_application_modules_or_tests_executed": False,
                "original_serializer_or_write_action_executed": False,
                "original_deployment_or_randomness_security_certified": False}

    def test_complete_retained_baseline_and_two_precise_controls(self):
        self.assertTrue(audit.evaluate("baseline_full", self.baseline, self.packet)["new_evidence_gate_admitted"])
        for mode in audit.MODES[1:]:
            with self.subTest(mode=mode):
                result = audit.evaluate(mode, self.controlled_record(mode), self.packet)
                self.assertIs(result["new_evidence_gate_admitted"], False)
                self.assertIs(result["original_frozen_collector_reported_agreement"], True)
                self.assertIn("serializer readonly/version/record transfer", result["rejection"])

    def test_control_rejection_cannot_hide_an_unrelated_bad_record(self):
        for mode in audit.MODES[1:]:
            for control in ("extra_sql", "wrong_steps", "non_boolean_agreement", "missing_row"):
                with self.subTest(mode=mode, control=control):
                    result = self.controlled_record(mode)
                    if control == "extra_sql":
                        result["rows"][0]["sql"].append(deepcopy(result["rows"][0]["sql"][0]))
                        result["totals"]["actual_SELECTs"] += 1
                    elif control == "wrong_steps":
                        result["rows"][0]["IR_steps"] += 1
                    elif control == "non_boolean_agreement":
                        result["rows"][0]["agrees"] = 1
                    else:
                        result["rows"] = []
                    with self.assertRaisesRegex(ValueError, "beyond the declared serializer fault"):
                        audit.evaluate(mode, result, self.packet)

    def test_private_control_construction_does_not_mutate_frozen_input(self):
        before = deepcopy(self.packet)
        for mode in audit.MODES:
            binding, cases, changes = audit.prepared_input(self.packet, mode)
            self.assertIsNot(binding, self.packet["binding"])
            self.assertEqual(len(changes), int(mode != "baseline_full"))
            self.assertEqual(len(cases), 1260 if mode == "baseline_full" else 1)
        self.assertTrue(audit.typed_equal(before, self.packet))

    def test_existing_output_is_rejected_before_native_process_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(audit.subprocess, "run", side_effect=AssertionError("existing output reached native process")):
                with self.assertRaises(FileExistsError):
                    audit.run("all", directory)

    def test_ambiguous_json_and_boolean_runtime_counter_are_rejected(self):
        with self.assertRaises(ValueError):
            audit.decode('{"mode":"baseline_full","mode":"version_boolean"}')
        runtime = {"python": "CPython", "implementation": "CPython", "Django": "6.1.2", "SQLite": "3",
                   "started_utc": "2026-01-01T00:00:00+00:00", "finished_utc": "2026-01-01T00:00:01+00:00",
                   "elapsed_seconds": True}
        with self.assertRaisesRegex(ValueError, "invalid recorded elapsed time"):
            audit.validate_runtime(runtime)


if __name__ == "__main__":
    unittest.main()
