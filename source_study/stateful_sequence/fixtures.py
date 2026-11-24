"""Public, fixed, owned session rows and request names; no private tokens."""
from datetime import datetime, timedelta
from itertools import product

NOW = datetime(2020, 1, 1)
TOKEN_A = "authrefine-owned-session-a"
TOKEN_B = "authrefine-owned-session-b"
UNKNOWN = "authrefine-owned-missing-session"
USER = 101
RESOURCES = ("credential-a", "credential-b", "missing", "row-a", "row-b")
ACTIONS = ("lookup", "remove")


def rows(expiry_a=60, maximum_a=120):
    return [{"id": 1, "token": TOKEN_A, "user_id": USER,
             "expiry_date": NOW + timedelta(seconds=expiry_a),
             "max_expiry_date": NOW + timedelta(seconds=maximum_a)},
            {"id": 2, "token": TOKEN_B, "user_id": USER,
             "expiry_date": NOW + timedelta(seconds=60),
             "max_expiry_date": NOW + timedelta(seconds=120)}]


def token_for(resource, action):
    # remove receives a resolved store identifier; lookup receives a presented
    # credential label. Their reference correspondence is supplied separately.
    # Nonmatching interface labels pass a known-absent token to the actual source.
    return ({"row-a": TOKEN_A, "row-b": TOKEN_B} if action == "remove" else
            {"credential-a": TOKEN_A, "credential-b": TOKEN_B}).get(resource, UNKNOWN)


def alphabet():
    return [["client", resource, action] for resource, action in product(RESOURCES, ACTIONS)]


def serialized_rows(values):
    return [{key: value.isoformat() if isinstance(value, datetime) else value
             for key, value in sorted(row.items())} for row in sorted(values, key=lambda row: row["id"])]


def mask(values):
    return sum(1 << (row["id"] - 1) for row in values)


def expiry_inputs():
    for number, (expiry, maximum, increase, resource) in enumerate(product(
            (-1, 0, 10, 30, 60), (-1, 0, 120), (None, 30),
            ("credential-a", "credential-b", "missing"))):
        yield {"id": f"expiry-{number:03}", "expiry_a_seconds": expiry,
               "maximum_a_seconds": maximum, "increase_seconds": increase,
               "request": ["client", resource, "lookup"]}


def document():
    return {"clock": NOW.isoformat(), "initial_rows": serialized_rows(rows()),
            "alphabet": alphabet(), "expiry_inputs": list(expiry_inputs()),
            "input_contract": {
                "lookup": "presented credential label translated to the explicit token string",
                "remove": "already resolved store-row label translated to its explicit token string",
                "other_labels": "the same known-absent fixture token",
                "decision": "lookup returns a user id: allow; returns None: deny; completed remove: allow",
                "state": "two presence bits for the identified persisted session rows",
                "lifecycle_clock_and_expiry": "fixed clock; both stored sessions unexpired; increase_expiry=None",
                "separate_expiry_grid": "strict expiry and maximum boundaries, plus optional renewal; not included in the two-bit finite graph",
                "same_user": "both sessions belong to user 101, as with two devices for one account",
                "reference_family": "two supplied bijections from presented credential labels to independently identified store rows",
                "identity_boundary": "raw selected row/token reveal the correspondence on a lookup; the finite contract intentionally compares decision and presence state"}}
