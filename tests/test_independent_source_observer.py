"""Meaningful failures at source, state, handoff and graph-encoding boundaries."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from source_study.independent_observer import source
from source_study.independent_observer.fixtures import request, code, pretix_fixtures
from source_study.independent_observer.observer import HealthSession, observe_pretix, observe_wger, observe_resume_graph


class IndependentSourceObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes, cls.manifest = source.nodes_and_manifest()

    def read(self, key="1w", target=1, version=3, control=None, carrier="header"):
        nodes = self.nodes if control is None else source.nodes_and_manifest(control)[0]
        session = HealthSession("stored_mac", nodes)
        try:
            return session.invoke(request("stored_mac", key, version, carrier), target)
        finally:
            session.close()

    def resume(self, control=None):
        nodes = self.nodes if control is None else source.nodes_and_manifest(control)[0]
        session = HealthSession("plain", nodes)
        try:
            return session.resume({"key": "1w", "target": 1})
        finally:
            session.close()

    def test_changed_source_fails_before_compilation(self):
        path = source.ART / source.SOURCES["health_models"][0]
        original_read = Path.read_bytes
        def read_bytes(p):
            raw = original_read(p)
            return raw + b"\n# changed source\n" if p == path else raw
        with patch.object(Path, "read_bytes", read_bytes):
            with self.assertRaisesRegex(ValueError, "source identity differs"):
                source.nodes_and_manifest()

    def test_extraction_keeps_complete_bodies(self):
        raw = source.load_sources()
        for key, (module, owner, name) in source.SELECTIONS.items():
            original = source.select(raw[module], owner, name)
            normalized = source.SignatureOnly().visit(deepcopy(original))
            self.assertEqual(ast.dump(normalized, include_attributes=False),
                             ast.dump(self.nodes[key], include_attributes=False))
            self.assertFalse(any(n.decorator_list for n in ast.walk(self.nodes[key]) if isinstance(n, ast.FunctionDef)))

    def test_same_prefix_mac_candidates_keep_resolved_identity(self):
        first, second = self.read("1w", 1), self.read("2w", 2)
        self.assertEqual((first["status"], second["status"]), (200, 200))
        self.assertEqual((first["project"], second["project"]), (1, 2))
        self.assertTrue(first["exact_resolved_identity"] and second["exact_resolved_identity"])
        bad = self.read("bad_digest", 1)
        self.assertEqual(bad["status"], 401)
        self.assertEqual(bad["manager_returns"], [None])

    def test_body_only_get_stops_before_lookup(self):
        got = self.read(carrier="body")
        self.assertEqual(got["status"], 401)
        self.assertEqual(got["manager_returns"], [])
        self.assertEqual(got["serializers"], [])

    def test_read_controls_preserve_response_change_actual_arguments(self):
        base = self.read()
        version = self.read(control="read_wrong_version")
        foreign = self.read(control="read_foreign_serializer")
        self.assertEqual((base["status"], version["status"], foreign["status"]), (200, 200, 200))
        self.assertEqual(base["serializers"][0]["v"], 3)
        self.assertEqual(version["serializers"][0]["v"], 1)
        self.assertEqual((foreign["project"], foreign["serializers"][0]["project_id"]), (1, 2))

    def test_denial_does_not_reach_foreign_serializer_control(self):
        base, changed = self.read(target=2), self.read(target=2, control="read_foreign_serializer")
        self.assertEqual(base, changed)
        self.assertEqual(base["status"], 403)

    def test_repeated_resume_checks_persisted_state(self):
        session = HealthSession("plain", self.nodes)
        try:
            first = session.resume({"key": "1w", "target": 1})
            second = session.resume({"key": "1w", "target": 1})
            self.assertEqual((first["status"], second["status"]), (200, 409))
            self.assertEqual((first["event_delta"], second["event_delta"]), (1, 0))
            self.assertEqual(first["store"], second["store"])
            self.assertTrue(first["store_invariant"] and second["store_invariant"])
        finally:
            session.close()

    def test_resume_controls_distinguish_effect_failures(self):
        base = self.resume()
        missing, duplicate, stale = [self.resume(c) for c in ("resume_omit_save", "resume_repeat_flip", "resume_stale_ping")]
        self.assertEqual([o["status"] for o in (base, missing, duplicate, stale)], [200] * 4)
        self.assertEqual(missing["after"], 0)
        self.assertEqual(duplicate["event_delta"], 2)
        self.assertEqual(stale["store"]["records"][0][5], "ping")
        self.assertTrue(base["store_invariant"])
        self.assertTrue(all(not o["store_invariant"] for o in (missing, duplicate, stale)))
        self.assertEqual(base["store"]["records"][1:], missing["store"]["records"][1:])

    def test_pretix_organizer_control_changes_handoff_with_same_allow(self):
        fixture = next(c for c in pretix_fixtures() if c["all_events"] and not c["limited_events"] and
                       c["query"] == "own-a" and c["method"] == "GET" and c["permissions"] == ["event.items:read"])
        baseline = observe_pretix(fixture, self.nodes)
        mutated = observe_pretix(fixture, source.nodes_and_manifest("pretix_wrong_organizer")[0])
        self.assertTrue(baseline["allow"] and mutated["allow"])
        self.assertEqual((baseline["organizer"], mutated["organizer"]), (1, 2))
        self.assertEqual(baseline["permissions"], ["event.items:read"])
        self.assertEqual(mutated["permissions"], [])

    def test_wger_supplied_owner_cannot_replace_authenticated_user(self):
        fixture = {"actor": "user-1", "supplied_owner": 2}
        base = observe_wger(fixture, self.nodes)
        changed = observe_wger(fixture, source.nodes_and_manifest("wger_client_owner")[0])
        self.assertTrue(base["allowed"] and changed["allowed"])
        self.assertEqual((base["rows"][-1][1], changed["rows"][-1][1]), (1, 2))
        self.assertTrue(base["saves"][0]["exact_request_user"])
        self.assertFalse(changed["saves"][0]["exact_request_user"])

    def test_all_mutations_change_exactly_one_selected_function(self):
        for control in source.MUTATIONS:
            _, manifest = source.nodes_and_manifest(control)
            changed = [r for r in manifest["functions"] if r["compiled_ast_sha256"] != r["baseline_compiled_ast_sha256"]]
            self.assertEqual(len(changed), 1)
            self.assertEqual(changed[0]["mutation"], control)

    def test_source_and_canonical_alphabets_have_explicit_bijection(self):
        from source_study.independent_observer.compare import production_imports, diagnose_stateful
        production_imports()
        graph = observe_resume_graph(self.nodes)
        reports = diagnose_stateful({"healthchecks_resume": graph})
        for report in reports:
            mapping = report["source_fixture_index_to_model_index"]
            self.assertEqual(set(mapping), set(range(28)))
            self.assertEqual(set(mapping.values()), set(range(28)))
            self.assertNotEqual(mapping[0], 0)  # canonical "absent" sorts first
            self.assertEqual(report["diagnosis"]["strata"], {"1": 26, "infinity": 1})
            self.assertEqual(len(report["cpython_witness_replays"]), 26)

    def test_production_provider_runs_without_cpython_collector(self):
        from source_study.independent_observer.compare import IRSession
        with patch.object(HealthSession, "__init__", side_effect=AssertionError("CPython collector must not be used")):
            session = IRSession("stored_mac", self.nodes)
            read = session.invoke(request("stored_mac", "2r", 2), 2)
            write = session.resume({"key": "1w", "target": 1})
            repeated = session.resume({"key": "1w", "target": 1})
        self.assertEqual((read["status"], read["project"], read["readonly"], read["version"]), (200, 2, True, 2))
        self.assertTrue(read["exact_resolved_identity"])
        self.assertEqual((write["status"], repeated["status"]), (200, 409))
        self.assertEqual(write["store"], repeated["store"])


if __name__ == "__main__":
    unittest.main()
