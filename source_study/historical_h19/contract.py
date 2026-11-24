"""Finite fixtures and independently stated observation requirements."""
from __future__ import annotations

FIELDS = ("id", "token", "user_id", "expiry_date", "max_expiry_date")
TOKENS = ("h19-owned-fixture-alpha", "h19-owned-fixture-beta")
PROFILES = (
    ("before", "before", False),
    ("after", "before", False),
    ("before", "after", False),
    ("after", "after", False),
    ("after", "after", True),
)


def profile_id(producer: str, consumer: str, repair: bool) -> str:
    return f"producer-{producer}__consumer-{consumer}" + ("__owned-repair" if repair else "")


def fixtures() -> dict:
    selections = (None, ("token",), ("user_id",), ("token", "user_id"),
                  FIELDS, ("expiry_date", "max_expiry_date"))
    contexts = []
    for i, requested in enumerate(selections):
        for j, override in enumerate((None, True, False)):
            contexts.append({"id": f"selection-{i}-override-{j}",
                             "requested_fields": None if requested is None else list(requested),
                             "exclude_secrets_override": override})
    return {
        "scope": "Two owned SQLite rows; no HTTP server, real credentials or account actions.",
        "rows": [
            {"token": token, "user_id": i + 1,
             "expiry_date": "2030-01-01T00:00:00", "max_expiry_date": "2030-01-08T00:00:00"}
            for i, token in enumerate(TOKENS)
        ],
        "profiles": [{"id": profile_id(p, c, r), "producer": p, "consumer": c,
                      "owned_filter_boundary_repair": r} for p, c, r in PROFILES],
        "selection_contexts": contexts,
        "filter_contexts": [
            {"id": "matching-token", "params": {"token": TOKENS[0], "token__match": "exact"}},
            {"id": "absent-token", "params": {"token": "h19-owned-absent", "token__match": "exact"}},
            {"id": "ordinary-user", "params": {"user_id": "1"}},
        ],
        "requirements": {
            "confidential_output": "With exclusion enabled, no stored token value occurs in the response rows.",
            "filter_boundary": "A field declared secret must not be accepted by the generated filter model.",
            "explicit_inclusion": "exclude_secrets=False intentionally permits token output; it is a separate configuration.",
            "ordinary_field": "The ordinary user_id filter remains usable after the owned repair.",
        },
    }


def contains_owned_token(rows: list[dict]) -> bool:
    return any(row.get("token") in TOKENS for row in rows)


def normalise(value):
    """Retain types relevant here, with explicit ISO dates for JSON storage."""
    from datetime import datetime
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): normalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalise(v) for v in value]
    if value is None or type(value) in (bool, int, float, str):
        return value
    raise TypeError(f"Unregistered observation type: {type(value).__name__}")
