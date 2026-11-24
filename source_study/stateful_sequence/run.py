#!/usr/bin/env python3
"""Rebuild native session observations, independent comparison and diagnosis."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sqlite3
import sys
import time
import traceback

ART = Path(__file__).resolve().parents[2]
if str(ART) not in sys.path:
    sys.path.insert(0, str(ART))
from source_study.stateful_sequence import fixtures
from source_study.stateful_sequence.collect import acquire_native


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    timings = {}
    started = time.perf_counter()
    try:
        write(output / "fixtures.json", fixtures.document())
        from source_study.historical_h19.source import check_native
        write(output / "native-dependencies.json", check_native())
        start = time.perf_counter()
        native = asyncio.run(acquire_native())
        write(output / "native-observations.json", native)
        timings["native_acquisition_seconds"] = time.perf_counter() - start
        native_hash = digest(output / "native-observations.json")
        # Only after the actual framework/SQLite values have been frozen may
        # the independent production interpreter and finite checkers be loaded.
        from source_study.stateful_sequence.collect import acquire_interpreted
        start = time.perf_counter()
        interpreted = acquire_interpreted()
        write(output / "interpreted-observations.json", interpreted)
        timings["interpreted_acquisition_seconds"] = time.perf_counter() - start
        if native != interpreted:
            raise ValueError("native and independently interpreted session observations differ")
        from source_study.stateful_sequence.diagnose import diagnose, replay_native
        start = time.perf_counter()
        diagnosis = diagnose(native)
        write(output / "diagnosis.json", diagnosis)
        replay = asyncio.run(replay_native(diagnosis))
        write(output / "native-witness-replay.json", replay)
        timings["diagnosis_and_native_replay_seconds"] = time.perf_counter() - start
        if digest(output / "native-observations.json") != native_hash:
            raise ValueError("comparison changed frozen native records")
        summary = {
            "status": "PASS", "native_engine": "Piccolo 1.16.0 with SQLite",
            "source_application": "Piccolo API", "selected_complete_methods": 2,
            "unmodified_source_profiles": 1, "introduced_source_controls": 1,
            "baseline_reachable_states": len(native["baseline"]["states"]),
            "baseline_paired_edges": len(native["baseline"]["edges"]),
            "control_reachable_states": len(native["omit_delete"]["states"]),
            "control_paired_edges": len(native["omit_delete"]["edges"]),
            "paired_expiry_boundary_inputs": len(native["expiry_boundaries"]),
            "unmodified_paired_total": len(native["baseline"]["edges"]) + len(native["expiry_boundaries"]),
            "control_paired_total": len(native["omit_delete"]["edges"]),
            "paired_total": len(native["baseline"]["edges"]) + len(native["omit_delete"]["edges"]) + len(native["expiry_boundaries"]),
            "paired_disagreements": 0,
            "additional_prefix_operations_per_arm": sum(native[name]["prefix_steps"] for name in ("baseline", "omit_delete")),
            "source_acquisition_operations_per_arm": sum(native[name]["source_operations"] for name in ("baseline", "omit_delete")) + len(native["expiry_boundaries"]),
            "extra_native_witness_runs": len(replay),
            "extra_native_witness_operations": sum(len(row["observations"]) for row in replay),
            "supplied_bijections": 2, "baseline_matching_bijections": 1,
            "baseline_excluded_bijection_shortest_full_witness": 2,
            "baseline_excluded_bijection_shortest_selected_identity_witness": 1,
            "omit_delete_shortest_full_witness": 1,
            "omit_delete_shortest_decision_only_witness": 2,
            "initial_one_step_decisions_alone_detect_omit_delete": False,
            "richer_fields_compared": ["token_argument", "returned_user_id", "selected_record",
                                       "before_rows", "after_rows", "removed_ids", "store_changed"],
            "finite_observation": "allow/deny and two persisted-row presence bits",
            "finite_lifecycle_invariant_checked_on_every_edge_and_prefix": True,
            "full_module_and_native_orm_executed": True,
            "native_records_frozen_before_interpreter_import": True,
            "source_methods_modified_in_baseline": False,
            "clock_is_fixed_fixture": True,
            "historical_application_or_http_server_reproduced": False,
            "independent_new_upstream_defects": 0,
            "diagnostic_comparisons": ["ordinary binding profile", "support-indexed complete-family profile", "shared target/caller binding profile",
                                       "independent direct-equation product search", "shorter-word enumeration",
                                       "decision-only fixed-binding product search", "native witness replay"],
            "scope": "One pinned session-store interface; supplied correspondence hypotheses and an introduced omitted-delete control; no population prevalence claim"}
        write(output / "summary.json", summary)
        timings["wall_seconds"] = time.perf_counter() - started
        code_files = list((ART / "source_study/stateful_sequence").glob("*.py"))
        code_files += [ART / "source_study/historical_h19" / name
                       for name in ("source.py", "pins.json", "requirements.lock")]
        for module in list(sys.modules.values()):
            path = getattr(module, "__file__", None)
            if path and Path(path).is_file():
                path = Path(path).resolve()
                if path.parent == ART / "src" and path.suffix == ".py":
                    code_files.append(path)
        write(output / "runtime.json", {
            "python": platform.python_version(), "implementation": platform.python_implementation(),
            "sqlite": sqlite3.sqlite_version, "platform": platform.platform(), "timings": timings,
            "packages": {d.metadata["Name"]: d.version for d in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower())},
            "source_sha256": {str(path.relative_to(ART)): digest(path) for path in sorted(set(code_files))},
            "output_sha256": {path.name: digest(path) for path in sorted(output.glob("*.json"))},
            "timing_scope": "validation runtime, not a matched checker performance comparison"})
        print(json.dumps(summary, sort_keys=True))
    except BaseException as error:
        write(output / "failure.json", {"type": type(error).__name__, "message": str(error),
                                        "traceback": traceback.format_exc(), "timings": timings})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    run(parser.parse_args().output)
