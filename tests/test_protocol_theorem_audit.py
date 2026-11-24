"""Independent word-oracle controls for the mechanized caller-protocol bound."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ARTIFACT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT / "src"))
_SPEC = importlib.util.spec_from_file_location("authrefine_protocol_audit", ARTIFACT / "proofs/protocol_audit.py")
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


class ProtocolTheoremAuditTests(unittest.TestCase):
    def test_declared_small_domain_contains_every_table_once(self):
        for generator, expected in ((audit.reference_tables, 81), (audit.candidate_tables, 256),
                                    (audit.caller_tables, 81)):
            tables = list(generator())
            self.assertEqual(len(tables), expected)
            self.assertEqual(len(set(tables)), expected)
        self.assertTrue(all(decision != "deny" or successor == index // 2
                            for table in audit.reference_tables()
                            for index, (decision, successor) in enumerate(table)))

    def test_oracle_keeps_protocol_history_for_a_repeated_target_state(self):
        reference = (("allow", 0), ("deny", 0), ("allow", 1), ("deny", 1))
        candidate = (("allow", 0),) * 4
        protocol = (1, None, None, 1)
        result = audit.compare_case(reference, candidate, protocol)
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["length"], 2)
        self.assertEqual(result["nodes"], 2)
        self.assertEqual(result["word"], (0, 1))
        self.assertEqual({target for target, _ in audit.reachable_product_nodes(candidate, protocol)}, {0})

    def test_oracle_detects_an_erroneous_shared_reference_evaluator(self):
        reference = (("deny", 0), ("deny", 0), ("deny", 1), ("deny", 1))
        candidate = (("allow", 0),) * 4
        protocol = (0, None, None, None)
        self.assertEqual(audit.compare_case(reference, candidate, protocol)["status"], "mismatch")
        # This deliberately makes the implementation say "equivalent". The
        # word oracle still reads the supplied independent reference table.
        with patch("protocol_check.reference_step", return_value=("allow", 0)):
            with self.assertRaises(AssertionError):
                audit.compare_case(reference, candidate, protocol)

    def test_oracle_checks_complete_state_observation_even_when_decisions_match(self):
        reference = (("allow", 1), ("deny", 0), ("allow", 0), ("deny", 1))
        candidate = (("allow", 0), ("deny", 0), ("allow", 1), ("deny", 1))
        result = audit.compare_case(reference, candidate, (0, None, None, None))
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["length"], 1)
        rows = audit.replay_word(reference, candidate, (0, None, None, None), result["word"])
        self.assertEqual(rows[-1][2][0], rows[-1][3][0])
        self.assertNotEqual(rows[-1][2][1], rows[-1][3][1])

    def test_no_enabled_event_keeps_the_implementation_inconclusive(self):
        reference = (("deny", 0), ("deny", 0), ("deny", 1), ("deny", 1))
        candidate = reference
        self.assertEqual(audit.compare_case(reference, candidate, (None,) * 4)["status"], "inconclusive")
        self.assertEqual(audit.compare_case(reference, candidate, (0, None, None, None))["status"], "equivalent")

    def test_witness_rows_are_checked_separately_from_the_claimed_length(self):
        reference = (("deny", 0), ("deny", 0), ("deny", 1), ("deny", 1))
        candidate = (("allow", 0),) * 4
        protocol = (0, None, None, None)
        wrong = {"status": "mismatch", "length": 1,
                 "trace": [{"request": audit.ALPHABET[0], "protocol_state": 1,
                            "source": ["deny", 0], "target": ["allow", 0]}]}
        with patch.object(audit, "verify_protocol", return_value=wrong):
            with self.assertRaises(AssertionError):
                audit.compare_case(reference, candidate, protocol)


if __name__ == "__main__":
    unittest.main()
