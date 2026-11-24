"""Controls for the independent multi-alias support-index audit."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("support_overlap_audit", ROOT / "proofs/audit_support_overlap.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class OverlappingSupportAuditTests(unittest.TestCase):
    def test_domain_contains_all_single_cell_changes_and_nonempty_subfamilies(self):
        targets = list(audit.targets())
        self.assertEqual(len(targets), 65)
        self.assertEqual(len({audit.encoded(row["machine"]) for row in targets}), 65)
        base = audit.baseline_target()["transitions"]
        for target in targets[1:]:
            changed = [(q, i) for q in range(4) for i in range(4)
                       if base[q][i] != target["machine"]["transitions"][q][i]]
            self.assertEqual(len(changed), 1)
        families = [audit.family(mask) for mask in range(1, 256)]
        self.assertEqual(len({audit.encoded(f) for f in families}), 255)
        self.assertEqual(sum(map(len, families)), 1024)

    def test_separate_source_table_matches_every_encoded_contract_cell(self):
        p = audit.policy()
        for binding in audit.BINDINGS:
            for state in range(4):
                for action in audit.ACTIONS:
                    self.assertEqual(audit.implementation.reference_step(p, state, ["u", "o", action], binding),
                                     audit.source_cell(state, action, binding))

    def test_all_indexes_exist_before_delayed_retirement_and_correlated_family_stays_exact(self):
        p, m = audit.policy(), audit.baseline_target()
        result = audit.implementation.support_indexed_profile(p, m)
        audit.check_report(result, audit.expected_family(m, 255))
        self.assertEqual(result["strata"], {"infinity": 1, "2": 6, "3": 1})
        self.assertEqual((result["cached_supports"], result["index_memberships_created"],
                          result["index_memberships_removed"]), (4, 32, 28))
        correlated = audit.implementation.support_indexed_profile(p, m, audit.family(129))
        audit.check_report(correlated, audit.expected_family(m, 129))
        self.assertEqual(correlated["bindings"], 2)
        self.assertEqual(correlated["matching_bindings"], 1)

    def test_independent_comparison_rejects_executed_semantic_and_family_mutations(self):
        results = audit.mutation_controls()
        self.assertEqual(len(results), 3)
        self.assertTrue(all(row["detected"] and row["detection_stage"] == "independent-comparison" for row in results))
        self.assertEqual(results[0]["actual_matching"], 8)
        self.assertEqual(results[2]["actual_bindings"], 8)
        self.assertEqual(results[2]["expected_bindings"], 2)

    def test_replay_corruption_is_rejected_even_with_correct_verdict_and_word(self):
        m = audit.baseline_target()
        report = audit.implementation.support_indexed_profile(audit.policy(), m)
        changed = copy.deepcopy(report)
        row = next(row for row in changed["profiles"] if not row["equivalent"])
        row["trace"][0]["binding"] = {**row["trace"][0]["binding"], "x": "s"}
        with self.assertRaises(AssertionError):
            audit.check_report(changed, audit.expected_family(m, 255))


if __name__ == "__main__":
    unittest.main()
