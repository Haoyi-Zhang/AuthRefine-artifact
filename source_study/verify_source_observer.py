"""Recompute and reconcile a complete independent source-observer acquisition.

The command reads a retained directory and leaves its seven files unchanged.
It executes the pinned selected CPython functions on owned SQLite records, then
the production comparison and eight source controls. It does not import an
application module, start a server, execute Django, or repeat timing experiments.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source_study.observation_evidence import integer, object_fields, require, typed_equal
from source_study.independent_observer.evidence import COHORTS, validate_observations
from source_study.independent_observer.fixtures import all_fixtures, read_fixtures, resume_symbols

ART = Path(__file__).resolve().parents[1]
OBSERVER = ART / "source_study/independent_observer"
SCIENCE = ("fixtures.json", "source-manifest.json", "direct-observations.json", "comparisons.json", "source-controls.json")
OUTPUTS = (*SCIENCE, "summary.json")
PRODUCTION_SOURCES = (
    "adaptation_study/owner_insert.py", "adaptation_study/profiles.py",
    "source_study/code/credential_flow_contexts.py", "source_study/code/credential_flow_ir.py",
    "source_study/code/credential_flow_native.py", "source_study/code/finite_observation_diagnosis.py",
    "source_study/code/pretix_event_profile.py", "source_study/observation_evidence.py",
    "src/baseline_checks.py", "src/cases.py", "src/checker.py", "src/compiler.py", "src/effect_slice.py",
    "src/extensions.py", "src/language.py", "src/native_casbin.py", "src/native_runtime.py", "src/oracle.py",
    "src/policy_slice.py", "src/public_inputs.py", "src/source_bindings.py", "src/source_family.py",
    "src/symbolic.py", "src/symbolic_profile.py", "src/token_roles.py",
)

# Acquisitions made before the Python-3.13 AST compatibility layer contain the
# original production set. Current acquisitions additionally execute this
# package initializer, whose import hook changes only the two declared modules'
# local AST representation and does not load either target eagerly.
OPTIONAL_COMPATIBILITY_SOURCES = ("source_study/__init__.py",)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "retained JSON", "duplicate object key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("retained JSON: nonfinite number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def read(path):
    return decode(Path(path).read_bytes())


def as_record(value):
    # JSON object keys (including the explicit alphabet-index bijection) are
    # compared in their recorded representation, without converting values.
    return decode(json.dumps(value, sort_keys=True, allow_nan=False))


def source_identities(runtime):
    acquisition = {path.name: sha(path) for path in sorted(OBSERVER.glob("*.py"))}
    require(typed_equal(runtime["source_sha256"], acquisition), "runtime.source_sha256",
            "complete acquisition-module identities differ")
    base = {name: sha(ART / name) for name in PRODUCTION_SOURCES}
    with_compatibility = {
        **base,
        **{name: sha(ART / name) for name in OPTIONAL_COMPATIBILITY_SOURCES},
    }
    recorded = runtime["production_module_sha256"]
    # Preserve verification of the pre-fix acquisition while requiring a fresh
    # acquisition to name exactly the base modules plus the declared shim. No
    # unknown extra module, missing module, or stale shim hash is accepted.
    if typed_equal(recorded, base):
        production = base
    else:
        require(typed_equal(recorded, with_compatibility), "runtime.production_module_sha256",
                "complete production/shared-module identities differ")
        production = with_compatibility
    return acquisition, production


def verify_records(directory):
    directory = Path(directory).resolve()
    require(directory.is_dir(), "source-observer directory", "directory does not exist")
    require({path.name for path in directory.iterdir()} == {*OUTPUTS, "runtime.json"},
            "source-observer directory", "complete seven-file acquisition required")
    for name in (*OUTPUTS, "runtime.json"):
        require((directory / name).is_file() and not (directory / name).is_symlink(),
                "source-observer directory", "plain evidence files required")
    runtime = read(directory / "runtime.json")
    object_fields(runtime, ("python", "implementation", "platform", "sqlite", "direct_stage_seconds",
                            "all_stages_seconds", "source_sha256", "production_module_sha256",
                            "output_sha256", "exit_status"), "runtime")
    integer(runtime["exit_status"], "runtime.exit_status")
    require(runtime["exit_status"] == 0, "runtime.exit_status", "successful acquisition required")
    for name in ("python", "implementation", "platform", "sqlite"):
        require(type(runtime[name]) is str and bool(runtime[name]), "runtime." + name, "runtime description required")
    require(runtime["implementation"] == "CPython", "runtime.implementation", "CPython acquisition required")
    for name in ("direct_stage_seconds", "all_stages_seconds"):
        value = runtime[name]
        require(type(value) in (float, int) and math.isfinite(value) and value >= 0,
                "runtime." + name, "finite nonnegative recorded duration required")
    require(runtime["all_stages_seconds"] >= runtime["direct_stage_seconds"], "runtime", "stage durations are inconsistent")
    sources = source_identities(runtime)
    hashes = {name: sha(directory / name) for name in OUTPUTS}
    require(typed_equal(runtime["output_sha256"], hashes), "runtime.output_sha256",
            "complete output identities differ")
    records = {name: read(directory / name) for name in OUTPUTS}
    require(typed_equal(records["summary.json"]["files_sha256"], {name: hashes[name] for name in SCIENCE}),
            "summary.files_sha256", "complete scientific-file identities differ")
    require(typed_equal(records["fixtures.json"], as_record(all_fixtures())), "fixtures", "current declared fixture domain differs")
    validate_observations(records["direct-observations.json"])
    return records, runtime, hashes, sources


def recompute_summary(direct, comparison, controls, hashes):
    """Derive each reported denominator and outcome from the admitted records."""
    counts = validate_observations(direct)
    graph = [row for profile in direct["healthchecks_resume"] for row in profile["rows"]]
    statuses = lambda rows: dict(sorted(Counter(str(row["observation"]["status"]) for row in rows).items()))
    decisions = lambda rows, key: dict(sorted(Counter(str(row["observation"][key]).lower() for row in rows).items()))
    control_counts = []
    for control in controls:
        rows = control["rows"]
        response = "allow" if control["control"].startswith("pretix_") else "allowed" if control["control"].startswith("wger_") else "status"
        changed, response_count = 0, 0
        for row in rows:
            before, after = row["baseline"], row["modified"]
            differs = not typed_equal(before, after)
            response_differs = not typed_equal(before[response], after[response])
            fields = sorted(key for key in set(before) | set(after)
                            if key not in before or key not in after or not typed_equal(before[key], after[key]))
            require(differs and typed_equal(row["response_changed"], response_differs)
                    and typed_equal(row["differing_fields"], fields), "source controls", "recorded difference classification differs")
            changed += differs
            response_count += response_differs
        tested = (counts["healthchecks_reads"] if control["control"].startswith("read_") else
                  counts["healthchecks_resume"] if control["control"].startswith("resume_") else
                  counts["pretix"] if control["control"].startswith("pretix_") else counts["wger_owner_insert"])
        row_counts = {"control": control["control"], "tested_inputs": tested,
                      "changed_observations": changed, "response_differences": response_count,
                      "field_only_differences": changed - response_count}
        require(typed_equal({key: value for key, value in control.items() if key not in ("rows", "source")}, row_counts),
                "source controls", "control totals differ")
        control_counts.append(row_counts)
    read_fields = ["status", "project", "readonly", "version", "exact_resolved_identity",
                   "manager_returns", "serializers", "effects"]
    return {
        "scope": "New CPython execution of 13 selected source functions on explicit finite stand-ins; separate fresh production-IR comparison",
        "historical_272_direct_pairs_recovered": False, "new_independent_applications": 0,
        "full_application_or_framework_execution": False, "native_Django_bubblewrap_replay_invoked": False,
        "wger_historical_date_validation_reconstructed": False,
        "profile_counts": {"healthchecks_reads": counts["healthchecks_reads"], "healthchecks_resume_edges": counts["healthchecks_resume"],
                           "pretix_active_token_event": counts["pretix"], "wger_guarded_owner_insert": counts["wger_owner_insert"]},
        "paired_observations": sum(len(comparison[cohort]) for cohort in COHORTS),
        "comparison_disagreements": sum(row["agrees"] is not True for cohort in COHORTS for row in comparison[cohort]),
        "observation_admission": {"complete_fixture_sets": counts, "unique_fixture_ids_and_state_input_pairs": True,
                                  "prefix_observations_checked_against_graph": True, "observation_value_and_type_equality": True,
                                  "boolean_agreement_required": True},
        "fields_compared": {"healthchecks_reads": read_fields,
                            "healthchecks_resume": read_fields + ["before", "after", "store", "store_changed", "event_delta",
                                                                  "store_invariant", "all prefix observations"],
                            "pretix": ["allow", "event", "organizer", "permissions", "exact_event_identity"],
                            "wger_owner_insert": ["allowed", "persisted rows", "save-call count", "exact request user identity"]},
        "pretix_direct_only_fields": ["raw query filters", "access/grant handoff arguments and identities"],
        "source_control_comparison": "complete baseline versus modified CPython observations; response means HTTP status or permission/entry decision",
        "healthchecks_read_statuses": statuses(direct["healthchecks_reads"]),
        "healthchecks_read_body_only_GET_cases": sum(case["carrier"] == "body" and case["request"]["method"] == "GET" for case in read_fixtures()),
        "healthchecks_read_body_only_contract": "authorize_read uses headers; all body-only GET inputs stop before credential lookup",
        "healthchecks_resume_statuses": statuses(graph),
        "healthchecks_resume_states_per_form": [len(profile["paths"]) for profile in direct["healthchecks_resume"]],
        "healthchecks_resume_symbols_per_state": len(resume_symbols()),
        "healthchecks_resume_prefix_step_executions": sum(len(row["prefix_observations"]) for row in graph),
        "healthchecks_store_invariant_checks": sum(row["observation"]["store_invariant"] for row in graph),
        "pretix_decisions": decisions(direct["pretix"], "allow"),
        "wger_guard_decisions": decisions(direct["wger_owner_insert"], "allowed"),
        "stateful_binding_families": [{"form": profile["form"], "bindings": len(profile["diagnosis"]["profiles"]),
                                      "matching_bindings": profile["diagnosis"]["matching_bindings"],
                                      "strata": profile["diagnosis"]["strata"],
                                      "cpython_witness_replays": len(profile["cpython_witness_replays"])}
                                     for profile in comparison["stateful_diagnosis"]],
        "source_mutations": control_counts,
        "source_mutation_tests": sum(row["tested_inputs"] for row in control_counts),
        "source_mutation_changed_observations": sum(row["changed_observations"] for row in control_counts),
        "source_mutation_response_differences": sum(row["response_differences"] for row in control_counts),
        "source_mutation_field_only_differences": sum(row["field_only_differences"] for row in control_counts),
        "healthchecks_primitive_contract_shared_between_executors": True,
        "healthchecks_primitive_implementation_shared_between_executors": False,
        "healthchecks_store_implementations": {"cpython": "owned SQLite tables", "production_IR": "separate in-memory typed records and event list"},
        "source_control_flow_execution_independent_of_production_interpreter": True,
        "production_imports_before_direct_evidence_freeze": [],
        "files_sha256": {name: hashes[name] for name in SCIENCE},
    }


def verify(directory):
    records, runtime, hashes, sources = verify_records(directory)
    from source_study.independent_observer.observer import baseline, control_observations
    # Recollect direct-only fields as well as those compared with production.
    # The checker never calls the acquisition writer and never alters records.
    direct = baseline()
    manifest = direct.pop("source_manifest")
    require(typed_equal(as_record(manifest), records["source-manifest.json"]), "source manifest", "current selected bodies differ")
    require(typed_equal(as_record(direct), records["direct-observations.json"]), "direct observations",
            "fresh selected-function execution differs")
    from source_study.independent_observer.compare import compare
    comparison = as_record(compare(direct))
    require(typed_equal(comparison, records["comparisons.json"]), "comparisons", "fresh complete production comparison differs")
    controls = as_record(control_observations(direct))
    require(typed_equal(controls, records["source-controls.json"]), "source controls", "fresh eight-control execution differs")
    summary = as_record(recompute_summary(direct, comparison, controls, hashes))
    require(typed_equal(summary, records["summary.json"]), "summary", "independently reaggregated complete summary differs")
    require(typed_equal(source_identities(runtime), sources), "source identities", "code changed during verification")
    require(typed_equal({name: sha(Path(directory) / name) for name in OUTPUTS}, hashes), "output identities",
            "evidence changed during verification")
    return {"status": "PASS", "paired_observations": summary["paired_observations"],
            "comparison_disagreements": summary["comparison_disagreements"],
            "source_mutation_tests": summary["source_mutation_tests"],
            "source_mutation_changed_observations": summary["source_mutation_changed_observations"],
            "source_mutation_response_differences": summary["source_mutation_response_differences"],
            "source_mutation_field_only_differences": summary["source_mutation_field_only_differences"],
            "complete_summary_recomputed": True, "complete_observation_value_and_type_equality": True,
            "selected_CPython_source_bodies_reexecuted": True, "application_modules_or_Django_executed": False,
            "timing_campaign_reexecuted": False, "retained_files_changed": False,
            "recorded_source_files_checked": sum(len(mapping) for mapping in sources),
            "retained_runtime_sha256": sha(Path(directory) / "runtime.json"),
            "retained_output_sha256": hashes, "verifier_sha256": sha(Path(__file__))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ART / "results/source-observer")
    parser.add_argument("--output", type=Path, help="optional new receipt outside the retained results directory")
    args = parser.parse_args(argv)
    try:
        if args.output is not None:
            require(not args.output.exists(), "receipt", "existing receipt is not overwritten")
            require(not args.output.resolve().is_relative_to(args.results.resolve()), "receipt",
                    "receipt must be outside the retained results directory")
        report = verify(args.results)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as handle:
                json.dump(report, handle, indent=2, allow_nan=False)
                handle.write("\n")
    except Exception as error:
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__, "error": str(error)}))
        return 1
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
