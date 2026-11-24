"""Admission regressions using the retained complete-output comparison.

Malformed copies below test the evidence reader. They are not measurements and
never change a file in the retained comparison or its scientific origins.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import audit_symbolic_comparison as audit

RESULTS = ROOT / "results/symbolic-comparison"
SCRIPT = ROOT / "benchmarks/audit_symbolic_comparison.py"


class CompleteComparisonEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = audit.load_evidence(RESULTS)

    def test_entire_retained_campaign_is_admitted(self):
        report = self.evidence["summary"]
        self.assertEqual((report["tasks"], report["case_method_pairs"], report["repeats"],
                          report["processes"], report["timed_task_records"],
                          report["complete_binding_profiles"]), (158, 760, 7, 42, 5320, 10529))
        self.assertIs(report["bytes_and_modification_times_unchanged"], True)
        self.assertEqual(report["campaign_files"], 89)
        self.assertIs(report["scope"]["executed_diagnosis_or_backend"], False)

    def test_controls_cover_raw_completeness_types_grid_and_provenance(self):
        result = audit.controls(self.evidence)
        names = {row["name"] for row in result["records"]}
        self.assertTrue({"empty raw worker object", "Boolean process return code",
                         "missing timed task", "duplicate method process",
                         "missing CUDD package metadata", "missing historical source identity",
                         "Boolean zero in derived summary", "unaltered full campaign"} <= names)
        self.assertEqual(result["rejection_controls"], 42)
        self.assertEqual(result["positive_controls"], 3)
        self.assertEqual(result["scientific_measurements_added"], 0)

    def test_boolean_numeric_values_remain_distinct_at_every_depth(self):
        for left, right in ((False, 0), (True, 1), (1, 1.0),
                            ({"row": [True]}, {"row": [1]})):
            with self.subTest(left=left, right=right):
                self.assertFalse(audit.same(left, right))
        self.assertTrue(audit.same({"a": 1, "b": False}, {"b": False, "a": 1}))

    def test_json_decoder_rejects_duplicate_keys_and_nonfinite_numbers(self):
        for raw in (b'{"exit_code":1,"exit_code":0}', b'{"time":NaN}',
                    b'{"time":Infinity}', b'{"time":-Infinity}', b'{"time":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(audit.EvidenceError):
                audit.decode(raw)

    def test_legal_family_profiles_cannot_omit_or_replace_a_binding(self):
        task = deepcopy(self.evidence["tasks"][0])
        task["expected"].pop()
        with self.assertRaisesRegex(audit.EvidenceError, "denominator"):
            audit.validate_profiles(task)
        task = deepcopy(self.evidence["tasks"][0])
        task["expected"][-1] = deepcopy(task["expected"][0])
        with self.assertRaisesRegex(audit.EvidenceError, "binding order"):
            audit.validate_profiles(task)

    def test_replay_boolean_integer_and_length_controls(self):
        original = next(task for task in self.evidence["tasks"]
                        if any(not row["equivalent"] for row in task["expected"]))
        for key in ("equivalent", "length", "indices", "trace"):
            task = deepcopy(original)
            row = next(row for row in task["expected"] if not row["equivalent"])
            if key == "equivalent":
                row[key] = 0
            elif key == "length":
                row[key] = float(row[key])
            elif key == "indices":
                row[key][0] = True
            else:
                row[key][-1]["compared_equal"] = 0
            with self.subTest(key=key), self.assertRaises(audit.EvidenceError):
                audit.validate_profiles(task)

    def test_changed_complete_replay_cannot_hide_behind_equal_failure_lengths(self):
        trial = deepcopy(self.evidence["trials"][0])
        task = next(task for task in self.evidence["tasks"]
                    if any(not row["equivalent"] for row in task["expected"]))
        row = next(row for row in trial["records"] if row["id"] == task["id"])
        changed = deepcopy(task["expected"])
        failure = next(profile for profile in changed if not profile["equivalent"])
        failure["trace"][-1]["request"][-1] = "different-action"
        row["output_sha256"] = audit.hashlib.sha256(audit.encoded(changed)).hexdigest()
        row["output_bytes"] = len(audit.encoded(changed))
        raw = {key: deepcopy(trial[key]) for key in audit.WORKER_FIELDS}
        with self.assertRaisesRegex(audit.EvidenceError, "complete output identity"):
            audit.validate_trial(trial, raw, b"", self.evidence["tasks"], self.evidence["environment"], 0, audit.METHODS[0])

    def test_original_task_and_profile_types_are_bound_to_origins(self):
        task = self.evidence["tasks"][0]
        source = {key: value for key, value in task.items() if key != "output_contract"}
        inputs = [{key: value for key, value in source.items() if key != "expected"}]
        profiles = [{"id": source["id"], "profiles": deepcopy(source["expected"])}]
        profiles[0]["profiles"][0]["equivalent"] = 1
        with self.assertRaisesRegex(audit.EvidenceError, "scientific origin"):
            audit.prepare_tasks(inputs, profiles, [source])

    def test_new_output_must_not_overlap_any_scientific_evidence(self):
        for path in (RESULTS, RESULTS / "new-review", ROOT / "src",
                     ROOT / "results/family-cost/inputs.json"):
            with self.subTest(path=path), self.assertRaises(audit.EvidenceError):
                audit.output_destination(path, RESULTS, ROOT)

    def test_output_symlink_routing_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="comparison-reader-") as temp:
            directory = Path(temp)
            target = directory / "actual"
            target.mkdir()
            link = directory / "linked"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(audit.EvidenceError, "symlinks"):
                audit.output_destination(link / "report", RESULTS, ROOT)
            self.assertEqual(list(target.iterdir()), [])


class ComparisonReaderCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="comparison-evidence-cli-")
        cls.directory = Path(cls.temporary.name)
        cls.copy = cls.directory / "comparison"
        shutil.copytree(RESULTS, cls.copy)
        cls.base_trial = audit.read(cls.copy / "trials.json")[0]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def command(self, *args, optimized=False):
        flags = ["-OO"] if optimized else []
        return subprocess.run([sys.executable, *flags, "-B", "-W", "error", str(SCRIPT),
                               "--results", str(self.copy), *map(str, args)],
                              capture_output=True, text=True, timeout=60)

    def mutate_file_and_reject(self, relative, contents, reason, optimized=False):
        path = self.copy / relative
        before = path.read_bytes()
        try:
            path.write_bytes(contents)
            result = self.command(optimized=optimized)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(reason, result.stderr)
        finally:
            path.write_bytes(before)

    def test_empty_raw_worker_file_is_rejected_by_cli(self):
        self.mutate_file_and_reject(self.base_trial["stdout"], b"{}", "raw worker: exact fields")

    def test_boolean_return_code_is_rejected_even_under_optimization(self):
        trials = audit.read(self.copy / "trials.json")
        trials[0]["exit_code"] = False
        self.mutate_file_and_reject("trials.json", audit.encoded(trials), "process return code: integer", optimized=True)

    def test_missing_log_file_is_rejected(self):
        path = self.copy / self.base_trial["stdout"]
        before = path.read_bytes()
        try:
            path.unlink()
            result = self.command()
            self.assertEqual(result.returncode, 2)
            self.assertIn("complete raw stdout grid", result.stderr)
        finally:
            path.write_bytes(before)

    def test_log_symlink_is_rejected(self):
        path = self.copy / self.base_trial["stdout"]
        before = path.read_bytes()
        external = self.directory / "external-worker.json"
        external.write_bytes(before)
        try:
            path.unlink()
            path.symlink_to(external)
            result = self.command()
            self.assertEqual(result.returncode, 2)
            self.assertIn("symlinks", result.stderr)
        finally:
            path.unlink()
            path.write_bytes(before)
            external.unlink()

    def test_duplicate_json_field_is_rejected(self):
        raw = audit.read(self.copy / self.base_trial["stdout"])
        payload = audit.encoded(raw)
        duplicate = b'{"complete_outputs_compared":false,' + payload[1:]
        self.mutate_file_and_reject(self.base_trial["stdout"], duplicate, "duplicate key")

    def test_existing_output_is_untouched_and_rejected_before_audit(self):
        output = self.directory / "existing-output"
        output.mkdir(exist_ok=True)
        sentinel = output / "keep.txt"
        sentinel.write_text("unchanged")
        result = self.command("--output", output)
        self.assertEqual(result.returncode, 2)
        self.assertIn("fresh audit output", result.stderr)
        self.assertEqual(sentinel.read_text(), "unchanged")
        self.assertEqual([path.name for path in output.iterdir()], ["keep.txt"])

    def test_read_only_cli_accepts_complete_evidence_and_preserves_files(self):
        paths = audit._files(self.copy)
        before = audit._snapshot(paths)
        result = self.command(optimized=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["timed_task_records"], 5320)
        self.assertEqual(audit._snapshot(paths), before)
        self.assertEqual(set(audit._files(self.copy)), set(paths))


if __name__ == "__main__":
    unittest.main()
