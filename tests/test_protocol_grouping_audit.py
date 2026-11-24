"""Controls for the independent caller/grouping audit, separate from engine tests."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("grouping_audit_control", ROOT / "proofs/audit_protocol_grouping.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class GroupingOracleTests(unittest.TestCase):
    def test_domain_contains_complete_changes_and_each_missing_cell(self):
        targets = list(audit.targets())
        self.assertEqual(len(targets), 81)
        self.assertEqual(len({audit.overlap.encoded(row["machine"]) for row in targets}), 81)
        self.assertEqual(sum(row["id"].startswith("missing-") for row in targets), 16)
        self.assertEqual(len(audit.callers()), 6)

    def test_every_executed_fault_is_detected(self):
        rows = audit.controls()
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["detected"] for row in rows))

    def test_corrupted_caller_state_or_fixed_binding_cannot_keep_correct_word(self):
        policy, machine = audit.overlap.policy(), audit.overlap.baseline_target()
        protocol = audit.callers()["three_ticks_then_probes"]
        result = audit.implementation.support_indexed_protocol_profile(policy, machine, protocol)
        expected = [audit.oracle_profile(machine, protocol, binding) for binding in audit.overlap.BINDINGS]
        audit.check_report(result, expected)
        for field, value in (("protocol_state", 99), ("binding", {"x": "s", "y": "s", "z": "s"})):
            changed = copy.deepcopy(result)
            row = next(row for row in changed["profiles"] if not row["equivalent"])
            row["trace"][0][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                audit.check_report(changed, expected)


if __name__ == "__main__":
    unittest.main()
