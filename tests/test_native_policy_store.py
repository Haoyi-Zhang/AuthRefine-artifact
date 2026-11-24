"""Conet full-module execution, provenance and fixed-correspondence records."""
from copy import deepcopy
import importlib.metadata
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ART = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ART / "src"))
from source_study.native_policy_store import fixtures, native, oracle, summarize
from source_study.native_policy_store.run import check_graph, compare_previous_table


class NativePolicyStoreContractTests(unittest.TestCase):
    def test_correspondences_are_bijections_shared_by_all_three_methods(self):
        family = fixtures.family()
        self.assertEqual(len(family), 6)
        self.assertTrue(all(set(binding.values()) == set(fixtures.resources()) for binding in family))
        self.assertEqual(len({tuple(binding.items()) for binding in family}), 6)
        policy = fixtures.contract(3)
        for alias in fixtures.aliases():
            selected = [rule for rule in policy["rules"] if any(atom.get("alias") == alias for atom in rule["guard"])]
            self.assertEqual(len(selected), 3)

    def test_complete_repair_preserves_module_except_two_mutation_returns(self):
        original, candidate, manifest = native.source_material()
        self.assertNotIn("save_policy()", original)
        self.assertEqual(candidate.count("self._enforcer.save_policy()"), 2)
        self.assertIn("from jose import JWTError, jwt", candidate)
        self.assertIn("async def authorize", candidate)
        self.assertFalse(manifest["original_module_modified"])
        reverted = "\n".join(candidate.splitlines()[2:])
        for method in ("add_policy", "remove_policy"):
            block = (f"        changed = self._enforcer.{method}(subject, skill_id, action)\n"
                     "        if changed is True:\n"
                     "            self._enforcer.save_policy()\n"
                     "        return changed")
            reverted = reverted.replace(block, f"        return self._enforcer.{method}(subject, skill_id, action)")
        self.assertEqual(reverted, original.rstrip("\n"))

    def test_changed_upstream_source_is_rejected_before_import(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "conet"
            root.mkdir()
            binding = (native.SOURCE.parent / "bindings.json").read_bytes()
            (root.parent / "bindings.json").write_bytes(binding)
            for relative in (native.MODULE, native.MODEL, "pyproject.toml", "LICENSE", "NOTICE"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((native.SOURCE / relative).read_bytes())
            with (root / native.MODULE).open("a") as output:
                output.write("\n# changed input\n")
            with patch.object(native, "SOURCE", root):
                with self.assertRaisesRegex(ValueError, "source identity differs"):
                    native.source_material()

    def test_independent_set_equations_preserve_unchanged_denials(self):
        binding = fixtures.family()[0]
        empty = fixtures.initial_state(0)
        self.assertEqual(oracle.step(empty, ["api", "row-1", "remove"], binding), ("deny", empty))
        success, state = oracle.step(empty, ["api", "row-1", "add"], binding)
        self.assertEqual((success, state), ("allow", 9))
        self.assertEqual(oracle.step(state, ["api", "row-1", "add"], binding), ("deny", state))
        self.assertEqual(oracle.step(state, ["api", "row-2", "restart"], binding), ("allow", state))


class NativePolicyStoreRecordTests(unittest.TestCase):
    results = ART / "results/native-policy-store"

    def reject_record(self, name, modify, reason):
        original = summarize.read
        def altered(path):
            value = original(path)
            if path.name == name:
                value = deepcopy(value)
                modify(value)
            return value
        with patch.object(summarize, "read", side_effect=altered):
            with self.assertRaisesRegex(ValueError, reason):
                summarize.verify(self.results)

    def test_retained_scientific_payload_is_recomputed(self):
        result = summarize.verify(self.results)
        self.assertEqual(result["measured_edges"], 3072)
        self.assertEqual(result["distinct_physical_state_request_pairs"], {"original": 1536, "repaired": 192})
        self.assertEqual(result["method_binding_comparisons"], 1152)

    def test_changed_prior_source_lowering_is_rejected(self):
        graphs = summarize.read(self.results / "native-observations.json.gz")
        prior = summarize.read(ART / "source_study/data/repair-profiles.json.gz")["Conet"]
        prior["original"]["machine"]["transitions"][0][0][0] = "deny"
        with self.assertRaisesRegex(ValueError, "prior source-lowered table"):
            compare_previous_table(graphs, prior)

    def test_native_witness_binds_indices_and_carries_the_complete_store(self):
        replay = summarize.read(self.results / "native-witness-replay.json.gz")[0]
        row = next(word for word in replay["words"] if len(word["indices"]) == 3)
        binding = fixtures.family()[0]
        self.assertEqual(oracle.check_native_witness(0, binding, row["indices"], row["observations"], observe_state=False), 3)
        changed_word = list(row["indices"])
        changed_word[0] = 4
        with self.assertRaisesRegex(ValueError, "declared index"):
            oracle.check_native_witness(0, binding, changed_word, row["observations"], observe_state=False)
        invalid_word = list(row["indices"])
        invalid_word[0] = True
        with self.assertRaisesRegex(ValueError, "declared alphabet"):
            oracle.check_native_witness(0, binding, invalid_word, row["observations"], observe_state=False)
        changed_records = deepcopy(row["observations"])
        changed_records[1]["before"]["disk_text"] += "\n"
        with self.assertRaisesRegex(ValueError, "preceding complete store"):
            oracle.check_native_witness(0, binding, row["indices"], changed_records, observe_state=False)

    def test_corrupt_raw_disk_text_is_detected(self):
        def alter(rows):
            rows[0]["edges"][0]["observation"]["after"]["disk_text"] = "p, invented, row, invoke"
        self.reject_record("native-observations.json.gz", alter, "rich record")

    def test_missing_actual_prefix_is_detected(self):
        def alter(rows):
            edge = next(row for row in rows[0]["edges"] if row["prefix"])
            edge["prefix_observations"].pop()
        self.reject_record("native-observations.json.gz", alter, "prefix/cell record count")

    def test_illegal_added_mapping_is_detected(self):
        def alter(rows):
            rows[0]["family"].append({name: "row-1" for name in fixtures.aliases()})
        self.reject_record("inputs.json.gz", alter, "supplied family")

    def test_decision_only_length_is_not_the_full_observation_length(self):
        def alter(rows):
            rows[0]["decision_only"][0]["length"] = 1
        self.reject_record("profiles.json.gz", alter, "decision-only profile")

    def test_corrupt_native_replay_is_detected(self):
        def alter(rows):
            rows[0]["words"][0]["observations"][0]["after"]["memory_rows"].clear()
        self.reject_record("native-witness-replay.json.gz", alter, "rich record")


def native_available():
    try:
        return importlib.metadata.version("casbin") == "1.43.0" and importlib.metadata.version("python-jose") == "3.5.0"
    except importlib.metadata.PackageNotFoundError:
        return False


@unittest.skipUnless(native_available(), "install source_study/native_policy_store/requirements.lock")
class NativeConetExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native.dependency_record()
        cls.context = native.modules()
        cls.modules, _ = cls.context.__enter__()
        cls.graphs = {arm: {"id": f"{arm}-initial-0", "arm": arm, **native.graph(module, 0)}
                      for arm, module in cls.modules.items()}

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def test_actual_original_and_repaired_modules_close_the_reachable_graph(self):
        for arm, graph in self.graphs.items():
            checked = check_graph(graph)
            self.assertEqual(checked["physical_states"], 16)
            self.assertEqual(checked["membership_states"], 8)
            self.assertEqual(checked["measured_cells"], 192)
            self.assertEqual(sum((state["state"] >> 3) == 7 for state in graph["states"]), 6)
            restarted = next(edge["observation"] for edge in graph["edges"] if edge["observation"]["request"][2] == "restart")
            self.assertEqual(restarted["native_return"], {"kind": "instance", "class": "PolicyEngine"})
            self.assertIs(restarted["interface_result"], True)

    def test_full_observation_and_boolean_only_have_different_shortest_witnesses(self):
        identity = fixtures.family()[0]
        original = self.graphs["original"]["machine"]
        complete = oracle.profile(0, original, identity)
        boolean = oracle.profile(0, original, identity, observe_state=False)
        self.assertEqual(complete["length"], 1)
        self.assertEqual(boolean["length"], 3)
        self.assertEqual([original["alphabet"][i][2] for i in boolean["indices"]], ["add", "restart", "add"])
        workflow = oracle.profile(0, original, identity, fixtures.callers()["mutation-restart-query"], observe_state=False)
        self.assertEqual(workflow["length"], 3)
        self.assertEqual([original["alphabet"][i][2] for i in workflow["indices"]], ["add", "restart", "authorize"])
        self.assertTrue(oracle.profile(0, self.graphs["repaired"]["machine"], identity)["equivalent"])

    def test_complete_fixed_family_matches_grouped_protocol_and_native_replay(self):
        from protocol_grouped import support_indexed_protocol_profile
        from source_study.native_policy_store.run import semantic_rows
        family, policy = fixtures.family(), fixtures.contract(0)
        for arm, graph in self.graphs.items():
            protocol = fixtures.callers()["one-mutation"]
            expected = [oracle.profile(0, graph["machine"], binding, protocol) for binding in family]
            got = support_indexed_protocol_profile(policy, graph["machine"], protocol, family=family)
            self.assertEqual(semantic_rows(got), expected)
            words = sorted({tuple(row["indices"]) for row in expected if not row["equivalent"]})
            records, _ = native.replay_words(self.modules[arm], 0, words)
            observed = {tuple(row["indices"]): row["observations"] for row in records}
            for row in expected:
                if not row["equivalent"]:
                    oracle.check_native_witness(0, row["binding"], row["indices"], observed[tuple(row["indices"])])


if __name__ == "__main__":
    unittest.main()
