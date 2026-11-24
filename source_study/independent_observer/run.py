"""Reconstruct the closed-function observations and preserve their evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import sys
import time
import traceback

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from source_study.independent_observer.fixtures import all_fixtures
    from source_study.independent_observer.observer import baseline, control_observations
    from source_study.independent_observer.evidence import validate_observations
else:
    from .fixtures import all_fixtures
    from .observer import baseline, control_observations
    from .evidence import validate_observations


def write(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(raw)
    return hashlib.sha256(raw).hexdigest()


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    hashes = {}
    try:
        hashes["fixtures.json"] = write(output / "fixtures.json", all_fixtures())
        direct = baseline()
        hashes["source-manifest.json"] = write(output / "source-manifest.json", direct.pop("source_manifest"))
        admitted_counts = validate_observations(direct)
        # Freeze the direct observation bytes before importing any production
        # evaluator. Later stages consume them; they cannot generate the raw run.
        hashes["direct-observations.json"] = write(output / "direct-observations.json", direct)
        raw_stage_seconds = time.monotonic() - started
        premature = sorted(k for k in sys.modules if k in ("credential_flow_ir", "effect_slice", "profiles", "pretix_event_profile", "owner_insert"))
        if premature:
            raise ValueError("production evaluator loaded before raw evidence was frozen: " + repr(premature))
        print("Direct observations frozen; starting the separate production comparison.", flush=True)
        from source_study.independent_observer.compare import compare
        comparison = compare(direct)
        hashes["comparisons.json"] = write(output / "comparisons.json", comparison)
        controls = control_observations(direct)
        hashes["source-controls.json"] = write(output / "source-controls.json", controls)
        rows = [r for p in direct["healthchecks_resume"] for r in p["rows"]]
        status = lambda entries: dict(sorted(Counter(r["observation"]["status"] for r in entries).items()))
        summary = {
            "scope": "New CPython execution of 13 selected source functions on explicit finite stand-ins; separate fresh production-IR comparison",
            "historical_272_direct_pairs_recovered": False,
            "new_independent_applications": 0,
            "full_application_or_framework_execution": False,
            "native_Django_bubblewrap_replay_invoked": False,
            "wger_historical_date_validation_reconstructed": False,
            "profile_counts": {"healthchecks_reads": len(direct["healthchecks_reads"]), "healthchecks_resume_edges": len(rows),
                               "pretix_active_token_event": len(direct["pretix"]), "wger_guarded_owner_insert": len(direct["wger_owner_insert"])},
            "paired_observations": sum(len(comparison[k]) for k in ("healthchecks_reads", "healthchecks_resume", "pretix", "wger_owner_insert")),
            "comparison_disagreements": sum(not r["agrees"] for k in ("healthchecks_reads", "healthchecks_resume", "pretix", "wger_owner_insert") for r in comparison[k]),
            "observation_admission": {"complete_fixture_sets": admitted_counts,
                                      "unique_fixture_ids_and_state_input_pairs": True,
                                      "prefix_observations_checked_against_graph": True,
                                      "observation_value_and_type_equality": True,
                                      "boolean_agreement_required": True},
            "fields_compared": {
                "healthchecks_reads": ["status", "project", "readonly", "version", "exact_resolved_identity",
                                       "manager_returns", "serializers", "effects"],
                "healthchecks_resume": ["status", "project", "readonly", "version", "exact_resolved_identity",
                                        "manager_returns", "serializers", "effects", "before", "after", "store",
                                        "store_changed", "event_delta", "store_invariant", "all prefix observations"],
                "pretix": ["allow", "event", "organizer", "permissions", "exact_event_identity"],
                "wger_owner_insert": ["allowed", "persisted rows", "save-call count", "exact request user identity"],
            },
            "pretix_direct_only_fields": ["raw query filters", "access/grant handoff arguments and identities"],
            "source_control_comparison": "complete baseline versus modified CPython observations; response means HTTP status or permission/entry decision",
            "healthchecks_read_statuses": status(direct["healthchecks_reads"]),
            "healthchecks_read_body_only_GET_cases": 240,
            "healthchecks_read_body_only_contract": "authorize_read uses headers; all body-only GET inputs stop before credential lookup",
            "healthchecks_resume_statuses": status(rows),
            "healthchecks_resume_states_per_form": [len(p["paths"]) for p in direct["healthchecks_resume"]],
            "healthchecks_resume_symbols_per_state": 28,
            "healthchecks_resume_prefix_step_executions": sum(len(r["prefix_observations"]) for r in rows),
            "healthchecks_store_invariant_checks": sum(r["observation"]["store_invariant"] for r in rows),
            "pretix_decisions": dict(sorted(Counter(str(r["observation"]["allow"]).lower() for r in direct["pretix"]).items())),
            "wger_guard_decisions": dict(sorted(Counter(str(r["observation"]["allowed"]).lower() for r in direct["wger_owner_insert"]).items())),
            "stateful_binding_families": [{"form": p["form"], "bindings": len(p["diagnosis"]["profiles"]),
                                          "matching_bindings": p["diagnosis"]["matching_bindings"],
                                          "strata": p["diagnosis"]["strata"],
                                          "cpython_witness_replays": len(p["cpython_witness_replays"])} for p in comparison["stateful_diagnosis"]],
            "source_mutations": [{k: v for k, v in r.items() if k not in ("rows", "source")} for r in controls],
            "source_mutation_tests": sum(r["tested_inputs"] for r in controls),
            "source_mutation_changed_observations": sum(r["changed_observations"] for r in controls),
            "source_mutation_response_differences": sum(r["response_differences"] for r in controls),
            "source_mutation_field_only_differences": sum(r["field_only_differences"] for r in controls),
            "healthchecks_primitive_contract_shared_between_executors": True,
            "healthchecks_primitive_implementation_shared_between_executors": False,
            "healthchecks_store_implementations": {"cpython": "owned SQLite tables", "production_IR": "separate in-memory typed records and event list"},
            "source_control_flow_execution_independent_of_production_interpreter": True,
            "production_imports_before_direct_evidence_freeze": premature,
            "files_sha256": hashes,
        }
        hashes["summary.json"] = write(output / "summary.json", summary)
        runtime = {"python": sys.version, "implementation": platform.python_implementation(),
                   "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
                   "direct_stage_seconds": raw_stage_seconds, "all_stages_seconds": time.monotonic() - started,
                   "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted(Path(__file__).resolve().parent.glob("*.py"))},
                   "production_module_sha256": {
                       str(p.relative_to(Path(__file__).resolve().parents[2])): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted({Path(m.__file__).resolve() for m in tuple(sys.modules.values())
                                        if getattr(m, "__file__", None) and str(m.__file__).endswith(".py")
                                        and Path(m.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[2])
                                        and not Path(m.__file__).resolve().is_relative_to(Path(__file__).resolve().parent)})},
                   "output_sha256": hashes, "exit_status": 0}
        write(output / "runtime.json", runtime)
        print(json.dumps({k: summary[k] for k in ("profile_counts", "paired_observations", "comparison_disagreements",
                                                 "source_mutation_tests", "source_mutation_changed_observations",
                                                 "source_mutation_response_differences", "source_mutation_field_only_differences")}, indent=2))
        return summary
    except Exception as error:
        write(output / "failure.json", {"error": str(error), "traceback": traceback.format_exc(),
                                        "written_files_sha256": hashes, "seconds": time.monotonic() - started})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new output directory; existing evidence is never overwritten")
    args = parser.parse_args()
    run(args.output)
