"""Type-preserving admission of recorded source observations.

These checks apply to evidence, not to the source language's equality operator.
In particular, a Boolean flag and an integer counter remain different recorded
values even when Python's ordinary equality would compare them as equal.
"""
from collections import Counter


def typed_equal(left, right):
    """Compare JSON-like trees without bool/int or int/float coercion."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        left_keys = {(type(key), key): key for key in left}
        right_keys = {(type(key), key): key for key in right}
        return left_keys.keys() == right_keys.keys() and all(
            typed_equal(left[left_keys[key]], right[right_keys[key]]) for key in left_keys)
    if type(left) in (list, tuple):
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def require(condition, location, explanation):
    if not condition:
        raise ValueError(location + ": " + explanation)


def object_fields(value, fields, location):
    require(type(value) is dict and all(type(key) is str for key in value)
            and set(value) == set(fields), location, "observation fields differ")


def sequence(value, location):
    require(type(value) is list, location, "list required")
    return value


def integer(value, location, *, minimum=None, maximum=None, nullable=False):
    if nullable and value is None:
        return
    require(type(value) is int and (minimum is None or value >= minimum)
            and (maximum is None or value <= maximum), location, "integer value required")


def boolean(value, location, *, nullable=False):
    require(type(value) is bool or (nullable and value is None), location, "Boolean value required")


def string(value, location, *, nullable=False):
    require(type(value) is str or (nullable and value is None), location, "string value required")


def fixture_rows(rows, fixtures, location):
    """Admit the complete declared ordered fixture set, without duplicate IDs."""
    sequence(rows, location)
    sequence(fixtures, location + ".fixtures")
    expected_ids = [case["id"] for case in fixtures]
    require(all(type(key) is str for key in expected_ids)
            and len(set(expected_ids)) == len(expected_ids), location, "declared fixture IDs are not unique strings")
    require(len(rows) == len(fixtures), location, "complete fixture set required")
    actual_ids = []
    for index, row in enumerate(rows):
        require(type(row) is dict and type(row.get("id")) is str,
                f"{location}[{index}]", "fixture ID required")
        actual_ids.append(row["id"])
    require(len(set(actual_ids)) == len(actual_ids), location, "duplicate fixture ID")
    require(typed_equal(actual_ids, expected_ids), location, "fixture identity or order differs")
    return rows


def validate_credential_row(row, case, expected):
    """Check one native credential result against its independent finite oracle."""
    where = "credential." + case["id"]
    object_fields(row, ("id", "observed", "expected", "agrees", "sql",
                       "exact_resolved_project_identity_transferred", "serializer_transfers",
                       "source_manager_returns", "native_mac_calls", "IR_steps"), where)
    require(typed_equal(row["id"], case["id"]), where, "fixture identity differs")
    wanted = expected(case)
    fields = ("status", "project", "readonly", "version", "consumer")
    for name in ("observed", "expected"):
        value = row[name]
        object_fields(value, fields, where + "." + name)
        integer(value["status"], where + "." + name + ".status")
        integer(value["project"], where + "." + name + ".project", minimum=1, maximum=3, nullable=True)
        boolean(value["readonly"], where + "." + name + ".readonly", nullable=True)
        integer(value["version"], where + "." + name + ".version", minimum=1, maximum=3, nullable=True)
        string(value["consumer"], where + "." + name + ".consumer", nullable=True)
    require(typed_equal(row["expected"], wanted), where, "independent expected observation differs")
    agrees = typed_equal(row["observed"], wanted)
    boolean(row["agrees"], where + ".agrees")
    require(row["agrees"] is agrees, where, "reported agreement differs from recomputed agreement")
    require(agrees, where, "independent finite reference differs")
    observed = row["observed"]
    boolean(row["exact_resolved_project_identity_transferred"], where + ".identity")
    require(row["exact_resolved_project_identity_transferred"] is (observed["project"] is not None),
            where, "resolved project identity evidence differs")
    transfers = sequence(row["serializer_transfers"], where + ".serializer_transfers")
    wanted_transfers = []
    if observed["consumer"] == "serializer_boundary":
        wanted_transfers = [{"check_id": case["target"], "project_id": observed["project"],
                             "readonly": observed["readonly"], "v": observed["version"]}]
    # The observation's public key is "version"; the source call's keyword is "v".
    require(typed_equal(transfers, wanted_transfers), where,
            "serializer readonly/version/record transfer differs in value or type")
    returns = sequence(row["source_manager_returns"], where + ".source_manager_returns")
    require(len(returns) <= 1, where, "unexpected manager return count")
    for value in returns:
        object_fields(value, ("function", "project"), where + ".source_manager_returns")
        require(value["function"] == "ProjectManager.for_api_key", where, "manager function differs")
        integer(value["project"], where + ".manager_project", minimum=1, maximum=3, nullable=True)
        require(typed_equal(value["project"], observed["project"]), where, "manager/project handoff differs")
    require(observed["project"] is None or bool(returns), where, "resolved project has no manager return")
    for index, sql in enumerate(sequence(row["sql"], where + ".sql")):
        location = f"{where}.sql[{index}]"
        object_fields(sql, ("statement", "parameters"), location)
        string(sql["statement"], location + ".statement")
        require(sql["statement"].lstrip().upper().startswith("SELECT"), location, "non-SELECT credential query")
        for parameter in sequence(sql["parameters"], location + ".parameters"):
            string(parameter, location + ".parameter")
    integer(row["native_mac_calls"], where + ".native_mac_calls", minimum=0)
    integer(row["IR_steps"], where + ".IR_steps", minimum=1)
    return agrees


def validate_credential_evidence(actual, fixtures, expected):
    """Admit every row and recompute totals for a trusted declared fixture set.

    Public replay supplies the complete independently regenerated fixture list;
    the historical collector's own equality and summary are never sufficient.
    """
    flags = ("original_application_modules_or_tests_executed", "original_serializer_or_write_action_executed",
             "original_deployment_or_randomness_security_certified")
    object_fields(actual, ("rows", "producer_records", "totals", *flags), "credential evidence")
    rows = fixture_rows(actual["rows"], fixtures, "credential rows")
    for flag in flags:
        require(actual[flag] is False, "credential evidence." + flag, "scope flag must be Boolean false")
    totals = Counter()
    for case, row in zip(fixtures, rows, strict=True):
        agrees = validate_credential_row(row, case, expected)
        totals["contexts"] += 1
        totals["actual_SELECTs"] += len(row["sql"])
        totals["native_mac_calls"] += row["native_mac_calls"]
        totals["exact_project_identity_transfers"] += row["exact_resolved_project_identity_transferred"]
        totals["serializer_transfers"] += len(row["serializer_transfers"])
        totals["differences"] += not agrees
        totals["status_" + str(row["observed"]["status"])] += 1
    require(typed_equal(actual["totals"], dict(totals)), "credential totals", "recomputed totals differ")
    wanted_producers = []
    previous_profile = None
    for case in fixtures:
        if case["profile"] != previous_profile and case["profile"] == "stored_mac":
            for project in (1, 2, 3):
                for kind, method in (("w", "set_api_key"), ("r", "set_api_key_readonly")):
                    wanted_producers.append({"project": project, "kind": kind, "source_method": method,
                                             "returned_key_matches": True, "stored_value_matches": True,
                                             "native_mac_calls": 1,
                                             "entropy_contract": "fixed owned alphanumeric28chars for token_urlsafe(21);not RNG/security-quality validation"})
        previous_profile = case["profile"]
    require(typed_equal(actual["producer_records"], wanted_producers), "credential producers",
            "complete producer records differ in value or type")
    return dict(totals)
