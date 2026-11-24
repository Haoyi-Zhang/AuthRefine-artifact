"""Declarative evaluation profiles used by :mod:`evaluate`.

The core profile is intentionally self-contained relative to the packaged
artifact.  Every unittest module is launched in a separate interpreter so that
module-level caches, monkey patches, or optional imports in one test file cannot
make another file pass or hang.  The portable profile expands that check to every self-contained top-level
test module.  The full profile is a strict integration
superset and therefore begins with an exact dependency/tool preflight.
"""
from __future__ import annotations

CORE_TEST_MODULES = (
    "tests.test_core",
    "tests.test_family_diagnosis",
    "tests.test_protocol_grouped",
    "tests.test_protocol_grouping_audit",
    "tests.test_protocol_theorem_audit",
    "tests.test_session_correspondence",
    "tests.test_session_initial_state",
    "tests.test_session_observation",
    "tests.test_support_overlap_audit",
    "tests.test_symbolic_family",
    "tests.test_symbolic_profile",
    "tests.test_diagnostic_example",
    "tests.test_reachable_checker",
    "tests.test_prepared_checker",
)

PORTABLE_TEST_MODULES = (
    "tests.test_adaptation_study",
    "tests.test_ast_evidence_compat",
    "tests.test_batch_dependencies",
    "tests.test_call_handoff",
    "tests.test_case_result_integrity",
    "tests.test_chained_profiles",
    "tests.test_context_fidelity",
    "tests.test_contract_handoffs",
    "tests.test_core",
    "tests.test_credential_admission_audit",
    "tests.test_diagnostic_example",
    "tests.test_effect_slice",
    "tests.test_entry_guard_prefix",
    "tests.test_explicit_effect_body",
    "tests.test_family_diagnosis",
    "tests.test_fastapi_routes",
    "tests.test_fixed_source_empirical",
    "tests.test_fixed_source_profiles",
    "tests.test_grant_binding",
    "tests.test_guard_field_types",
    "tests.test_guard_prefix",
    "tests.test_h19_boundary_repair",
    "tests.test_historical_boundary",
    "tests.test_historical_h19",
    "tests.test_independent_source_observer",
    "tests.test_maintenance_case",
    "tests.test_native_healthchecks",
    "tests.test_native_healthchecks_tree",
    "tests.test_native_policy_store",
    "tests.test_observation_evidence",
    "tests.test_observation_reuse",
    "tests.test_ordered_rules",
    "tests.test_policy_slice",
    "tests.test_prepared_checker",
    "tests.test_pretix_event_profile",
    "tests.test_profile_cli",
    "tests.test_prospective_transfer",
    "tests.test_protocol_check",
    "tests.test_protocol_grouped",
    "tests.test_protocol_grouping_audit",
    "tests.test_protocol_profile",
    "tests.test_protocol_theorem_audit",
    "tests.test_query_admission",
    "tests.test_queryset_scope",
    "tests.test_reachable_checker",
    "tests.test_record_projection",
    "tests.test_reference_completion",
    "tests.test_reference_snapshots",
    "tests.test_reference_validation",
    "tests.test_relational_policy",
    "tests.test_release_cli",
    "tests.test_return_contract",
    "tests.test_review_entrypoint",
    "tests.test_session_correspondence",
    "tests.test_session_initial_state",
    "tests.test_session_observation",
    "tests.test_source_bindings",
    "tests.test_source_entry",
    "tests.test_source_paths",
    "tests.test_source_study",
    "tests.test_source_workflow",
    "tests.test_sql_seed",
    "tests.test_stateful_sequence",
    "tests.test_summarize",
    "tests.test_support_overlap_audit",
    "tests.test_symbolic_comparison",
    "tests.test_symbolic_comparison_evidence",
    "tests.test_symbolic_family",
    "tests.test_symbolic_profile",
    "tests.test_token_lifecycle",
    "tests.test_transform_guard",
    "tests.test_view_binding",
)

FRAMEWORK_TEST_MODULES = (
    "tests.test_boundary_repairs",
    "tests.test_cached_decision",
    "tests.test_cached_factory",
    "tests.test_dependency_flow",
    "tests.test_file_wrapper_discovery",
    "tests.test_finite_routes",
    "tests.test_frontend_scan",
    "tests.test_native_casbin",
    "tests.test_native_literal_policy",
    "tests.test_native_pipeline",
    "tests.test_native_runtime",
    "tests.test_native_state_export",
    "tests.test_persistent_store",
    "tests.test_policy_cache",
    "tests.test_python_wrapper",
    "tests.test_repair_profiles",
    "tests.test_request_frontend",
    "tests.test_request_outcomes",
    "tests.test_rest_discovery",
    "tests.test_rest_policy",
    "tests.test_rest_source_chain",
    "tests.test_snapshot_discovery",
    "tests.test_snapshot_policy",
    "tests.test_source_contracts",
    "tests.test_source_family",
    "tests.test_tenant_dependency",
    "tests.test_tenant_lookup",
    "tests.test_tenant_routes",
    "tests.test_threadpool_roles",
    "tests.test_token_roles",
    "tests.test_versioned_cache",
    "tests.test_versioned_discovery",
    "tests.test_workflow_replay",
    "tests.test_yaml_discovery",
    "tests.test_yaml_policy",
    "tests.test_workflow_syntax",
)

QUERY_TEST_MODULES = (
    "tests.test_tenant_query",
)

CORE_MODES = (
    {"name": "normal", "python_flags": ()},
    {"name": "optimized", "python_flags": ("-O",)},
    {"name": "strict", "python_flags": ("-OO", "-W", "error")},
)

CORE_EVIDENCE = (
    {
        "name": "credential-observations",
        "arguments": ("-W", "error", "source_study/replay.py", "check"),
        "description": "Verify source bindings and all 1,260 owned credential contexts.",
    },
    {
        "name": "source-observer",
        "arguments": (
            "-W", "error", "-m", "source_study.verify_source_observer",
            "--results", "results/source-observer",
        ),
        "description": "Reexecute the selected CPython source bodies and recompute the complete summary.",
        "output_argument": "--output",
        "output_file": "source-observer-verification.json",
    },
    {
        "name": "initial-store-native",
        "arguments": (
            "-W", "error", "source_study/session_initial_state/run.py", "verify",
            "--input", "results/session-initial-state",
        ),
        "description": "Verify retained native initial-store traces and strategies.",
    },
    {
        "name": "initial-store-finite",
        "arguments": (
            "-W", "error", "benchmarks/audit_session_initial_state.py", "--verify",
            "results/session-initial-state/finite-audit.json.gz",
        ),
        "description": "Independently verify the finite initial-store audit.",
    },
)

# Tools required only by optional/native or proof reacquisition.  Their absence
# must not be converted into a scientific mismatch or a core-profile skip.
FULL_TOOLS = (
    {"name": "bubblewrap", "executables": ("bwrap",)},
    {"name": "Lean 4", "executables": ("lake", "lean")},
)

FRAMEWORK_REQUIREMENTS = "requirements-test.txt"
QUERY_REQUIREMENTS = "requirements-query.txt"
FULL_REQUIREMENTS = "requirements-test.txt"
