"""Persistence, observation scope, fixed bindings and native lifecycle replay."""
import ast
import asyncio
from copy import deepcopy
import importlib.metadata
from pathlib import Path
import unittest
from unittest.mock import patch

from source_study.stateful_sequence import source
from source_study.stateful_sequence.collect import acquire_interpreted, acquire_native
from source_study.stateful_sequence.diagnose import diagnose, replay_native
from source_study.stateful_sequence.fixtures import alphabet, expiry_inputs, rows
from source_study.stateful_sequence.interpreted import InterpretedSession


class StatefulSequenceTests(unittest.TestCase):
    def test_hash_rejects_changed_original_module(self):
        original = Path.read_bytes
        path = source.ART / source.SOURCE
        def changed(value):
            raw = original(value)
            return raw + b"\n" if value == path else raw
        with patch.object(Path, "read_bytes", changed):
            with self.assertRaisesRegex(ValueError, "identity differs"):
                source.load()

    def test_selected_bodies_are_complete(self):
        raw, _, selected, manifest = source.load()
        cls = next(n for n in ast.parse(raw).body if isinstance(n, ast.ClassDef) and n.name == "SessionsBase")
        for name, chosen in selected.items():
            original = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
            self.assertEqual([ast.dump(n, include_attributes=False) for n in original.body],
                             [ast.dump(n, include_attributes=False) for n in chosen.body])
        self.assertEqual(len(manifest["functions"]), 2)
        _, _, control, _ = source.load("omit_delete")
        self.assertNotEqual(source.ast_hash(selected["remove_session"]), source.ast_hash(control["remove_session"]))
        self.assertEqual(source.ast_hash(selected["get_user_id"]), source.ast_hash(control["get_user_id"]))

    def test_removal_persists_without_changing_other_session(self):
        session = InterpretedSession()
        before = session.invoke(["client", "credential-a", "lookup"])
        removed = session.invoke(["client", "row-a", "remove"])
        same = session.invoke(["client", "credential-a", "lookup"])
        other = session.invoke(["client", "credential-b", "lookup"])
        self.assertEqual([before["decision"], removed["decision"], same["decision"], other["decision"]],
                         ["allow", "allow", "deny", "allow"])
        self.assertEqual(removed["removed_ids"], [1])
        self.assertEqual(removed["after_rows"], [before["before_rows"][1]])
        self.assertEqual(other["returned_user_id"], 101)

    def test_complete_source_graph_is_closed(self):
        acquired = acquire_interpreted()
        graph = acquired["baseline"]
        self.assertEqual(set(graph["states"]), {0, 1, 2, 3})
        self.assertEqual(len(graph["edges"]), 40)
        self.assertEqual(graph["prefix_steps"], 40)
        self.assertEqual({(e["from_state"], e["input_index"]) for e in graph["edges"]},
                         {(state, index) for state in range(4) for index in range(10)})
        self.assertTrue(all(e["observation"]["before_state"] == e["from_state"] for e in graph["edges"]))

    def test_correspondence_depth_depends_on_declared_observation(self):
        result = diagnose(acquire_interpreted())["profiles"]["baseline"]
        self.assertEqual(result["binding_profile"]["strata"], {"infinity": 1, "2": 1})
        self.assertEqual(result["binding_profile"]["profiles"], result["support_indexed_profile"]["profiles"])
        swapped = result["independent"][1]
        self.assertEqual(swapped["full"]["length"], 2)
        self.assertEqual(swapped["full_shorter_words"], 11)
        self.assertEqual(swapped["richer_selected_identity"]["length"], 1)
        self.assertEqual(result["all_enabled_protocol"]["graph_traversals"], 1)
        self.assertEqual(result["one_removal_protocol"]["strata"], {"infinity": 1, "2": 1})

    def test_omitted_delete_is_invisible_to_initial_decisions(self):
        acquired = acquire_interpreted()
        good = [e["observation"]["decision"] for e in acquired["baseline"]["edges"] if e["from_state"] == 3]
        bad = [e["observation"]["decision"] for e in acquired["omit_delete"]["edges"]]
        self.assertEqual(good, bad)
        result = diagnose(acquired)["profiles"]["omit_delete"]
        self.assertEqual(result["binding_profile"]["strata"], {"1": 2})
        self.assertEqual([r["decision_only"]["length"] for r in result["independent"]], [2, 2])

    def test_expiry_strict_boundaries_and_persistent_renewal(self):
        session = InterpretedSession()
        for expiry, maximum, increase, decision, after_expiry in (
                (0, 120, 30, "deny", 0), (10, 0, 30, "deny", 10),
                (10, 120, 30, "allow", 40), (30, 120, 30, "allow", 30),
                (60, 120, None, "allow", 60)):
            with self.subTest(expiry=expiry, maximum=maximum, increase=increase):
                session.reset(rows(expiry, maximum))
                value = session.invoke(["client", "credential-a", "lookup"], increase)
                self.assertEqual(value["decision"], decision)
                self.assertEqual(session.store[1]["expiry_date"], after_expiry)
                self.assertEqual(session.store[1]["max_expiry_date"], maximum)

    def test_missing_token_is_idempotent_and_preserves_rows(self):
        session = InterpretedSession()
        value = session.invoke(["client", "missing", "lookup"])
        self.assertEqual((value["decision"], value["selected_record"], value["store_changed"]), ("deny", None, False))
        first = session.invoke(["client", "missing", "remove"])
        second = session.invoke(["client", "missing", "remove"])
        self.assertEqual(first, second)
        self.assertEqual((first["decision"], first["removed_ids"], first["store_changed"]), ("allow", [], False))


def has_native_dependency():
    try:
        return importlib.metadata.version("piccolo") == "1.16.0"
    except importlib.metadata.PackageNotFoundError:
        return False


@unittest.skipUnless(has_native_dependency(), "install source_study/historical_h19/requirements.lock for native Piccolo replay")
class NativeStatefulSequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = asyncio.run(acquire_native())

    def test_actual_orm_graphs_match_separate_provider(self):
        other = acquire_interpreted()
        self.assertEqual(self.native["baseline"], other["baseline"])
        self.assertEqual(self.native["omit_delete"], other["omit_delete"])

    def test_actual_orm_expiry_grid_matches_separate_provider(self):
        other = acquire_interpreted()
        self.assertEqual(len(self.native["expiry_boundaries"]), 90)
        self.assertEqual(self.native["expiry_boundaries"], other["expiry_boundaries"])

    def test_diagnostic_witnesses_reexecute_native_source(self):
        result = asyncio.run(replay_native(diagnose(self.native)))
        self.assertEqual(len(result), 6)
        self.assertEqual(sum(len(row["observations"]) for row in result), 10)
        for row in result:
            self.assertTrue(all(step["equal"] for step in row["observations"][:-1]))
            self.assertFalse(row["observations"][-1]["equal"])


if __name__ == "__main__":
    unittest.main()
