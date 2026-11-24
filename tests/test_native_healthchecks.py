"""Regression checks for native Healthchecks evidence and its observer."""
from copy import deepcopy
from contextlib import redirect_stdout
import gzip
import importlib.metadata
import io
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ART = Path(__file__).resolve().parents[1]
if str(ART) not in sys.path: sys.path.insert(0, str(ART))
from source_study.native_healthchecks import contracts, outcomes, production, run, summarize


class NativeHealthchecksEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = ART / "results/native-healthchecks"
        cls.case = run.read(cls.results / "native/original/observations.json.gz")["cases"][0]

    def outcome(self, case):
        direct = outcomes.independent_profile(case, "lifecycle", "complete")
        measured = production.diagnose(case, "lifecycle", "complete")
        self.assertEqual((direct["equivalent"], direct["length"]), (measured["equivalent"], measured["length"]))
        return measured

    def alter_json(self, case, index, transform):
        record = case["records"][index]
        transform(record["response"])
        record["response_text"] = json.dumps(record["response"])
        record["response_headers"]["Content-Length"] = str(len(record["response_text"].encode()))

    def test_all_retained_scientific_results_are_recomputed(self):
        result = summarize.verify(self.results)
        self.assertEqual(result["native_cases"], 120)
        self.assertEqual(result["native_http_requests"], 4200)
        self.assertEqual(result["native_key_rotations"], 240)
        self.assertFalse(result["shared_target_correspondence_family"])
        self.assertEqual(result["upstream_tests"], 30)
        self.assertEqual(production.canonical(result), production.canonical(run.read(self.results / "summary.json")))
        # The actual science is recomputed above. Exercise the CLI's separate
        # no-write summary acceptance contract without repeating that workload.
        with TemporaryDirectory() as directory:
            output = Path(directory)
            run.write(output / "summary.json", result)
            before = (output / "summary.json").read_bytes()
            with patch.object(summarize, "verify", return_value=result), patch.object(sys, "argv", ["run", "verify", "--output", str(output)]), redirect_stdout(io.StringIO()):
                run.main()
                self.assertEqual((output / "summary.json").read_bytes(), before)
                changed = deepcopy(result)
                changed["native_cases"] += 1
                run.write(output / "summary.json", changed)
                changed_bytes = (output / "summary.json").read_bytes()
                with self.assertRaisesRegex(ValueError, "retained summary differs"):
                    run.main()
                self.assertEqual((output / "summary.json").read_bytes(), changed_bytes)
                self.assertEqual([path.name for path in output.iterdir()], ["summary.json"])

    def test_original_source_is_exact_and_edits_are_explicit(self):
        self.assertEqual(len(run.source_identity()["files"]), 34)
        controls = run.read(self.results / "source-controls.json")
        self.assertFalse(controls[0]["patch"])
        self.assertTrue(all(item["patch"] for item in controls[1:]))
        self.assertTrue(all(not item["historical_deployment_executed"] for item in controls))

    def assert_preflight_rejected(self, filename, transform, message):
        # Copy only the files required to reach this admission gate. Rejection
        # must precede access to the absent production diagnoses and databases.
        with TemporaryDirectory() as directory:
            output = Path(directory)
            shutil.copytree(self.results / "source-controls", output / "source-controls")
            names = ("source-controls.json", "acquisition.json", "native-replay.json", "upstream-tests.json")
            if filename not in names:
                names += (filename,)
            for name in names:
                value = run.read(self.results / name)
                if name == filename:
                    transform(value)
                run.write(output / name, value)
            with self.assertRaisesRegex(ValueError, message):
                summarize.verify(output)

    def test_source_manifest_cannot_omit_or_duplicate_a_module(self):
        def omit(controls):
            controls[0]["files"] = [row for row in controls[0]["files"] if row["path"] != "hc/api/views.py"]

        def substitute(controls):
            files = controls[0]["files"]
            index = next(i for i, row in enumerate(files) if row["path"] == "hc/api/views.py")
            files[index] = deepcopy(files[0])

        for transform in (omit, substitute):
            with self.subTest(control=transform.__name__):
                self.assert_preflight_rejected("source-controls.json", transform, "complete unique original file set")

    def test_unsuccessful_or_noninteger_process_receipts_are_rejected(self):
        for filename, select, message in (
                ("acquisition.json", lambda rows: rows["runs"][0], "native acquisition receipt is not successful"),
                ("native-replay.json", lambda rows: rows[0]["receipt"], "native replay receipt is not successful"),
                ("upstream-tests.json", lambda row: row, "upstream native test receipt is not successful")):
            for returncode in (124, False, 0.0):
                with self.subTest(file=filename, returncode=repr(returncode)):
                    self.assert_preflight_rejected(filename,
                        lambda value: select(value).update(returncode=returncode), message)

    def test_acquisition_receipts_require_every_source_arm(self):
        def duplicate(acquisition):
            acquisition["runs"][-1] = deepcopy(acquisition["runs"][0])

        self.assert_preflight_rejected("acquisition.json", duplicate, "cover each source arm")

    def test_provenance_booleans_and_source_byte_counts_keep_their_types(self):
        self.assert_preflight_rejected("acquisition.json",
            lambda value: value.update(source_imports_replaced=0), "native acquisition declarations differ")
        self.assert_preflight_rejected("source-controls.json",
            lambda rows: rows[0].update(current_complete_source_modules=1), "source control declarations differ")
        self.assert_preflight_rejected("source-controls.json",
            lambda rows: rows[0]["files"][0].update(bytes=float(rows[0]["files"][0]["bytes"])),
            "executed source control bytes differ")

    def test_module_map_requires_every_module_and_its_exact_source_file(self):
        def empty(document):
            document["imported_application_modules"] = {}

        def missing(document):
            del document["imported_application_modules"]["hc.api.views"]

        def wrong_file(document):
            modules = document["imported_application_modules"]
            modules["hc.api.views"] = modules["hc.api.models"]

        for transform in (empty, missing, wrong_file):
            with self.subTest(control=transform.__name__):
                self.assert_preflight_rejected("native/original/observations.json.gz", transform,
                    "native module map is not the complete declared source mapping")

    def test_an_unmeasured_error_body_field_is_not_lost(self):
        case = deepcopy(self.case)
        self.alter_json(case, 10, lambda body: body.update(error="different error including an unintended credential"))
        self.assertEqual(self.outcome(case)["length"], 11)

    def test_every_success_json_field_remains_observable(self):
        case = deepcopy(self.case)
        self.alter_json(case, 0, lambda body: body.update(timeout=1))
        self.assertEqual(self.outcome(case)["length"], 1)

    def test_json_scalar_types_are_observable(self):
        for field, replacement in (("n_pings", False), ("manual_resume", 0), ("n_pings", 0.0)):
            with self.subTest(field=field, replacement_type=type(replacement).__name__):
                case = deepcopy(self.case)
                self.alter_json(case, 0, lambda body: body.update({field: replacement}))
                self.assertEqual(self.outcome(case)["length"], 1)
        case = deepcopy(self.case)
        case["records"][0]["manager_result_is_request_project"] = 1
        self.assertEqual(self.outcome(case)["length"], 1)

    def test_equal_length_wire_type_change_is_rejected_before_projection(self):
        case = deepcopy(self.case)
        record = case["records"][0]
        original = record["response_text"]
        self.assertIn('"n_pings": 0', original)
        changed = original.replace('"n_pings": 0', '"n_pings": false', 1)
        for _ in range(4):
            changed = changed.replace(", ", ",", 1)
        self.assertEqual(len(original.encode()), len(changed.encode()))
        record["response_text"] = changed
        self.assertIs(type(record["response"]["n_pings"]), int)
        for check in (
                lambda: contracts.check_case(case),
                lambda: outcomes.independent_profile(case, "lifecycle", "complete"),
                lambda: production.diagnose(case, "lifecycle", "http_status")):
            with self.assertRaisesRegex(ValueError, "response object and actual body differ"):
                check()

    def test_incomplete_independent_input_cannot_certify_a_full_caller(self):
        case = deepcopy(self.case)
        case["records"] = case["records"][:1]
        with self.assertRaisesRegex(ValueError, "incomplete finite caller"):
            outcomes.independent_profile(case, "lifecycle", "complete")
        with self.assertRaisesRegex(ValueError, "incomplete replay cannot establish agreement"):
            outcomes.independent_profile(case, "lifecycle", "complete", replay_length=1)
        self.alter_json(case, 0, lambda body: body.update(n_pings=False))
        profile = outcomes.independent_profile(case, "lifecycle", "complete", replay_length=1)
        self.assertFalse(profile["equivalent"])
        self.assertEqual(profile["length"], 1)

    def test_boolean_api_version_is_not_an_integer_version(self):
        case = deepcopy(self.case)
        case["api_version"] = True
        with self.assertRaisesRegex(ValueError, "undeclared native case"):
            production.diagnose(case, "lifecycle", "complete")

    def test_native_manager_object_handoff_is_observable(self):
        case = deepcopy(self.case)
        case["records"][0]["source_manager_returns"][0]["project_id"] = case["owners"]["bob"]["project_id"]
        case["records"][0]["manager_result_is_request_project"] = False
        self.assertEqual(self.outcome(case)["length"], 1)

    def test_unqueried_credential_slot_is_checked_after_rotation(self):
        case = deepcopy(self.case)
        for index, record in enumerate(case["records"]):
            if index < 29: continue
            for key in (["after"] if index == 29 else ["before", "after"]):
                for project in record[key]["projects"]:
                    if project["id"] == case["owners"]["bob"]["project_id"]:
                        project["api_key_readonly"] = "changed-unqueried-slot"
        self.assertEqual(self.outcome(case)["length"], 30)

    def test_metadata_and_cookie_changes_are_observable(self):
        case = deepcopy(self.case)
        case["records"][20]["response_headers"]["Access-Control-Allow-Origin"] = "unrelated-origin"
        self.assertEqual(self.outcome(case)["length"], 21)
        case = deepcopy(self.case)
        case["records"][10]["response_cookies"] = {"credential": "credential=unexpected"}
        self.assertEqual(self.outcome(case)["length"], 11)

    def test_method_order_normalization_preserves_the_same_values(self):
        case = deepcopy(self.case)
        value = case["records"][0]["response_headers"]["Access-Control-Allow-Methods"]
        case["records"][0]["response_headers"]["Access-Control-Allow-Methods"] = ", ".join(reversed(value.split(", ")))
        self.assertTrue(self.outcome(case)["equivalent"])

    def test_full_input_admission_precedes_even_the_short_caller(self):
        case = deepcopy(self.case)
        case["records"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete finite caller"):
            production.diagnose(case, "single_check_read", "complete")
        case = deepcopy(self.case)
        case["records"][15]["before"]["projects"][0]["name"] = "changed at block boundary"
        with self.assertRaisesRegex(ValueError, "actual prefix"):
            production.diagnose(case, "lifecycle", "complete")

    def test_each_block_boundary_preserves_first_difference_position(self):
        for index in (14, 15, 29, 30, 36):
            case = deepcopy(self.case)
            if case["records"][index]["operation"]["kind"] == "http":
                case["records"][index]["request_api_version"] = 99
            else:
                case["records"][index]["producer_class"] = "changed.Class"
            self.assertEqual(self.outcome(case)["length"], index + 1)


def native_available():
    try:
        return all(importlib.metadata.version(name) == version for name, version in
            (line.split("==") for line in (run.ROOT / "requirements.lock").read_text().splitlines()))
    except importlib.metadata.PackageNotFoundError:
        return False


@unittest.skipUnless(native_available(), "install source_study/native_healthchecks/requirements.lock")
class NativeHealthchecksExecutionTests(unittest.TestCase):
    def test_actual_full_original_modules_and_native_orm(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "actual"
            run.subprocess_native(run.ROOT / "source", output, "original", ("hashed", 3, "identity"))
            record = run.read(output / "observations.json.gz")
            result = contracts.check_case(record["cases"][0])
            self.assertEqual(result["disagreements"], [])
            self.assertEqual(result["http_requests"], 35)
            self.assertFalse(record["source_imports_replaced"])
            self.assertEqual(len(record["imported_application_modules"]), 27)

    def test_real_source_edit_loses_context_with_unchanged_http_statuses(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            run.prepare_sources(base / "source-controls")
            output = base / "actual"
            run.subprocess_native(base / "source-controls/omit_readonly_context", output, "omit_readonly_context", ("hashed", 3, "identity"))
            case = run.read(output / "observations.json.gz")["cases"][0]
            contracts.check_case(case)
            self.assertEqual(outcomes.independent_profile(case, "lifecycle", "complete")["length"], 1)
            self.assertTrue(outcomes.independent_profile(case, "lifecycle", "http_status")["equivalent"])


if __name__ == "__main__": unittest.main()
