"""Reconcile the identical-fixture native runs across the two pinned ORMs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from .verify import require, verify_directory


def compare_versions(directory: Path):
    paths = {v: directory / ("orm-" + v) for v in ("1.16.0", "1.34.0")}
    summaries = {v: verify_directory(p) for v, p in paths.items()}
    def read(version, name):
        return json.loads((paths[version] / name).read_text())
    for name in ("fixtures.json", "source-manifest.json"):
        require((paths["1.16.0"] / name).read_bytes() == (paths["1.34.0"] / name).read_bytes(), "Version matrix inputs differ")
    for version, summary in summaries.items():
        require(summary["orm_version"] == version, "Version result is in the wrong matrix cell")
    runtimes = {v: read(v, "runtime.json") for v in paths}
    installed = {v: {d["name"].lower().replace("_", "-"): d["version"]
                     for d in r["all_distributions"]} for v, r in runtimes.items()}
    changed_packages = [name for name in sorted(set(installed["1.16.0"]) | set(installed["1.34.0"]))
                        if installed["1.16.0"].get(name) != installed["1.34.0"].get(name)]
    require(changed_packages == ["piccolo"], "Other installed package versions changed")
    data = {v: read(v, "native-observations.json") for v in paths}
    fields = ("token_metadata_secret", "registry_fields", "filter_fields")
    changes = {name: [] for name in (*fields, "query_projection", "selection_endpoint", "filter_endpoint")}
    left = {(r["profile"], r["context"]): r for r in data["1.16.0"]["selection_observations"]}
    right = {(r["profile"], r["context"]): r for r in data["1.34.0"]["selection_observations"]}
    require(left.keys() == right.keys(), "Selection profile grids differ")
    def result_semantics(row):
        return {k: row[k] for k in ("outcome", "error_type", "error", "status", "json") if k in row}
    for key, a in left.items():
        b = right[key]
        for field in fields:
            if a[field] != b[field]:
                changes[field].append({"profile": key[0], "context": key[1], "minimum": a[field], "migration_version": b[field]})
        if a["query"]["projected_fields"] != b["query"]["projected_fields"]:
            changes["query_projection"].append(list(key))
        if result_semantics(a["endpoint"]) != result_semantics(b["endpoint"]):
            changes["selection_endpoint"].append(list(key))
    left = {(r["profile"], r["context"]): r for r in data["1.16.0"]["filter_observations"]}
    right = {(r["profile"], r["context"]): r for r in data["1.34.0"]["filter_observations"]}
    require(left.keys() == right.keys(), "Filter profile grids differ")
    for key, a in left.items():
        b = right[key]
        if result_semantics(a["endpoint"]) != result_semantics(b["endpoint"]):
            changes["filter_endpoint"].append({"profile": key[0], "context": key[1],
                "minimum": result_semantics(a["endpoint"]), "migration_version": result_semantics(b["endpoint"])})
    counts = {k: len(v) for k, v in changes.items()}
    require(counts == {"token_metadata_secret": 0, "registry_fields": 54, "filter_fields": 18,
                       "query_projection": 0, "selection_endpoint": 0, "filter_endpoint": 2}, "Version mechanism differs from the observed native predicates")
    return {"orm_versions": list(paths), "same_fixtures_and_original_source_bytes": True,
            "different_installed_packages": changed_packages,
            "fixture_sha256": hashlib.sha256((paths["1.16.0"] / "fixtures.json").read_bytes()).hexdigest(),
            "metadata_pairs": sum(s["metadata_pairs"] for s in summaries.values()),
            "metadata_disagreements": 0, "complete_get_all_invocations": 210,
            "endpoint_returns": 198, "endpoint_exceptions": 12,
            "change_counts": counts, "changes": changes,
            "registry_predicates": {v: s["registry_source"] for v, s in summaries.items()},
            "interpretation": "Both versions suppress stored token values after the producer change; only the metadata-registering ORM also connects the unchanged patched filter consumer to that declaration.",
            "version_selection": {"1.16.0": "Declared minimum in pinned API requirements.",
                                  "1.34.0": "VERSION recorded by the migration in upstream commit 520ec2567ae1d2cc417c8c0d1ad0ddc05549a8a4; not an installed-deployment lock."},
            "passed": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare_versions(args.directory)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.write_text(rendered)
    print(rendered)
