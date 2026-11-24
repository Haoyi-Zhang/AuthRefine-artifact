"""Checks the native H19 evidence boundary, including deliberately bad records."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ARTIFACT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT))
from source_study.historical_h19.source import SOURCE, check_source, load_original
from source_study.historical_h19.verify import verify, verify_directory
from source_study.historical_h19.matrix import compare_versions

MATRIX = ARTIFACT / "results/published-patch"
RESULT = MATRIX / "orm-1.16.0"


class HistoricalH19Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = json.loads((RESULT / "fixtures.json").read_text())
        cls.observations = json.loads((RESULT / "native-observations.json").read_text())
        cls.comparison = json.loads((RESULT / "comparison.json").read_text())

    def test_complete_native_result_retains_errors_and_values(self):
        result = verify_directory(RESULT)
        self.assertEqual((result["metadata_pairs"], result["metadata_disagreements"]), (90, 0))
        self.assertEqual((result["selection_endpoint_returns"], result["selection_endpoint_exceptions"]), (84, 6))
        patch = result["default_patch_comparison"]
        self.assertFalse(patch["status_only_distinguishes"])
        self.assertFalse(patch["json_field_names_distinguish"])
        self.assertTrue(patch["stored_token_values_distinguish"])

    def test_changed_output_value_is_not_hidden_by_status(self):
        records = copy.deepcopy(self.observations)
        row = next(r for r in records["selection_observations"] if r["profile"] == "producer-after__consumer-after" and r["context"] == "selection-0-override-0")
        row["endpoint"]["json"]["rows"][0]["token"] = self.fixtures["rows"][0]["token"]
        row["endpoint"]["body"] = json.dumps(row["endpoint"]["json"])
        row["endpoint"]["owned_token_value_exposed"] = True
        with self.assertRaisesRegex(ValueError, "JSON row values"):
            verify(self.fixtures, records, self.comparison)

    def test_exception_cannot_be_recoded_as_success(self):
        records = copy.deepcopy(self.observations)
        row = next(r for r in records["selection_observations"] if r["endpoint"]["outcome"] == "exception")
        row["endpoint"]["outcome"] = "return"
        with self.assertRaisesRegex(ValueError, "SQL error"):
            verify(self.fixtures, records, self.comparison)

    def test_filter_repair_requires_actual_rejection(self):
        records = copy.deepcopy(self.observations)
        row = next(r for r in records["filter_observations"] if r["profile"].endswith("owned-repair") and r["context"] == "matching-token")
        row["endpoint"]["status"] = 200
        with self.assertRaisesRegex(ValueError, "Filter admission"):
            verify(self.fixtures, records, self.comparison)

    def test_duplicate_context_does_not_inflate_coverage(self):
        records = copy.deepcopy(self.observations)
        records["selection_observations"][-1] = copy.deepcopy(records["selection_observations"][0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            verify(self.fixtures, records, self.comparison)

    def test_native_registry_is_not_replaced_with_ideal_metadata(self):
        records = copy.deepcopy(self.observations)
        row = next(r for r in records["selection_observations"] if r["profile"] == "producer-after__consumer-after")
        row["registry_fields"] = ["token"]
        with self.assertRaisesRegex(ValueError, "subclass registry"):
            verify(self.fixtures, records, self.comparison)

    def test_changed_source_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            for label in ("before", "after"):
                for part in ("piccolo_api/session_auth/tables.py", "piccolo_api/crud/endpoints.py"):
                    destination = target / label / part
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(SOURCE / label / part, destination)
            changed = target / "after/piccolo_api/session_auth/tables.py"
            changed.write_bytes(changed.read_bytes() + b"\n# changed source\n")
            with self.assertRaisesRegex(ValueError, "Pinned H19 source changed"):
                check_source(target)

    def test_arbitrary_source_label_is_not_executed(self):
        with self.assertRaisesRegex(ValueError, "two pinned"):
            load_original("outside", "table", "invalid")

    def test_native_dependency_version_explains_filter_difference(self):
        result = compare_versions(MATRIX)
        self.assertEqual(result["different_installed_packages"], ["piccolo"])
        self.assertEqual(result["metadata_pairs"], 180)
        self.assertEqual(result["change_counts"]["filter_endpoint"], 2)
        self.assertEqual(result["change_counts"]["selection_endpoint"], 0)

    def test_version_relabel_cannot_hide_missing_registry_entry(self):
        records = copy.deepcopy(self.observations)
        records["orm_version"] = "1.34.0"
        with self.assertRaisesRegex(ValueError, "Registry source binding"):
            verify(self.fixtures, records, self.comparison)

    def test_raw_sql_cannot_disagree_with_serialized_output(self):
        records = copy.deepcopy(self.observations)
        row = next(r for r in records["selection_observations"] if r["profile"] == "producer-after__consumer-after" and r["context"] == "selection-0-override-0")
        row["endpoint"]["sql_calls"][0]["rows"][0]["user_id"] = 999
        with self.assertRaisesRegex(ValueError, "Raw SQL readback"):
            verify(self.fixtures, records, self.comparison)


if __name__ == "__main__":
    unittest.main()
