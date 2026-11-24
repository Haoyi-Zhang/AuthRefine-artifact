"""Exercise the complete-family CLI's outputs, bounds and atomic failure path."""
import json
from importlib.util import find_spec
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ARTIFACT = Path(__file__).resolve().parents[1]
CLI = ARTIFACT / "src/profile.py"
EXPORT = ARTIFACT / "source_study/stateful_sequence/export_profile_inputs.py"
sys.path.insert(0, str(ARTIFACT / "src"))
from cases import width_case
from compiler import compile_policy
from policy import output


def invoke(script, *arguments):
    run = subprocess.run([sys.executable, "-B", str(script), *map(str, arguments)],
                         capture_output=True, text=True, timeout=20,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return run, json.loads(run.stdout)


class ProfileCLITests(unittest.TestCase):
    def write_inputs(self, directory):
        policy = width_case(2)
        machine = compile_policy(policy)
        output(directory / "policy.json", policy)
        output(directory / "machine.json", machine)
        return directory / "policy.json", directory / "machine.json"

    def test_export_and_all_engines_preserve_complete_native_family_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            inputs = directory / "inputs"
            done, receipt = invoke(EXPORT, "--output", inputs)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertTrue(receipt["completed"])
            self.assertEqual(set(receipt["files"]), {"policy.json", "machine.json", "control-machine.json",
                                                       "family.json", "protocol.json", "provenance.json"})
            results = {}
            engines = ["indexed", "scan", "protocol", "protocol-indexed",
                       "symbolic", "protocol-symbolic"]
            if find_spec("dd") is not None:
                engines.extend(["symbolic-cudd", "protocol-symbolic-cudd"])
            for engine in engines:
                destination = directory / (engine + ".json")
                arguments = [inputs / "policy.json", inputs / "machine.json", destination,
                             "--family", inputs / "family.json", "--engine", engine]
                if engine.startswith("protocol"):
                    arguments.extend(["--protocol", inputs / "protocol.json"])
                done, receipt = invoke(CLI, *arguments)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertTrue(receipt["completed"])
                results[engine] = json.loads(destination.read_text())
                self.assertEqual(results[engine]["engine"], engine)
                self.assertEqual(results[engine]["bindings"], 2)
                self.assertEqual(results[engine]["strata"], {"infinity": 1, "2": 1})
                self.assertEqual([row["binding"] for row in results[engine]["profiles"]],
                                 json.loads((inputs / "family.json").read_text()))
            self.assertEqual(results["indexed"]["profiles"], results["scan"]["profiles"])
            self.assertEqual(results["protocol-indexed"]["profiles"], results["protocol"]["profiles"])
            fields = ("binding", "equivalent", "length", "indices", "trace")
            for engine in engines:
                reference = results["protocol"] if engine.startswith("protocol") else results["scan"]
                self.assertEqual([{k: row[k] for k in fields} for row in results[engine]["profiles"]],
                                 [{k: row[k] for k in fields} for row in reference["profiles"]])
            destination = directory / "introduced-control.json"
            done, receipt = invoke(CLI, inputs / "policy.json", inputs / "control-machine.json", destination,
                                   "--family", inputs / "family.json")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(json.loads(destination.read_text())["strata"], {"1": 2})
            # Leaving out the supplied two-permutation family really means the
            # declaration's larger Cartesian family; it is not silently reused.
            destination = directory / "cartesian.json"
            done, _ = invoke(CLI, inputs / "policy.json", inputs / "machine.json", destination)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(json.loads(destination.read_text())["bindings"], 4)

    def test_protocol_argument_is_required_only_by_the_protocol_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            policy, machine = self.write_inputs(directory)
            protocol = directory / "protocol.json"
            output(protocol, {"initial": 0, "transitions": [[0, 0]]})
            for suffix, options in enumerate((["--engine", "protocol"],
                                               ["--engine", "protocol-indexed"],
                                               ["--engine", "protocol-symbolic"],
                                               ["--engine", "protocol-symbolic-cudd"],
                                               ["--protocol", str(protocol)],
                                               ["--engine", "scan", "--protocol", str(protocol)],
                                               ["--engine", "symbolic", "--protocol", str(protocol)])):
                destination = directory / f"invalid-{suffix}.json"
                done, receipt = invoke(CLI, policy, machine, destination, *options)
                self.assertEqual(done.returncode, 1)
                self.assertEqual(receipt["kind"], "invalid")
                self.assertFalse(destination.exists())

    def test_budget_family_limit_and_missing_enabled_edge_write_no_partial_family(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            policy, machine = self.write_inputs(directory)
            for name, options in (("budget", ["--budget", "0"]),
                                  ("family", ["--family-limit", "1"])):
                destination = directory / (name + ".json")
                before = set(directory.iterdir())
                done, receipt = invoke(CLI, policy, machine, destination, *options)
                self.assertEqual(done.returncode, 2)
                self.assertEqual(receipt["kind"], "inconclusive")
                self.assertFalse(destination.exists())
                self.assertEqual(set(directory.iterdir()), before)
            partial = json.loads(machine.read_text())
            partial["transitions"][partial["initial"]][0] = None
            partial_path, protocol = directory / "partial.json", directory / "protocol.json"
            output(partial_path, partial)
            output(protocol, {"initial": 0, "transitions": [[0, 0]]})
            for engine in ("protocol", "protocol-indexed", "protocol-symbolic", "protocol-symbolic-cudd"):
                destination = directory / ("missing-" + engine + ".json")
                done, receipt = invoke(CLI, policy, partial_path, destination,
                                       "--engine", engine, "--protocol", protocol)
                self.assertEqual(done.returncode, 2)
                self.assertEqual(receipt["kind"], "inconclusive")
                self.assertFalse(destination.exists())

    def test_symbolic_limits_are_enforced_without_partial_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            policy, machine = self.write_inputs(directory)
            for number, options in enumerate((
                ["--engine", "symbolic", "--symbolic-operations", "0"],
                ["--engine", "symbolic", "--node-limit", "1"],
                ["--engine", "symbolic-cudd", "--symbolic-operations", "0"],
            )):
                destination = directory / ("bounded-" + str(number) + ".json")
                done, receipt = invoke(CLI, policy, machine, destination, *options)
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertEqual(receipt["kind"], "inconclusive")
                self.assertFalse(destination.exists())
            destination = directory / "invalid-limit.json"
            done, receipt = invoke(CLI, policy, machine, destination, "--node-limit", "100")
            self.assertEqual(done.returncode, 1)
            self.assertEqual(receipt["kind"], "invalid")
            self.assertFalse(destination.exists())

    def test_existing_destination_and_inputs_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            policy, machine = self.write_inputs(directory)
            destination = directory / "existing.json"
            destination.write_bytes(b"preserve this existing result\n")
            before = {path.name: path.read_bytes() for path in directory.iterdir()}
            done, receipt = invoke(CLI, policy, machine, destination)
            self.assertEqual(done.returncode, 1)
            self.assertEqual(receipt["kind"], "invalid")
            self.assertEqual({path.name: path.read_bytes() for path in directory.iterdir()}, before)

    def test_duplicate_json_keys_and_invalid_family_envelopes_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            policy, machine = self.write_inputs(directory)
            duplicate = directory / "duplicate.json"
            duplicate.write_text('{"initial":0,"initial":0}\n')
            destination = directory / "duplicate-result.json"
            done, receipt = invoke(CLI, policy, duplicate, destination)
            self.assertEqual(done.returncode, 1)
            self.assertIn("duplicate", receipt["reason"])
            self.assertFalse(destination.exists())
            family = directory / "family.json"
            output(family, {"x00": "r", "x01": "r"})
            destination = directory / "family-result.json"
            done, receipt = invoke(CLI, policy, machine, destination, "--family", family)
            self.assertEqual(done.returncode, 1)
            self.assertIn("JSON array", receipt["reason"])
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
