"""Run the complete fixed Conet module with real native dependencies.

The original module is imported unchanged from the distributed snapshot. The
repair is an independently constructed, two-site source change, imported as a
complete module as well. Only owned temporary policy files are changed.
"""
import asyncio
import base64
from collections import Counter, deque
from contextlib import contextmanager
import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from source_study.native_policy_store import fixtures

ART = Path(__file__).resolve().parents[2]
SOURCE = ART / "source_study/source/repair-profiles/conet"
MODULE = "src/conet/control/policy.py"
MODEL = "src/conet/control/policy_model.conf"
sys.dont_write_bytecode = True


def source_material():
    binding = json.loads((SOURCE.parent / "bindings.json").read_text())["conet"]
    for relative, expected in binding["files"].items():
        if hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("fixed Conet source identity differs: " + relative)
    original = (SOURCE / MODULE).read_text()
    candidate = original
    for name in ("add_policy", "remove_policy"):
        old = f"        return self._enforcer.{name}(subject, skill_id, action)"
        replacement = (f"        changed = self._enforcer.{name}(subject, skill_id, action)\n"
                       "        if changed is True:\n"
                       "            self._enforcer.save_policy()\n"
                       "        return changed")
        if candidate.count(old) != 1:
            raise ValueError("the independently selected source repair site is ambiguous")
        candidate = candidate.replace(old, replacement)
    candidate = ("# Derived Conet source: persist each successful policy mutation.\n"
                 "# The original Apache license and NOTICE accompany this file.\n" + candidate)
    return original, candidate, {"files": binding["files"],
        "original_module": "source_study/source/repair-profiles/conet/" + MODULE,
        "candidate_change": "Two direct mutation returns become mutation/save-if-True/return.",
        "original_module_modified": False,
        "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest()}


def dependency_record():
    expected = {}
    for line in (Path(__file__).with_name("requirements.lock")).read_text().splitlines():
        if line and not line.startswith("#"):
            name, version = line.split("==")
            expected[name] = version
    result = []
    for name, version in expected.items():
        dist = importlib.metadata.distribution(name)
        if dist.version != version:
            raise ValueError("native dependency differs from the retained lock: " + name)
        record = dist.read_text("RECORD")
        verified_files = verified_bytes = 0
        for entry in dist.files or ():
            if entry.hash is None:
                continue
            if entry.hash.mode != "sha256":
                raise ValueError("unsupported installed dependency digest: " + name)
            raw = dist.locate_file(entry).read_bytes()
            digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
            if digest != entry.hash.value:
                raise ValueError("installed dependency file differs: " + name + "/" + str(entry))
            verified_files += 1
            verified_bytes += len(raw)
        if not verified_files:
            raise ValueError("native dependency has no installed content identity: " + name)
        result.append({"distribution": name, "installed_version": version,
                       "verified_installed_files": verified_files, "verified_installed_bytes": verified_bytes,
                       "installed_record_sha256": hashlib.sha256((record or "").encode()).hexdigest()})
    return {"packages": result, "complete_module_import": True,
            "source_declaration": "casbin>=1.36,<2.0; python-jose[cryptography]>=3.3,<4.0",
            "no_replaced_or_stubbed_imports": True}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("unable to load the fixed complete source module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def modules(candidate_output=None):
    original, candidate, manifest = source_material()
    if candidate_output is not None:
        candidate_output.mkdir(parents=True, exist_ok=False)
        (candidate_output / "policy.py").write_text(candidate)
        (candidate_output / "policy_model.conf").write_bytes((SOURCE / MODEL).read_bytes())
        for name in ("LICENSE", "NOTICE"):
            (candidate_output / name).write_bytes((SOURCE / name).read_bytes())
    with TemporaryDirectory(prefix="authrefine-conet-source-") as directory:
        path = Path(directory)
        (path / "policy.py").write_text(candidate)
        (path / "policy_model.conf").write_bytes((SOURCE / MODEL).read_bytes())
        selected = {"original": load_module(SOURCE / MODULE, "authrefine_conet_original"),
                    "repaired": load_module(path / "policy.py", "authrefine_conet_repaired")}
        yield selected, manifest


def file_text(mask):
    return "\n".join("p, " + ", ".join(row) for i, row in enumerate(fixtures.ROWS) if mask & (1 << i))


def mask_for(rows):
    tuples = [tuple(row) for row in rows]
    if len(tuples) != len(set(tuples)) or any(row not in fixtures.ROWS for row in tuples):
        raise ValueError("native policy has a duplicate or unobserved row")
    return sum(1 << fixtures.ROWS.index(row) for row in tuples)


class Session:
    def __init__(self, module, path, mask):
        self.module, self.path, self.initial = module, Path(path), mask
        self.calls = Counter()
        self.reset()

    def construct(self):
        self.calls["PolicyEngine.__init__"] += 1
        return self.module.PolicyEngine("authrefine-owned-conet-secret", str(self.path))

    def reset(self):
        self.path.write_text(file_text(self.initial))
        self.engine = self.construct()
        actual = self.snapshot()
        if actual["state"] != fixtures.initial_state(self.initial):
            raise ValueError("native constructor did not load the owned initial file")

    def snapshot(self):
        memory = [list(row) for row in self.engine.list_policy_rules()]
        self.calls["PolicyEngine.list_policy_rules"] += 1
        text = self.path.read_text()
        parsed = list(csv.reader(io.StringIO(text), skipinitialspace=True))
        if any(len(row) != 4 or row[0] != "p" for row in parsed):
            raise ValueError("native policy file has an unobserved record")
        disk = [row[1:] for row in parsed]
        return {"memory_rows": memory, "disk_rows": disk, "disk_text": text,
                "state": mask_for(disk) | (mask_for(memory) << len(fixtures.ROWS))}

    def step(self, request):
        if request not in fixtures.alphabet():
            raise ValueError("request is outside the declared finite store interface")
        before = self.snapshot()
        row = fixtures.ROWS[fixtures.resources().index(request[1])]
        action = request[2]
        if action == "restart":
            self.engine = self.construct()
            value, method = True, "PolicyEngine.__init__"
            native_return = {"kind": "instance", "class": type(self.engine).__name__}
        else:
            method = {"add": "add_policy_rule", "remove": "remove_policy_rule", "authorize": "authorize"}[action]
            function = getattr(self.engine, method)
            value = asyncio.run(function(*row)) if action == "authorize" else function(*row)
            self.calls["PolicyEngine." + method] += 1
            method = "PolicyEngine." + method
            native_return = {"kind": "boolean", "value": value}
        if type(value) is not bool:
            raise ValueError("complete source method returned a non-Boolean result")
        return {"request": list(request), "native_arguments": list(row) if action != "restart" else None,
                "source_method": method, "interface_result": value, "native_return": native_return,
                "decision": "allow" if value else "deny",
                "before": before, "after": self.snapshot()}


def graph(module, mask):
    requests = fixtures.alphabet()
    with TemporaryDirectory(prefix="authrefine-conet-policy-") as directory:
        session = Session(module, Path(directory) / "policy.csv", mask)
        # Preserve the actual ordered stores as target nodes. Two native row
        # orders may have the same six-bit reference observation; they are not
        # silently collapsed before their outgoing operations are executed.
        def key(snapshot):
            return (tuple(tuple(row) for row in snapshot["memory_rows"]),
                    tuple(tuple(row) for row in snapshot["disk_rows"]), snapshot["disk_text"])
        initial = session.snapshot()
        paths, waiting, states, edges, table = {0: []}, deque([0]), [initial], [], {}
        positions = {key(initial): 0}
        while waiting:
            state = waiting.popleft()
            outgoing = []
            for index, request in enumerate(requests):
                session.reset()
                prefix = [session.step(requests[i]) for i in paths[state]]
                if session.snapshot() != states[state]:
                    raise ValueError("actual source prefix does not reach the recorded state")
                observed = session.step(request)
                following_key = key(observed["after"])
                if following_key not in positions:
                    successor = len(states)
                    positions[following_key] = successor
                    paths[successor] = paths[state] + [index]
                    states.append(observed["after"])
                    waiting.append(successor)
                following = positions[following_key]
                edges.append({"from_state": state, "input_index": index, "prefix": paths[state],
                              "prefix_observations": prefix, "observation": observed})
                outgoing.append([observed["decision"], following])
            table[state] = outgoing
        calls = dict(session.calls)
    machine = {"state_names": fixtures.state_names(), "alphabet": requests,
        "observations": [snapshot["state"] for snapshot in states],
        "initial": 0, "transitions": [table[state] for state in range(len(states))]}
    return {"initial_mask": mask, "states": states,
            "paths": [{"state": state, "indices": paths[state]} for state in range(len(states))],
            "edges": edges, "machine": machine, "source_method_calls": calls,
            "measured_cells": len(edges), "prefix_operations": sum(len(row["prefix"]) for row in edges)}


def replay_words(module, mask, words):
    records = []
    with TemporaryDirectory(prefix="authrefine-conet-replay-") as directory:
        session = Session(module, Path(directory) / "policy.csv", mask)
        for word in words:
            session.reset()
            observed = [session.step(fixtures.alphabet()[i]) for i in word]
            records.append({"indices": list(word), "observations": observed})
        counts = dict(session.calls)
    return records, counts
