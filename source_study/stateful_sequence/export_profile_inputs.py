#!/usr/bin/env python3
"""Export complete-family CLI inputs from retained or freshly replayed sessions.

This reads recorded native and interpreted finite tables. It does not execute
the upstream application or replace the native experiment's dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ARTIFACT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ARTIFACT / "src"))
from checker import Rejected, ensure, inspect_machine, inspect_policy, load
from language import PolicyError
from policy import output

DEFAULT_RUN = ARTIFACT / "results/native-session"


def export(run, destination):
    run, destination = Path(run), Path(destination)
    ensure(not destination.exists(), "profile-input destination already exists")
    paths = {name: run / name for name in ("diagnosis.json", "native-observations.json",
                                         "interpreted-observations.json")}
    diagnosis, native, interpreted = (load(paths[name]) for name in paths)
    policy = diagnosis["policy"]
    inspect_policy(policy)
    for name in ("baseline", "omit_delete"):
        ensure(native[name]["machine"] == interpreted[name]["machine"],
               "native and interpreted finite tables differ")
        inspect_machine(policy, native[name]["machine"])
    payloads = {
        "policy.json": policy,
        "machine.json": native["baseline"]["machine"],
        "control-machine.json": native["omit_delete"]["machine"],
        "family.json": diagnosis["supplied_family"],
        "protocol.json": diagnosis["caller_protocols"]["one_removal"],
        "provenance.json": {
            "source_files": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for name, path in paths.items()},
            "recorded_run": str(run.relative_to(ARTIFACT)) if run.is_relative_to(ARTIFACT) else run.name,
            "control": "omit_delete is the declared introduced source control, not an upstream vulnerability",
            "scope": "Export of recorded finite tables and independently supplied fixed family; no application execution during export.",
        },
    }
    destination.mkdir(parents=True, exist_ok=False)
    written = []
    try:
        for name, value in payloads.items():
            path = destination / name
            output(path, value)
            written.append(path)
    except BaseException:
        # Remove only our own completed files if this multi-file export fails.
        for path in written:
            path.unlink()
        try:
            destination.rmdir()
        except OSError:
            pass
        raise
    return {"completed": True, "directory": str(destination), "files": list(payloads)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN,
                        help="native session-study output directory; default is the retained native session dataset")
    parser.add_argument("--output", required=True, type=Path, help="new input export directory")
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.run, args.output)))
        return 0
    except (PolicyError, Rejected, ValueError, TypeError, KeyError, OverflowError,
            RecursionError, OSError) as error:
        inconclusive = ((isinstance(error, PolicyError) and error.category == "LIMIT")
                        or (isinstance(error, Rejected) and error.kind == "inconclusive"))
        print(json.dumps({"completed": False, "kind": "inconclusive" if inconclusive else "invalid",
                          "reason": str(error)}))
        return 2 if inconclusive else 1


if __name__ == "__main__":
    raise SystemExit(main())
