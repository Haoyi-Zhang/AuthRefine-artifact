"""Explicit new fixtures; no historical outcome or production evaluator imports."""
import hashlib
import hmac
import itertools
import json
from uuid import UUID

SECRET = "independent-observer-owned-fixture-secret-20261118"
KEYS = ("1w", "1r", "2w", "2r", "3w", "3r", "missing")


def code(target):
    return str(UUID(int=target))


def credential(form, label):
    if label == "missing":
        return ""
    if label == "short":
        return "short-owned-key"
    if label == "unrecognized":
        return "unrecognized-owned-key".ljust(32, "x")
    if label == "bad_digest":
        return "hcw_" + "Collide8" + "invalid-owned-key".ljust(20, "z")
    if form == "plain":
        return ("Independent" + label).ljust(32, "x")
    prefix = "hcw_" if label[1] == "w" else "hcr_"
    lead = "Collide8" if label[0] in "12" else "ThirdPrj"
    return prefix + (lead + label).ljust(28, "x")


def projects(form):
    rows = []
    for project in (1, 2, 3):
        row = {"id": project}
        for suffix, field in (("w", "api_key"), ("r", "api_key_readonly")):
            key = credential(form, f"{project}{suffix}")
            row[field] = (key if form == "plain" else key[4:12] + "." +
                          hmac.new(SECRET.encode(), key.encode(), hashlib.sha256).hexdigest())
        rows.append(row)
    return rows


def request(form, label, version=3, carrier="header", *, method="GET"):
    key = credential(form, label)
    return {"method": method, "headers": {"X-Api-Key": key} if carrier == "header" else {},
            "body_hex": json.dumps({"api_key": key}).encode().hex() if carrier == "body" else "",
            "path_info": f"/api/v{version}/checks/"}


def read_fixtures():
    # The invalid inputs test lookup rejection and a MAC-prefix collision.
    labels = (*KEYS, "short", "unrecognized", "bad_digest")
    return [{"id": f"read-{form}-{key}-{carrier}-v{version}-{target}",
             "form": form, "key": key, "target": target, "version": version,
             "carrier": carrier, "request": request(form, key, version, carrier)}
            for form, key, carrier, version, target in itertools.product(
                ("plain", "stored_mac"), labels, ("header", "body"), (1, 2, 3), (1, 2, 3, 99))]


def resume_symbols():
    return [{"key": key, "target": target} for key, target in itertools.product(KEYS, (1, 2, 3, 99))]


def pretix_fixtures():
    return [{"id": f"event-{i:04d}", "all_events": all_events, "limited_events": list(limited),
             "query": query, "method": method, "permissions": list(grants)}
            for i, (all_events, limited, query, method, grants) in enumerate(itertools.product(
                (False, True), ((), (1,), (2,)), ("own-a", "own-b", "other", "missing"),
                ("GET", "POST", "HEAD"), ((), ("event.items:read",), ("event.items:write",),
                                          ("event.items:read", "event.items:write"))))]


def wger_fixtures():
    return [{"id": f"owner-{actor}-{owner}", "actor": actor, "supplied_owner": owner}
            for actor, owner in itertools.product(
                ("user-1", "user-2", "unauthenticated-record", "absent-record"), (None, 1, 2, 3))]


def all_fixtures():
    return {"version": 1, "origin": "new explicit fixtures, constructed 2026-11-18",
            "healthchecks_projects": {form: projects(form) for form in ("plain", "stored_mac")},
            "healthchecks_reads": read_fixtures(), "healthchecks_resume_symbols": resume_symbols(),
            "healthchecks_resume_initial_store": {"status": "paused", "last_start": "start",
                                                   "last_ping": "ping", "alert_after": "alert"},
            "pretix": pretix_fixtures(), "wger_owner_insert": wger_fixtures()}
