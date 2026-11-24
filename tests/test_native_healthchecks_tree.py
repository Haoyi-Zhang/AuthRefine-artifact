"""Bounded native language, physical histories and independent expectation checks."""
from copy import deepcopy
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

ART = Path(__file__).resolve().parents[1]
if str(ART) not in sys.path:
    sys.path.insert(0, str(ART))
from source_study.native_healthchecks import run as retained
from source_study.native_healthchecks_tree import audit, encoding, run, specification as spec


class NativeHealthchecksTreeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = ART / "results/native-healthchecks-tree"
        cls.directory = cls.results / "native/original/hashed-api-3-new"
        cls.case = spec.read(cls.directory / "observations.json.gz")

    def test_all_complete_native_trees_and_replays_are_recomputed(self):
        summary = audit.verify(self.results)
        self.assertTrue(spec.typed_equal(summary, spec.read(self.results / "summary.json")))
        self.assertEqual((summary["native_trees"], summary["native_http_edges"]), (60, 2340))
        self.assertEqual((summary["native_replay_words"], summary["native_replay_http_requests"]), (312, 732))
        self.assertEqual(summary["native_replayed_negative_results"], 396)

    def test_worst_case_core_bounds_and_complete_word_union(self):
        result = encoding.bound_probe()
        self.assertEqual(result["union_words"], 40)
        for branch in result["branches"]:
            self.assertEqual((branch["target_states"], branch["caller_states"], branch["state_bits"], branch["ast_nodes"]),
                             (14, 6, 5, 104))

    def test_missing_or_duplicate_evidence_is_rejected_before_both_profiles(self):
        for change in ("missing", "duplicate"):
            case = deepcopy(self.case)
            if change == "missing":
                case["records"].pop()
            else:
                case["records"][-1] = deepcopy(case["records"][0])
            with self.assertRaisesRegex(ValueError, "incomplete"):
                spec.independent_profile(case, "http_status")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                encoding.diagnose(case)

    def test_actual_child_preserves_the_full_parent_history(self):
        case = deepcopy(self.case)
        row = next(row for row in case["records"] if row["word"] == ["pause", "resume"])
        row["before"]["tables"]["api_flip"].clear()
        with self.assertRaisesRegex(ValueError, "physical parent"):
            encoding.diagnose(case)

    def test_history_label_erasure_is_not_just_a_depth_counter(self):
        profiles = encoding.diagnose(self.case)
        branch = deepcopy(profiles[0]["components"][0]["inputs"])
        branch["target_histories"][2] = ["pause", "get"]
        with self.assertRaisesRegex(ValueError, "physical history"):
            encoding.verify_language(branch)

    def test_absent_enabled_core_edge_is_rejected(self):
        profiles = encoding.diagnose(self.case)
        branch = deepcopy(profiles[0]["components"][0]["inputs"])
        index = next(i for i, edge in enumerate(branch["machine"]["transitions"][0]) if edge is not None)
        branch["machine"]["transitions"][0][index] = None
        with self.assertRaisesRegex(ValueError, "absent native edge"):
            encoding.verify_language(branch)

    def test_unqueried_user_relationship_and_sequence_rows_remain_observable(self):
        for table, field, value in (
            ("auth_user", "is_active", 0),
            ("api_channel_checks", "check_id", 999),
            ("sqlite_sequence", "seq", 999),
        ):
            case = deepcopy(self.case)
            row = next(row for row in case["records"] if row["word"] == ["get", "get", "get"])
            row["after"]["tables"][table][0][field] = value
            result = spec.independent_profile(case, "complete")
            self.assertEqual(result["shortest_word"], ["get", "get", "get"])
            self.assertTrue(spec.independent_profile(case, "http_status")["equivalent"])
            self.assertEqual(encoding.diagnose(case)[0]["shortest_word"], result["shortest_word"])

    def test_full_error_body_and_header_values_are_compared(self):
        case = deepcopy(self.case)
        row = next(row for row in case["records"] if row["word"] == ["resume"])
        row["response_text"] = "unintended response content"
        row["response_headers"]["Content-Length"] = str(len(row["response_text"].encode()))
        self.assertEqual(spec.independent_profile(case, "complete")["shortest_word"], ["resume"])
        case = deepcopy(self.case)
        row = next(row for row in case["records"] if row["word"] == ["get"])
        row["response_headers"]["Access-Control-Allow-Origin"] = "unrelated-origin"
        self.assertEqual(encoding.diagnose(case)[0]["shortest_word"], ["get"])

    def test_client_cookie_continuity_cannot_be_reset_between_branches(self):
        case = deepcopy(self.case)
        row = next(row for row in case["records"] if row["word"] == ["get", "pause"])
        row["client_cookies_before"] = {"unexpected": "unexpected=value"}
        with self.assertRaisesRegex(ValueError, "cookie continuity"):
            spec.independent_profile(case, "complete")

    def test_reference_continues_from_expected_not_faulty_actual_parent(self):
        case = spec.read(self.results / "native/omit_pause_persistence/hashed-api-3-paused/observations.json.gz")
        by_word = spec.admit(case)
        actual_after_pause = by_word[("resume", "pause")]["after"]["tables"]["api_check"][0]
        self.assertEqual(actual_after_pause["status"], "new")
        self.assertEqual(spec.state_after(case, ("resume", "pause"))["alice"], "paused")
        results = encoding.diagnose(case)
        self.assertEqual(results[0]["shortest_word"], ["resume", "pause"])
        self.assertEqual(results[1]["shortest_word"], ["resume", "pause", "resume"])
        self.assertEqual(by_word[("resume", "pause", "resume")]["http_status"], 409)

    def test_source_manifest_cannot_replace_a_missing_path_with_a_duplicate(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            shutil.copytree(self.results / "source-controls", output / "source-controls")
            manifest = spec.read(self.results / "source-controls.json")
            original = manifest[0]["files"]
            missing = next(index for index, row in enumerate(original) if row["path"] == "hc/api/views.py")
            duplicate = next(row for row in original if row["path"] == "requirements.txt")
            original[missing] = deepcopy(duplicate)
            (output / "source-controls/original/hc/api/views.py").unlink()
            spec.write(output / "source-controls.json", manifest)
            with self.assertRaisesRegex(ValueError, "duplicated or incomplete"):
                audit.source_check(output)

    def collection_inputs(self):
        receipt = spec.read(self.results / "acquisition.json")["runs"][0]
        _, source, report = audit.execution_receipt(receipt, "original")
        collection = spec.read(self.results / "native/original/collection.json")
        pinned = audit.dependencies(self.results)
        return collection, source, deepcopy(collection["cases"]), report, pinned

    def test_collection_requires_every_native_module_at_its_source_path(self):
        collection, source, cases, report, pinned = self.collection_inputs()
        collection["imported_application_modules"]["hc.api.views"] = "/outside-source/fake.py"
        with self.assertRaisesRegex(ValueError, "module mapping"):
            audit.collection_provenance(collection, "original", source, cases, report, pinned)

    def test_collection_clock_and_checkpoint_claims_are_admitted_exactly(self):
        for field in ("checkpoint_clock_restored", "complete_sqlite_checkpoints", "cookie_state_preserved", "source_imports_replaced"):
            collection, source, cases, report, pinned = self.collection_inputs()
            collection[field] = not collection[field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "provenance flag"):
                audit.collection_provenance(collection, "original", source, cases, report, pinned)

    def test_collection_case_counts_and_strata_match_the_native_index(self):
        for field, value in (("edges", 999), ("api_version", 3), ("directory", "../unexpected"), ("format", "hashed")):
            collection, source, cases, report, pinned = self.collection_inputs()
            collection["cases"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "case index"):
                audit.collection_provenance(collection, "original", source, cases, report, pinned)
        with TemporaryDirectory() as directory:
            output = Path(directory)
            collection = spec.read(self.results / "native/original/collection.json")
            first = collection["cases"][0]
            case = spec.read(self.results / "native/original" / first["directory"] / "observations.json.gz")
            case["api_version"] = float(case["api_version"])
            spec.write(output / "native/original/collection.json", collection)
            spec.write(output / "native/original" / first["directory"] / "observations.json.gz", case)
            with self.assertRaisesRegex(ValueError, "mislabelled native tree"):
                list(run.cases(output))

    def test_failed_main_or_replay_execution_receipts_are_rejected(self):
        main = spec.read(self.results / "acquisition.json")["runs"][0]
        replay = spec.read(self.results / "native-replay.json")[0]
        main["returncode"] = 124
        replay["receipt"]["returncode"] = 124
        with self.assertRaisesRegex(ValueError, "unsuccessful"):
            audit.execution_receipt(main, "original")
        with self.assertRaisesRegex(ValueError, "unsuccessful"):
            audit.execution_receipt(replay["receipt"], replay["arm"], replay=True)

    def test_native_stdout_counts_must_match_the_recorded_case_index(self):
        collection, source, cases, report, pinned = self.collection_inputs()
        report["native_http_requests"] = 999
        with self.assertRaisesRegex(ValueError, "stdout counts"):
            audit.collection_provenance(collection, "original", source, cases, report, pinned)

    def test_json_types_remain_distinct_in_the_observation_contract(self):
        for left, right in ((False, 0), (True, 1), (1, 1.0), ({"value": False}, {"value": 0})):
            self.assertFalse(spec.typed_equal(left, right))
        clock_projection = spec.projected_store({"tables": {"api_flip": [{"created": 1, "processed": True}]}})
        self.assertFalse(clock_projection["tables"]["api_flip"][0]["processed_at_creation"])
        case = deepcopy(self.case)
        row = next(row for row in case["records"] if row["word"] == ["get", "get", "get"])
        old_length = len(row["response_text"].encode())
        row["response"]["started"] = 0
        text = json.dumps(row["response"])
        row["response_text"] = text + " " * (old_length - len(text.encode()))
        self.assertEqual(len(row["response_text"].encode()), old_length)
        self.assertEqual(spec.independent_profile(case, "complete")["shortest_word"], ["get", "get", "get"])
        self.assertEqual(encoding.diagnose(case)[0]["shortest_word"], ["get", "get", "get"])

    def test_wire_only_numeric_boolean_substitution_cannot_pass_admission(self):
        case = deepcopy(self.case)
        row = next(row for row in case["records"] if row["word"] == ["get", "get", "get"])
        text = row["response_text"].replace('"n_pings": 0', '"n_pings": false', 1).replace(": ", ":", 4)
        self.assertEqual(len(text.encode()), len(row["response_text"].encode()))
        row["response_text"] = text
        for mode in ("complete", "http_status"):
            with self.assertRaisesRegex(ValueError, "response text and parsed document"):
                spec.independent_profile(case, mode)
        with self.assertRaisesRegex(ValueError, "response text and parsed document"):
            encoding.diagnose(case)

    def test_checkpoint_rows_use_type_sensitive_sqlite_comparison(self):
        case = deepcopy(self.case)
        row = next(row for row in case["records"] if row["word"] == ["get", "get", "get"])
        self.assertEqual(row["after"]["tables"]["auth_user"][0]["is_active"], 1)
        row["after"]["tables"]["auth_user"][0]["is_active"] = True
        with self.assertRaisesRegex(ValueError, "complete native SQLite checkpoint differs"):
            audit.checkpoints(self.directory, case)


def native_available():
    try:
        return all(importlib.metadata.version(name) == version for name, version in
                   (line.split("==") for line in (retained.ROOT / "requirements.lock").read_text().splitlines()))
    except importlib.metadata.PackageNotFoundError:
        return False


@unittest.skipUnless(native_available(), "install source_study/native_healthchecks/requirements.lock")
class NativeHealthchecksTreeExecutionTests(unittest.TestCase):
    def test_actual_original_paused_tree_and_every_sqlite_checkpoint(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "native"
            run.native_call(retained.ROOT / "source", output, "original", one=("hashed", 3, "paused"))
            path = output / "hashed-api-3-paused"
            case = spec.read(path / "observations.json.gz")
            self.assertEqual(audit.checkpoints(path, case), 40)
            self.assertTrue(all(row["equivalent"] for row in encoding.diagnose(case)))
            self.assertEqual(len(spec.read(output / "collection.json")["imported_application_modules"]), 27)

    def test_actual_source_omission_changes_history_dependent_first_failure(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            retained.prepare_sources(base / "source-controls")
            output = base / "native"
            run.native_call(base / "source-controls/omit_pause_persistence", output, "omit_pause_persistence",
                            one=("hashed", 3, "paused"))
            case = spec.read(output / "hashed-api-3-paused/observations.json.gz")
            results = encoding.diagnose(case)
            self.assertEqual(results[0]["shortest_word"], ["resume", "pause"])
            self.assertEqual(results[1]["shortest_word"], ["resume", "pause", "resume"])


if __name__ == "__main__":
    unittest.main()
