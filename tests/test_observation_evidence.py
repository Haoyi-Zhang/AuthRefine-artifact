"""Evidence-domain failures and type changes that previously passed comparison."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from source_study import replay
from source_study.observation_evidence import typed_equal, validate_credential_evidence
from source_study.independent_observer.evidence import validate_observations, validate_resume_graphs

ART = Path(__file__).resolve().parents[1]


def replace_path(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


class CredentialEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = replay.source_check()
        from credential_flow_contexts import expected
        cls.expected = staticmethod(expected)
        cls.original = replay.read(replay.ROOT / "data/credential-observations.json")

    def validate(self, value):
        return validate_credential_evidence(value, self.packet["owned_inputs"], self.expected)

    def test_full_retained_domain_recomputes_without_coercion(self):
        totals = self.validate(self.original)
        self.assertEqual(totals["contexts"], 1260)
        self.assertEqual(totals["actual_SELECTs"], 1332)
        self.assertEqual(totals["serializer_transfers"], 144)
        self.assertEqual(totals["differences"], 0)

    def test_type_changes_and_self_reported_agreement_do_not_authorize_admission(self):
        controls = [
            (("rows", 0, "observed", "readonly"), 0),
            (("rows", 0, "observed", "version"), True),
            (("rows", 0, "observed", "project"), 1.0),
            (("rows", 0, "expected", "version"), True),
            (("rows", 0, "agrees"), 1),
            (("rows", 0, "agrees"), False),
            (("rows", 0, "exact_resolved_project_identity_transferred"), 1),
            (("rows", 0, "serializer_transfers", 0, "readonly"), 0),
            (("rows", 0, "serializer_transfers", 0, "v"), True),
            (("rows", 0, "serializer_transfers", 0, "check_id"), True),
            (("rows", 0, "source_manager_returns", 0, "project"), True),
            (("rows", 0, "IR_steps"), True),
            (("totals", "contexts"), 1260.0),
            (("producer_records", 0, "returned_key_matches"), 1),
            (("original_application_modules_or_tests_executed",), 0),
        ]
        for path, value in controls:
            with self.subTest(path=path, value=value):
                altered = deepcopy(self.original)
                replace_path(altered, path, value)
                with self.assertRaises(ValueError):
                    self.validate(altered)

    def test_missing_duplicate_extra_and_renamed_rows_are_rejected(self):
        for control in ("missing", "duplicate", "extra", "renamed"):
            with self.subTest(control=control):
                altered = deepcopy(self.original)
                if control == "missing":
                    altered["rows"].pop()
                elif control == "duplicate":
                    altered["rows"][-1] = deepcopy(altered["rows"][0])
                elif control == "extra":
                    altered["rows"].append(deepcopy(altered["rows"][0]))
                else:
                    altered["rows"][0]["id"] = "undeclared"
                with self.assertRaises(ValueError):
                    self.validate(altered)

    def test_public_source_check_rejects_changed_records_and_changed_fixture_types(self):
        original_read = replay.read
        for target in ("observation", "fixture"):
            with self.subTest(target=target):
                changed = deepcopy(self.original if target == "observation" else self.packet)
                if target == "observation":
                    changed["rows"][0]["observed"]["version"] = True
                else:
                    changed["owned_inputs"][0]["version"] = True
                filename = "credential-observations.json" if target == "observation" else "credential-input.json"
                def read(path):
                    return changed if Path(path).name == filename else original_read(path)
                with patch.object(replay, "read", side_effect=read):
                    with self.assertRaises(ValueError):
                        replay.source_check()

    def test_serializer_keyword_cannot_be_renamed_to_observation_field(self):
        altered = deepcopy(self.original)
        transfer = altered["rows"][0]["serializer_transfers"][0]
        transfer["version"] = transfer.pop("v")
        with self.assertRaisesRegex(ValueError, "serializer"):
            self.validate(altered)


class IndependentEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads((ART / "results/source-observer/direct-observations.json").read_text())

    def test_complete_source_graphs_and_fixture_domains_pass(self):
        self.assertEqual(validate_observations(self.original),
                         {"healthchecks_reads": 480, "healthchecks_resume": 448, "pretix": 288, "wger_owner_insert": 16})

    def test_typed_schema_catches_coercions_in_all_profiles(self):
        controls = [
            (("healthchecks_reads", 0, "observation", "version"), True),
            (("healthchecks_reads", 0, "observation", "readonly"), 0),
            (("healthchecks_reads", 0, "observation", "exact_resolved_identity"), 1),
            (("healthchecks_reads", 0, "observation", "serializers", 0, "v"), True),
            (("pretix", 0, "observation", "allow"), 0),
            (("pretix", 0, "observation", "event"), True),
            (("pretix", 0, "observation", "handoffs", 0, "request_is_same"), 1),
            (("wger_owner_insert", 0, "observation", "allowed"), 1),
            (("wger_owner_insert", 0, "observation", "rows", 1, 1), True),
            (("wger_owner_insert", 0, "observation", "saves", 0, "exact_request_user"), 1),
            (("healthchecks_resume", 0, "rows", 0, "state"), False),
            (("healthchecks_resume", 0, "rows", 0, "index"), False),
            (("healthchecks_resume", 0, "rows", 0, "observation", "after"), True),
            (("healthchecks_resume", 0, "rows", 0, "observation", "event_delta"), True),
            (("healthchecks_resume", 0, "rows", 0, "observation", "store_invariant"), 1),
            (("healthchecks_resume", 0, "rows", 0, "observation", "store", "events", 0, 2), True),
        ]
        for path, value in controls:
            with self.subTest(path=path):
                altered = deepcopy(self.original)
                replace_path(altered, path, value)
                with self.assertRaises(ValueError):
                    validate_observations(altered)

    def test_missing_extra_duplicate_and_foreign_fixture_ids_are_rejected(self):
        for cohort in ("healthchecks_reads", "pretix", "wger_owner_insert"):
            for control in ("missing", "extra", "duplicate", "foreign", "reordered"):
                with self.subTest(cohort=cohort, control=control):
                    altered = deepcopy(self.original)
                    rows = altered[cohort]
                    if control == "missing":
                        rows.pop()
                    elif control == "extra":
                        rows.append(deepcopy(rows[0]))
                    elif control == "duplicate":
                        rows[-1] = deepcopy(rows[0])
                    elif control == "foreign":
                        rows[0]["id"] = "undeclared"
                    else:
                        rows[0], rows[1] = rows[1], rows[0]
                    with self.assertRaises(ValueError):
                        validate_observations(altered)

    def test_graph_requires_all_forms_edges_and_consistent_prefixes(self):
        for control in ("missing_form", "duplicate_form", "missing_edge", "duplicate_edge", "wrong_prefix", "truncated_prefix"):
            with self.subTest(control=control):
                graphs = deepcopy(self.original["healthchecks_resume"])
                if control == "missing_form":
                    graphs.pop()
                elif control == "duplicate_form":
                    graphs[1] = deepcopy(graphs[0])
                elif control == "missing_edge":
                    graphs[0]["rows"].pop()
                elif control == "duplicate_edge":
                    graphs[0]["rows"][-1] = deepcopy(graphs[0]["rows"][0])
                else:
                    row = next(row for row in graphs[0]["rows"] if row["prefix_observations"])
                    if control == "wrong_prefix":
                        row["prefix_observations"][0]["version"] = 2
                    else:
                        row["prefix_observations"].pop()
                with self.assertRaises(ValueError):
                    validate_resume_graphs(graphs)

    def test_public_comparison_checks_completeness_before_production_runs(self):
        from source_study.independent_observer import compare
        altered = deepcopy(self.original)
        altered["pretix"].pop()
        with patch.object(compare, "production_imports", side_effect=AssertionError("incomplete evidence reached evaluator")):
            with self.assertRaisesRegex(ValueError, "complete fixture"):
                compare.compare(altered)

    def test_each_public_cohort_comparator_rejects_previous_type_counterexample(self):
        from source_study.independent_observer.compare import compare_healthchecks, compare_pretix, compare_wger
        controls = [(compare_healthchecks, ("healthchecks_reads", 0, "observation", "version"), True),
                    (compare_pretix, ("pretix", 0, "observation", "allow"), 0),
                    (compare_wger, ("wger_owner_insert", 0, "observation", "allowed"), 1)]
        for compare, path, value in controls:
            with self.subTest(cohort=path[0]):
                altered = deepcopy(self.original)
                replace_path(altered, path, value)
                with self.assertRaises(ValueError):
                    compare(altered, {}) if compare is compare_healthchecks else compare(altered)

    def test_processed_flag_contract_matches_both_executors(self):
        from source_study.independent_observer.compare import IRSession
        from source_study.independent_observer.observer import HealthSession
        from source_study.independent_observer.source import nodes_and_manifest
        nodes, _ = nodes_and_manifest()
        ir = IRSession("plain", nodes)
        ir.effects = []
        receiver = ir.Record("Check", dict(ir.records[1]))
        before = ir.snapshot()
        for value in (1, 1.0, False, None):
            with self.subTest(value=value, type=type(value).__name__):
                with self.assertRaisesRegex(ValueError, "event"):
                    ir.call(ir.Ref("Check.create_flip", receiver), ["new"], {"mark_as_processed": value})
                self.assertTrue(typed_equal(ir.snapshot(), before))
        direct = HealthSession("plain", nodes)
        try:
            check = direct.Check(direct.snapshot()["records"][0])
            with self.assertRaisesRegex(ValueError, "event"):
                check.create_flip("new", mark_as_processed=1)
            check.create_flip("new", mark_as_processed=True)
            ir.call(ir.Ref("Check.create_flip", receiver), ["new"], {"mark_as_processed": True})
            self.assertTrue(typed_equal(ir.snapshot(), direct.snapshot()))
        finally:
            direct.close()

    def test_evidence_equality_does_not_replace_python_source_equality(self):
        from source_study.independent_observer.compare import production_imports
        Machine = production_imports()[0]
        machine = Machine({}, {}, None)
        self.assertIs(machine.value(["compare", "Eq", ["constant", True], ["constant", 1]], {}), True)
        self.assertFalse(typed_equal({"flag": True, "nested": [0]}, {"flag": 1, "nested": [False]}))
        self.assertFalse(typed_equal({True: "value"}, {1: "value"}))


class RetainedSourceObserverReconciliationTests(unittest.TestCase):
    def test_ambiguous_json_and_nonfinite_numbers_are_rejected(self):
        from source_study.verify_source_observer import decode
        for text in ('{"agrees": false, "agrees": true}', '{"time": NaN}', '{"time": Infinity}'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    decode(text)

    def test_a_recorded_boolean_is_not_a_success_exit_code(self):
        from source_study import verify_source_observer as verifier
        original_read = verifier.read
        directory = ART / "results/source-observer"
        runtime = original_read(directory / "runtime.json")
        runtime["exit_status"] = False
        with patch.object(verifier, "read", side_effect=lambda path: runtime if Path(path).name == "runtime.json" else original_read(path)):
            with self.assertRaisesRegex(ValueError, "runtime.exit_status.*integer"):
                verifier.verify_records(directory)

    def test_empty_or_incomplete_module_manifest_does_not_verify(self):
        from source_study import verify_source_observer as verifier
        runtime = {
            "source_sha256": {path.name: verifier.sha(path) for path in verifier.OBSERVER.glob("*.py")},
            "production_module_sha256": {name: verifier.sha(ART / name) for name in verifier.PRODUCTION_SOURCES},
        }
        for control in ("empty", "missing_shared_validator"):
            with self.subTest(control=control):
                altered = deepcopy(runtime)
                if control == "empty":
                    altered["production_module_sha256"] = {}
                else:
                    del altered["production_module_sha256"]["source_study/observation_evidence.py"]
                with self.assertRaisesRegex(ValueError, "complete production/shared-module identities"):
                    verifier.source_identities(altered)

    def test_control_totals_must_follow_actual_changed_records(self):
        from source_study import verify_source_observer as verifier
        directory = ART / "results/source-observer"
        direct = verifier.read(directory / "direct-observations.json")
        comparison = verifier.read(directory / "comparisons.json")
        controls = verifier.read(directory / "source-controls.json")
        hashes = {name: verifier.sha(directory / name) for name in verifier.SCIENCE}
        summary = verifier.recompute_summary(direct, comparison, controls, hashes)
        self.assertEqual((summary["source_mutation_tests"], summary["source_mutation_changed_observations"],
                          summary["source_mutation_response_differences"], summary["source_mutation_field_only_differences"]),
                         (2896, 318, 24, 294))
        for control in ("count", "typed_response_flag", "differing_fields"):
            with self.subTest(control=control):
                altered = deepcopy(controls)
                if control == "count":
                    altered[0]["changed_observations"] -= 1
                elif control == "typed_response_flag":
                    altered[0]["rows"][0]["response_changed"] = 0
                else:
                    altered[0]["rows"][0]["differing_fields"] = []
                with self.assertRaises(ValueError):
                    verifier.recompute_summary(direct, comparison, altered, hashes)


if __name__ == "__main__":
    unittest.main()
