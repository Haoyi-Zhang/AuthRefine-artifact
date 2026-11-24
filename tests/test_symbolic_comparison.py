"""Negative controls for the retained six-method comparison evidence.

The tiny record fixtures below exercise rejection paths. They are never used
as measurements and are never written to the research results directory.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from benchmarks.symbolic_comparison import COUNTERS, METHODS, digest, encoded, methods, summarize
from checker import Rejected


def records_fixture():
    profile = [{"binding": {"slot": "row"}, "equivalent": False,
                "length": 1, "indices": [0],
                "trace": [{"compared_equal": False, "request": ["p", "r", "a"]}]}]
    cohort = [{"id": "total", "case": "case", "cohort": "unit", "group": "unit",
               "regime": "unit", "caller": "total", "protocol": None, "expected": profile},
              {"id": "caller", "case": "case", "cohort": "unit", "group": "unit",
               "regime": "unit", "caller": "unrestricted", "protocol": {}, "expected": profile}]
    trials = []
    for repeat in range(3):
        for method in METHODS:
            rows = []
            for task in cohort:
                if method not in methods(task):
                    continue
                row = {key: 0 for key in COUNTERS}
                row.update(id=task["id"], output_sha256=digest(profile),
                           output_bytes=len(encoded(profile)), bindings=1, matching=0,
                           failure_lengths=[1], diagnosis_wall_ns=repeat + 1,
                           diagnosis_cpu_ns=repeat + 1, serialization_ns=repeat + 1)
                rows.append(row)
            trials.append({"repeat": repeat, "method": method, "records": rows,
                           "exit_code": 0, "complete_outputs_compared": True})
    return cohort, trials


class ComparisonEvidenceTests(unittest.TestCase):
    def test_exact_method_caller_denominator(self):
        cohort, trials = records_fixture()
        summary = summarize(cohort, trials, 3)
        self.assertEqual((summary["tasks"], summary["case_method_pairs"],
                          summary["processes"], summary["timed_task_records"]), (2, 10, 18, 30))
        missing = deepcopy(trials)
        missing[2]["records"].pop()
        with self.assertRaisesRegex(Rejected, "denominator"):
            summarize(cohort, missing, 3)

    def test_same_lengths_do_not_allow_an_altered_replay(self):
        cohort, trials = records_fixture()
        altered = deepcopy(cohort[0]["expected"])
        altered[0]["trace"][0]["request"] = ["p", "r", "b"]
        trials[0]["records"][0]["output_sha256"] = digest(altered)
        with self.assertRaisesRegex(Rejected, "output identity"):
            summarize(cohort, trials, 3)

    def test_repeated_process_cannot_replace_a_missing_method(self):
        cohort, trials = records_fixture()
        trials[-1] = deepcopy(trials[0])
        with self.assertRaisesRegex(Rejected, "unique valid"):
            summarize(cohort, trials, 3)

    def test_failed_or_unchecked_worker_is_not_measurement_evidence(self):
        for key, value in (("exit_code", 1), ("complete_outputs_compared", False)):
            cohort, trials = records_fixture()
            trials[0][key] = value
            with self.assertRaisesRegex(Rejected, "successful complete-output"):
                summarize(cohort, trials, 3)

    def test_counter_corruption_and_boolean_timings_are_rejected(self):
        for key, value in (("replay_steps", -1), ("diagnosis_wall_ns", True)):
            cohort, trials = records_fixture()
            trials[0]["records"][0][key] = value
            with self.assertRaisesRegex(Rejected, "nonnegative integer"):
                summarize(cohort, trials, 3)
        cohort, trials = records_fixture()
        trials[0]["records"][0]["replay_steps"] = 1
        with self.assertRaisesRegex(Rejected, "stable scientific work"):
            summarize(cohort, trials, 3)

    def test_family_and_failure_strata_are_checked_independently(self):
        for key, value, message in (("matching", 1, "family denominator"),
                                    ("failure_lengths", [2], "failure strata")):
            cohort, trials = records_fixture()
            trials[0]["records"][0][key] = value
            with self.assertRaisesRegex(Rejected, message):
                summarize(cohort, trials, 3)


if __name__ == "__main__":
    unittest.main()
