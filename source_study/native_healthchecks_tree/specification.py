"""Finite request language and an independent lifecycle reference.

No application or framework module is imported here. Physical histories remain
separate even when their declared observations are equal.
"""
from copy import deepcopy
from contextlib import closing
from itertools import product
import base64
import gzip
import json
import math
from pathlib import Path
import sqlite3

from source_study.native_healthchecks import contracts

DEPTH = 3
SYMBOLS = ("get", "pause", "resume")
INITIAL_STATUSES = ("new", "paused")
ARMS = contracts.ARMS
FORMATS = contracts.FORMATS
API_VERSIONS = contracts.API_VERSIONS
OPERATIONS = {
    symbol: dict(name=symbol, kind="http", route="single" if symbol == "get" else symbol,
                 target="alice", key="alice_ro" if symbol == "get" else "alice_rw",
                 method="GET" if symbol == "get" else "POST", body=None)
    for symbol in SYMBOLS
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def typed_equal(left, right):
    """JSON equality preserving Boolean, integer and floating-point types."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        if len(left) != len(right) or any(type(key) is not str for key in (*left, *right)):
            return False
        return left.keys() == right.keys() and all(typed_equal(value, right[key]) for key, value in left.items())
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right, strict=True))
    if isinstance(left, float) and (not math.isfinite(left) or not math.isfinite(right)):
        return False
    return left == right


def words(depth=DEPTH):
    return [()] + [word for length in range(1, depth + 1) for word in product(SYMBOLS, repeat=length)]


def language_manifest():
    return dict(operations=deepcopy(OPERATIONS), depth=DEPTH, words=[list(word) for word in words()],
                initial_statuses=list(INITIAL_STATUSES), key_formats=list(FORMATS), api_versions=list(API_VERSIONS),
                source_arms=list(ARMS), configuration="identity", one_physical_node_per_history=True,
                state_quotient_used=False, complete_unbounded_physical_reachability=False)


def name(word):
    return "root" if not word else "-".join(word)


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, sort_keys=True, indent=None if path.suffix == ".gz" else 2,
                      separators=(",", ":") if path.suffix == ".gz" else None,
                      allow_nan=False) + "\n").encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)


def sqlite_snapshot(raw):
    """Read all persistent tables and schema from an exact SQLite byte image."""
    with closing(sqlite3.connect(":memory:")) as db:
        db.deserialize(raw)
        db.execute("PRAGMA query_only=ON")
        db.row_factory = sqlite3.Row
        schema = [dict(row) for row in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
        tables = {}
        for entry in schema:
            if entry["type"] != "table":
                continue
            table = entry["name"]
            quoted = '"' + table.replace('"', '""') + '"'
            rows = []
            for row in db.execute("SELECT rowid AS __rowid__, * FROM " + quoted + " ORDER BY rowid"):
                rows.append({key: ({"sqlite_blob": base64.b64encode(value).decode()}
                                   if isinstance(value, bytes) else value)
                             for key, value in dict(row).items()})
            tables[table] = rows
        return dict(schema=schema, tables=tables)


def projected_store(raw):
    """All rows/columns, with only fresh Flip clock literals projected."""
    result = deepcopy(raw)
    for row in result["tables"]["api_flip"]:
        created, processed = row.pop("created"), row.pop("processed")
        row.update(created_present=created is not None, processed_present=processed is not None,
                   processed_at_creation=typed_equal(created, processed))
    return result


def initial_state(case):
    return {"alice": case["initial_status"], "bob": "new", "flips": []}


def state_after(case, word):
    state = initial_state(case)
    for symbol in word:
        _, state = contracts.reference_step(state, OPERATIONS[symbol])
    return state


def expected_store(case, state):
    result = projected_store(case["initial"])
    by_check = {value["check_id"]: owner for owner, value in case["owners"].items()}
    for row in result["tables"]["api_check"]:
        row["status"] = state[by_check[row["id"]]]
        row["last_start"] = row["last_ping"] = row["alert_after"] = None
    result["tables"]["api_flip"] = [
        dict(__rowid__=index, id=index, owner_id=case["owners"][flip["owner"]]["check_id"],
             old_status=flip["old_status"], new_status=flip["new_status"], reason="",
             created_present=True, processed_present=True, processed_at_creation=True)
        for index, flip in enumerate(state["flips"], 1)
    ]
    if state["flips"]:
        sequence = result["tables"]["sqlite_sequence"]
        existing = next((row for row in sequence if row["name"] == "api_flip"), None)
        if existing is None:
            sequence.append(dict(__rowid__=1 + max((row["__rowid__"] for row in sequence), default=0),
                                 name="api_flip", seq=len(state["flips"])))
        else:
            existing["seq"] = len(state["flips"])
    return result


def reference_observation(case, word):
    state = state_after(case, word[:-1])
    op = OPERATIONS[word[-1]]
    expected, after = contracts.reference_step(state, op)
    project_id = case["owners"]["alice"]["project_id"]
    managers, transferred = contracts.expected_manager(case, op, expected)
    return dict(
        store=expected_store(case, after), http_status=expected["status"],
        project_id=project_id, project_class="hc.accounts.models.Project",
        readonly=expected["readonly"], api_version=case["api_version"],
        manager_returns=managers, manager_result_is_request_project=transferred,
        response=contracts.expected_http(case, op, expected, after),
        client_cookies_before={}, client_cookies_after={},
    )


def actual_observation(record):
    json_response = record["response_headers"].get("Content-Type", "").startswith("application/json")
    return dict(
        store=projected_store(record["after"]), http_status=record["http_status"],
        project_id=record["request_project_id"], project_class=record["request_project_class"],
        readonly=record["request_readonly"], api_version=record["request_api_version"],
        manager_returns=record["source_manager_returns"],
        manager_result_is_request_project=record["manager_result_is_request_project"],
        response=dict(json=record["response"], text=None if json_response else record["response_text"],
                      headers=contracts.normalized_headers(record["response_headers"]),
                      cookies=record["response_cookies"]),
        client_cookies_before=record["client_cookies_before"],
        client_cookies_after=record["client_cookies_after"],
    )


def project(observation, mode):
    if mode == "complete":
        return observation
    if mode == "http_status":
        return {"http_status": observation["http_status"]}
    raise ValueError("undeclared observation")


def validate_initial(case):
    if (case["arm"] not in ARMS or case["format"] not in FORMATS or type(case["api_version"]) is not int or
            case["api_version"] not in API_VERSIONS or case["initial_status"] not in INITIAL_STATUSES):
        raise ValueError("undeclared tree stratum")
    rows = case["initial"]["tables"]
    if set(case["owners"]) != {"alice", "bob"} or len(rows["accounts_project"]) != 2 or len(rows["api_check"]) != 2 or rows["api_flip"]:
        raise ValueError("native initial object population differs")
    if len(rows["auth_user"]) != 2 or len(rows["accounts_profile"]) != 2 or len(rows["api_channel"]) != 2 or len(rows["api_channel_checks"]) != 2:
        raise ValueError("native initial user/profile/channel population differs")
    if any(row["name"] == "api_flip" for row in rows["sqlite_sequence"]):
        raise ValueError("initial Flip sequence is not fresh")
    projects = {row["id"]: row for row in rows["accounts_project"]}
    checks = {row["id"]: row for row in rows["api_check"]}
    for owner, data in case["owners"].items():
        if any(type(data[field]) is not int or data[field] < 1 for field in ("project_id", "check_id")):
            raise ValueError("native owner identifiers have invalid types")
        check = checks[data["check_id"]]
        status = case["initial_status"] if owner == "alice" else "new"
        if not typed_equal(check["project_id"], data["project_id"]) or check["status"] != status or any(check[k] is not None for k in ("last_start", "last_ping", "alert_after")):
            raise ValueError("initial lifecycle state differs")
        for role, column in (("rw", "api_key"), ("ro", "api_key_readonly")):
            token = data[role]
            expected = contracts.credential_digest(token) if case["format"] == "hashed" else token
            if len(token) != 32 or projects[data["project_id"]][column] != expected:
                raise ValueError("native key producer/store relation differs")
    if any(row["next_nag_date"] is not None for row in rows["accounts_profile"]):
        raise ValueError("initial notification state differs")


def admit(case, *, replay_word=None):
    """Require the complete declared tree before any acceptance is reported."""
    validate_initial(case)
    declared = words()[1:] if replay_word is None else [tuple(replay_word[:n]) for n in range(1, len(replay_word) + 1)]
    if replay_word is not None and (not 1 <= len(replay_word) <= DEPTH or any(s not in SYMBOLS for s in replay_word)):
        raise ValueError("undeclared replay word")
    observed = [tuple(record["word"]) for record in case["records"]]
    if len(observed) != len(set(observed)) or set(observed) != set(declared):
        raise ValueError("native history tree is incomplete or contains an extra word")
    by_word = {tuple(record["word"]): record for record in case["records"]}
    keys = {owner + "_" + role: data[role] for owner, data in case["owners"].items() for role in ("ro", "rw")}
    request_case = {**case, "configuration": "identity"}
    for word in declared:
        row = by_word[word]
        parent = None if len(word) == 1 else by_word[word[:-1]]
        before = case["initial"] if parent is None else parent["after"]
        cookies = {} if parent is None else parent["client_cookies_after"]
        if (not typed_equal(row["before"], before) or not typed_equal(row["client_cookies_before"], cookies) or
                row["checkpoint_exact_copy"] is not True):
            raise ValueError("physical parent history or cookie continuity differs")
        if (not typed_equal(row["operation"], OPERATIONS[word[-1]]) or
                not typed_equal(row["request"], contracts.request_spec(request_case, row["operation"], keys))):
            raise ValueError("actual native request differs from the declared word")
        is_json = row["response_headers"].get("Content-Type", "").startswith("application/json")
        if not typed_equal(json.loads(row["response_text"]) if is_json else None, row["response"]):
            raise ValueError("response text and parsed document differ")
        if row["response_headers"].get("Content-Length") != str(len(row["response_text"].encode())):
            raise ValueError("response body byte length differs")
    return by_word


def independent_profile(case, mode, *, replay_word=None):
    rows = admit(case, replay_word=replay_word)
    differences = {}
    for word in sorted(rows, key=lambda w: (len(w), w)):
        expected = project(reference_observation(case, word), mode)
        actual = project(actual_observation(rows[word]), mode)
        if not typed_equal(expected, actual):
            differences[word] = sorted(key for key in expected if not typed_equal(expected[key], actual[key]))
    minimal_bad = [word for word in differences if not any(word[:n] in differences for n in range(1, len(word)))]
    first = min(minimal_bad, key=lambda w: (len(w), w)) if minimal_bad else None
    return dict(mode=mode, equivalent=not differences,
                shortest_word=None if first is None else list(first),
                shortest_length=None if first is None else len(first),
                first_bad_prefixes=[dict(word=list(word), fields=differences[word]) for word in minimal_bad],
                differing_edges=len(differences), admitted_edges=len(rows))
