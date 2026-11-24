"""Stdlib verifier of raw H19 observations against finite fixture equations."""
from __future__ import annotations
import json
from pathlib import Path

from .contract import FIELDS, TOKENS, contains_owned_token, fixtures as make_fixtures


def require(condition, message):
    if not condition:
        raise ValueError(message)


def returned_rows(endpoint):
    require(endpoint["outcome"] == "return", "Expected an endpoint return")
    body = json.loads(endpoint["body"]) if endpoint["json"] is not None else None
    require(body == endpoint["json"], "Serialized response and retained parsed JSON differ")
    rows = body.get("rows", []) if isinstance(body, dict) else []
    require(endpoint["row_count"] == len(rows), "Incorrect endpoint denominator")
    require(endpoint["owned_token_value_exposed"] == contains_owned_token(rows), "Incorrect value-exposure label")
    return rows


def expected_rows(fixtures, selected, *, after, exclusion, descending):
    rows = []
    for i, fixture in enumerate(fixtures["rows"], 1):
        original = {"id": i, **fixture}
        values = {k: original[k] for k in FIELDS if k in selected}
        if "token" in values and after and exclusion:
            values["token"] = None
        rows.append(values)
    return list(reversed(rows)) if descending else rows


def verify(fixtures, observations, comparison):
    require(fixtures == make_fixtures(), "Fixture domain changed")
    from .source import registry_model
    orm_version = observations.get("orm_version", "1.16.0")
    registry = registry_model(orm_version)
    require(observations.get("registry_source", registry) == registry, "Registry source binding differs")
    require(comparison.get("registry_source", registry) == registry, "Comparison registry source differs")
    metadata_registry = registry["predicate_mode"] == "secrecy-metadata"
    profiles = {p["id"]: p for p in fixtures["profiles"]}
    contexts = {c["id"]: c for c in fixtures["selection_contexts"]}
    require(len(observations["selection_observations"]) == len(profiles) * len(contexts), "Incomplete selection grid")
    require(len(observations["filter_observations"]) == len(profiles) * len(fixtures["filter_contexts"]), "Incomplete filter grid")
    pairs = {(p, c) for p in profiles for c in contexts}
    profile_summary = {p: {"selection_trials": 0, "endpoint_returns": 0, "endpoint_exceptions": 0,
                          "output_value_exposures": 0, "explicit_inclusion_exposures": 0,
                          "filter_token_accepted": None} for p in profiles}
    for row in observations["selection_observations"]:
        key = row["profile"], row["context"]
        require(key in pairs, "Duplicate or unknown selection trial")
        pairs.remove(key)
        profile, context = profiles[key[0]], contexts[key[1]]
        requested = context["requested_fields"]
        selected = list(FIELDS) if requested is None else requested
        exclusion = context["exclude_secrets_override"] is not False
        after = profile["producer"] == "after"
        projected = [k for k in selected if not (k == "token" and exclusion and after)]
        require(row["requested_fields"] == requested and row["exclude_secrets_override"] == context["exclude_secrets_override"], "Selection input changed")
        require(row["effective_exclusion"] is exclusion, "Exclusion option changed")
        require(row["token_metadata_secret"] is after, "Native column metadata differs from source declaration")
        expected_registry = ["token"] if after and metadata_registry else []
        require(row["registry_fields"] == expected_registry, "Native subclass registry or metadata registry result differs")
        exclude_filter_token = (profile["owned_filter_boundary_repair"] or
                                (profile["consumer"] == "after" and after and metadata_registry))
        expected_filter = [k for k in FIELDS if not (exclude_filter_token and k == "token")]
        require(row["filter_fields"] == expected_filter, "Filter model disagrees with its metadata boundary")
        require(list(row["filter_schema"]["properties"]) == expected_filter, "Real Pydantic schema disagrees with model fields")
        require(row["query"]["projected_fields"] == projected, "Native query projection differs")
        require(len(row["query"]["sql_calls"]) == 1, "Expected one native SQL query per low-level selection")
        require(len(row["endpoint"]["sql_calls"]) == 1, "Expected one native SQL query per selection endpoint")
        counts = profile_summary[key[0]]
        counts["selection_trials"] += 1
        if not projected:
            for result in (row["query"], row["endpoint"]):
                require(result["outcome"] == "exception" and result["error_type"] == "OperationalError", "Empty native projection must retain its actual SQL error")
                call = result["sql_calls"][0]
                require(call["outcome"] == "exception" and call["error_type"] == "OperationalError", "Missing SQL exception record")
            counts["endpoint_exceptions"] += 1
            continue
        require(row["query"]["outcome"] == "return", "Nonempty projection failed")
        query_expected = expected_rows(fixtures, projected, after=False, exclusion=False, descending=False)
        require(row["query"]["rows"] == query_expected, "Native query row values differ")
        require(row["query"]["sql_calls"][0].get("rows") == query_expected, "Raw SQL readback differs from query rows")
        returned = returned_rows(row["endpoint"])
        require(row["endpoint"]["status"] == 200, "Unexpected selection status")
        response_expected = expected_rows(fixtures, selected, after=after, exclusion=exclusion, descending=True)
        require(returned == response_expected, "Native JSON row values differ")
        sql_expected = expected_rows(fixtures, projected, after=False, exclusion=False, descending=True)
        require(row["endpoint"]["sql_calls"][0].get("rows") == sql_expected, "Raw SQL readback differs from serialized selection")
        counts["endpoint_returns"] += 1
        if contains_owned_token(returned):
            counts["output_value_exposures"] += 1
            counts["explicit_inclusion_exposures"] += not exclusion
    require(not pairs, "Missing selection trials")

    filter_inputs = {f["id"]: f for f in fixtures["filter_contexts"]}
    seen_filters = set()
    for row in observations["filter_observations"]:
        key = row["profile"], row["context"]
        require(key not in seen_filters, "Duplicate filter trial")
        seen_filters.add(key)
        profile, context = profiles[key[0]], filter_inputs[key[1]]
        require(row["params"] == context["params"], "Filter parameters changed")
        endpoint = row["endpoint"]
        token_filter = context["id"] != "ordinary-user"
        rejects_token = (profile["owned_filter_boundary_repair"] or
                         (profile["producer"] == "after" and profile["consumer"] == "after" and metadata_registry))
        rejected = rejects_token and token_filter
        require(endpoint["status"] == (400 if rejected else 200), "Filter admission status differs")
        returned = returned_rows(endpoint)
        require(len(endpoint["sql_calls"]) == (0 if rejected else 1), "Unexpected SQL execution after filter rejection")
        if rejected:
            require(endpoint["body"] == "token isn't a valid field name.", "Wrong filter rejection")
        else:
            expected = [] if context["id"] == "absent-token" else expected_rows(
                fixtures, FIELDS, after=profile["producer"] == "after", exclusion=True, descending=False)[:1]
            require(returned == expected, "Native filtered rows differ")
            sql_expected = [{k: v for k, v in values.items()
                             if not (k == "token" and profile["producer"] == "after")}
                            for values in expected]
            require(endpoint["sql_calls"][0].get("rows") == sql_expected, "Raw SQL readback differs from filtered response")
        if context["id"] == "matching-token":
            profile_summary[key[0]]["filter_token_accepted"] = not rejected
    require(len(seen_filters) == len(profiles) * len(filter_inputs), "Missing filter trial")
    require(comparison["paired_observations"] == 90 and comparison["disagreements"] == 0, "Wrong metadata comparison count")
    require(len(comparison["rows"]) == 90, "Incomplete metadata comparisons")
    direct_by_key = {(r["profile"], r["context"]): r for r in observations["selection_observations"]}
    seen_comparisons = set()
    for row in comparison["rows"]:
        key = row["profile"], row["context"]
        require(key in direct_by_key and key not in seen_comparisons, "Duplicate metadata comparison")
        seen_comparisons.add(key)
        direct = direct_by_key[key]
        native = {"query_fields": direct["query"]["projected_fields"], "filter_fields": direct["filter_fields"],
                  "registry_fields": direct["registry_fields"], "token_metadata_secret": direct["token_metadata_secret"]}
        require(row["native"] == native and row["native"] == row["interpreter"] and row["agree"] is True, "Wrong metadata agreement")
    for execution in observations["execution_scope"]:
        require(execution["store_before"] == execution["store_after"], "Read-only study modified its store")
        require(not execution["original_module_bytes_modified"] and not execution["original_function_bodies_modified"], "Unreported source transformation")
    before = direct_by_key[("producer-before__consumer-before", "selection-0-override-0")]["endpoint"]
    after = direct_by_key[("producer-after__consumer-after", "selection-0-override-0")]["endpoint"]
    return {
        "orm_version": orm_version, "registry_source": registry,
        "profiles": profile_summary, "metadata_pairs": 90, "metadata_disagreements": 0,
        "original_before_after_metadata_pairs": 36, "cross_version_factorial_pairs": 36, "owned_repair_pairs": 18,
        "selection_endpoint_invocations": 90, "filter_endpoint_invocations": 15,
        "selection_endpoint_returns": sum(r["endpoint_returns"] for r in profile_summary.values()),
        "selection_endpoint_exceptions": sum(r["endpoint_exceptions"] for r in profile_summary.values()),
        "filter_endpoint_returns": 15,
        "default_patch_comparison": {"before_status": before["status"], "after_status": after["status"],
            "status_only_distinguishes": before["status"] != after["status"],
            "json_field_names_distinguish": set(before["json"]["rows"][0]) != set(after["json"]["rows"][0]),
            "stored_token_values_distinguish": before["owned_token_value_exposed"] != after["owned_token_value_exposed"],
            "before_token": "owned fixture value", "after_token": None},
        "scope": "Native pinned dependency profile, not a historical installed lock or a live deployment test.",
        "passed": True,
    }


def verify_directory(directory: Path):
    def read(name):
        return json.loads((directory / name).read_text(encoding="utf-8"))
    from .source import check_source, digest
    require(read("source-manifest.json") == check_source(), "Source manifest differs from current pinned inputs")
    if (directory / "file-hashes.json").is_file():
        for name, expected in read("file-hashes.json").items():
            require(Path(name).name == name, "Invalid retained file path")
            require(digest((directory / name).read_bytes()) == expected, f"Retained file changed: {name}")
    return verify(read("fixtures.json"), read("native-observations.json"), read("comparison.json"))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_directory(args.directory), indent=2))
