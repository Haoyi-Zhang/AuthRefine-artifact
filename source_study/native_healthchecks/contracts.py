"""Declared API protocol and reference rules, independent of application imports."""
from copy import deepcopy
import hashlib
import hmac

SECRET = "owned-native-healthchecks-test-key"
SENSITIVE = ("uuid", "ping_url", "update_url", "pause_url", "resume_url", "channels")
ARMS = ("original", "omit_readonly_context", "wrong_project_context", "omit_pause_persistence", "reject_readonly_get")
FORMATS = ("legacy", "hashed")
API_VERSIONS = (1, 2, 3)
CALLERS = {"single_check_read": 4, "read_surface": 12, "lifecycle": 37}
CHECK_SCALARS = dict(slug="", tags="", desc="", n_pings=0, manual_resume=False, methods="", start_kw="", success_kw="", failure_kw="", filter_subject=False, filter_body=False, filter_http_body=False, filter_default_fail=False)
NOT_FOUND_BODY = "\n<!doctype html>\n<html lang=\"en\">\n<head>\n  <title>Not Found</title>\n</head>\n<body>\n  <h1>Not Found</h1><p>The requested resource was not found on this server.</p>\n</body>\n</html>\n"


def typed_equal(left, right):
    """Compare recorded values without conflating Boolean and numeric fields."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(typed_equal(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def configurations():
    result = {}
    for name, change_project, change_role in (("identity", False, False), ("swap_privilege", False, True), ("swap_project", True, False), ("swap_both", True, True)):
        mapping = {}
        for owner in ("alice", "bob"):
            for role in ("ro", "rw"):
                target_owner = ({"alice": "bob", "bob": "alice"}[owner] if change_project else owner)
                target_role = ({"ro": "rw", "rw": "ro"}[role] if change_role else role)
                mapping[owner + "_" + role] = target_owner + "_" + target_role
        result[name] = mapping
    return result


def route_slot(configuration, slot):
    if slot.startswith("old_"):
        return "old_" + configuration[slot[4:]]
    return configuration[slot]


def request_spec(case, op, keys):
    import json
    configuration = configurations()[case["configuration"]]
    def key(slot):
        if slot is None: return None
        if slot == "invalid": return "!" * 32
        return keys[route_slot(configuration, slot)]
    base = "/api/v" + str(case["api_version"]) + "/checks/"
    target = op["target"]
    code = "00000000-0000-4000-8000-000000000099" if target == "missing" else case["owners"][target]["check_uuid"]
    if op["route"] == "list":
        path = base
    elif op["route"] == "unique":
        path = base + hashlib.sha1(code.replace("-", "")[:16].encode()).hexdigest()
    else:
        path = base + code + ("/" + op["route"] if op["route"] in ("pause", "resume") else "")
    body = ""
    if op["body"] == "malformed": body = "not-json"
    elif op["body"] == "list": body = "[]"
    elif op["body"] is not None: body = json.dumps({"api_key": key(op["body"])})
    return dict(method=op["method"], path=path, header_key=key(op["key"]), body=body)


def protocol():
    """A declared finite caller word; repeated requests are actual sequential calls."""
    def http(name, route="single", target="alice", key="alice_ro", method="GET", body=None):
        return dict(name=name, kind="http", route=route, target=target, key=key, method=method, body=body)
    return [
        http("readonly-own"),
        http("readonly-own-second-project", target="bob", key="bob_ro"),
        http("readonly-foreign", target="bob"),
        http("readonly-foreign-other-direction", key="bob_ro"),
        http("readwrite-own", key="alice_rw"),
        http("readonly-list", route="list"),
        http("readonly-list-second-project", route="list", key="bob_ro"),
        http("readonly-unique", route="unique"),
        http("readonly-foreign-unique", route="unique", target="bob"),
        http("missing-check", target="missing"),
        http("missing-key", key=None),
        http("invalid-key", key="invalid"),
        http("readonly-pause", route="pause", method="POST"),
        http("foreign-pause", route="pause", target="bob", key="alice_rw", method="POST"),
        http("pause", route="pause", key="alice_rw", method="POST"),
        http("repeat-pause", route="pause", key="alice_rw", method="POST"),
        http("read-paused", key="alice_ro"),
        http("resume", route="resume", key="alice_rw", method="POST"),
        http("repeat-resume", route="resume", key="alice_rw", method="POST"),
        http("wrong-method", route="pause", key="alice_rw"),
        http("preflight", route="pause", key=None, method="OPTIONS"),
        http("header-project-precedence", route="pause", key="bob_rw", method="POST", body="alice_rw"),
        http("body-key-pause", route="pause", key=None, method="POST", body="alice_rw"),
        http("body-key-resume", route="resume", key=None, method="POST", body="alice_rw"),
        http("invalid-header-precedence", route="pause", key="invalid", method="POST", body="alice_rw"),
        http("header-over-body", route="pause", key="alice_rw", method="POST", body="bob_rw"),
        http("resume-after-header", route="resume", key="alice_rw", method="POST"),
        http("malformed-body", route="pause", key="alice_rw", method="POST", body="malformed"),
        http("non-object-body", route="pause", key="alice_rw", method="POST", body="list"),
        dict(name="rotate-write-key", kind="rotate", owner="alice", role="rw"),
        http("revoked-write-key", key="old_alice_rw"),
        http("replacement-write-key", key="alice_rw"),
        http("readonly-after-write-rotation"),
        dict(name="rotate-read-key", kind="rotate", owner="alice", role="ro"),
        http("revoked-read-key", key="old_alice_ro"),
        http("replacement-read-key"),
        http("other-project-after-rotations", target="bob", key="bob_rw"),
    ]


def credential_digest(token):
    return token[4:12] + "." + hmac.digest(SECRET.encode(), token.encode(), "sha256").hex()


def project_rows(raw):
    return {row["id"]: row for row in raw["projects"]}


def semantic_store(raw):
    """Selected actual rows, retaining every column except fresh Flip clock values.

    Flip clocks remain in raw records. Their non-null/processing relationship is
    observed, while the exact wall-clock reading is not a reference constant.
    This projection makes no claim of a finite physical state space.
    """
    return {
        "projects": deepcopy(raw["projects"]), "checks": deepcopy(raw["checks"]),
        "profiles": deepcopy(raw["profiles"]), "channels": deepcopy(raw["channels"]),
        "flips": [{"id": row["id"], "owner_id": row["owner_id"], "old_status": row["old_status"], "new_status": row["new_status"],
            "reason": row["reason"], "created_present": row["created"] is not None,
            "processed": row["processed"] is not None, "processed_at_creation": typed_equal(row["processed"], row["created"])} for row in raw["flips"]],
    }


def expected_store(case, state, projects):
    result = semantic_store(case["initial"])
    result["projects"] = deepcopy(projects)
    by_check = {owner["check_id"]: name for name, owner in case["owners"].items()}
    for check in result["checks"]:
        check["status"] = state[by_check[check["id"]]]
        check["last_start"] = check["last_ping"] = check["alert_after"] = None
    result["flips"] = [dict(id=index + 1, owner_id=case["owners"][row["owner"]]["check_id"], old_status=row["old_status"],
        new_status=row["new_status"], reason="", created_present=True, processed=row["processed"], processed_at_creation=True)
        for index, row in enumerate(state["flips"])]
    return result


def expected_manager(case, op, expected):
    if expected["owner"] is not None:
        return [dict(project_id=case["owners"][expected["owner"]]["project_id"], native_class="hc.accounts.models.Project")], True
    if expected["status"] == 401:
        slot = op["key"] if op["key"] is not None else (op["body"] if op["method"] == "POST" else None)
        return ([] if slot is None else [None]), None
    return [], None


def reference_step(state, operation):
    """Authentication, object ownership and durable transition contract."""
    result = dict(status=200, owner=None, readonly=None, targets=[])
    if operation["kind"] == "rotate":
        return result, deepcopy(state)
    op = operation
    if op["method"] == "OPTIONS":
        return {**result, "status": 204}, deepcopy(state)
    if op["route"] in ("pause", "resume") and op["method"] != "POST":
        return {**result, "status": 405}, deepcopy(state)
    if op["method"] == "POST" and op["body"] in ("malformed", "list"):
        return {**result, "status": 400}, deepcopy(state)
    key = op["key"] if op["key"] is not None else (op["body"] if op["method"] == "POST" else None)
    if key not in ("alice_rw", "alice_ro", "bob_rw", "bob_ro"):
        return {**result, "status": 401}, deepcopy(state)
    owner, role = key.split("_")
    write = op["route"] in ("pause", "resume")
    if write and role == "ro":
        return {**result, "status": 401}, deepcopy(state)
    result.update(owner=owner, readonly=role == "ro")
    if op["route"] == "list":
        result["targets"] = [owner]
        return result, deepcopy(state)
    if op["target"] == "missing":
        return {**result, "status": 404}, deepcopy(state)
    if op["target"] != owner:
        return {**result, "status": 404 if op["route"] == "unique" else 403}, deepcopy(state)
    if op["route"] == "resume" and state[owner] != "paused":
        return {**result, "status": 409}, deepcopy(state)
    after = deepcopy(state)
    if op["route"] == "pause" and state[owner] != "paused":
        after[owner] = "paused"
        after["flips"].append(dict(owner=owner, old_status=state[owner], new_status="paused", processed=True))
    elif op["route"] == "resume":
        after[owner] = "new"
        after["flips"].append(dict(owner=owner, old_status="paused", new_status="new", processed=True))
    result["targets"] = [owner]
    return result, after


def expected_payload(case, target, readonly, status):
    item = case["owners"][target]
    result = dict(name=target + " check", **CHECK_SCALARS, grace=3600, status=status, started=False,
        last_ping=None, next_ping=None, subject="", subject_fail="",
        badge_url="http://testserver/b/2/" + item["badge_uuid"] + ".svg", timeout=86400)
    if readonly:
        result["unique_key"] = hashlib.sha1(item["check_uuid"].replace("-", "")[:16].encode()).hexdigest()
    else:
        url = "http://testserver/api/v" + str(case["api_version"]) + "/checks/" + item["check_uuid"]
        result.update(uuid=item["check_uuid"], ping_url="http://testserver/ping/" + item["check_uuid"], update_url=url, pause_url=url + "/pause", resume_url=url + "/resume", channels=item["channel_uuid"])
    return result


def normalized_headers(headers):
    result = {name.lower(): value for name, value in headers.items()}
    if "access-control-allow-methods" in result:
        result["access-control-allow-methods"] = sorted(value.strip() for value in result["access-control-allow-methods"].split(","))
    return result


def expected_http(case, op, expected, after):
    import json
    status = expected["status"]
    document, text = None, ""
    if status == 200:
        payloads = [expected_payload(case, target, expected["readonly"], after[target]) for target in expected["targets"]]
        document = {"checks": payloads} if op["route"] == "list" else payloads[0]
    elif status == 401:
        key = op["key"] if op["key"] is not None else (op["body"] if op["method"] == "POST" else None)
        document = {"error": "missing api key" if key is None else "wrong api key"}
    elif status == 400:
        document = {"error": "could not parse request body" if op["body"] == "malformed" else "json validation error: value is not an object"}
    elif status == 404 and op["target"] == "missing":
        text = NOT_FOUND_BODY
    elif status == 409:
        text = "check is not paused"
    wire_text = json.dumps(document) if document is not None else text
    headers = {"Content-Type": "application/json" if document is not None else "text/html; charset=utf-8",
        "Content-Length": str(len(wire_text.encode())), "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin", "Cross-Origin-Opener-Policy": "same-origin"}
    if not (status == 404 and op["target"] == "missing"):
        methods = {"single": ("DELETE", "GET", "OPTIONS", "POST"), "list": ("GET", "OPTIONS", "POST"),
                   "unique": ("GET", "OPTIONS"), "pause": ("OPTIONS", "POST"), "resume": ("OPTIONS", "POST")}[op["route"]]
        headers.update({"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "X-Api-Key",
                        "Access-Control-Allow-Methods": ", ".join(methods), "Access-Control-Max-Age": "600"})
    return dict(json=document, text=None if document is not None else text,
                headers=normalized_headers(headers), cookies={})


def check_case(case, required_length=None):
    """Recompute checks from raw observations, never trust a stored verdict."""
    if required_length is not None and (type(required_length) is not int or not 1 <= required_length <= len(protocol())):
        raise ValueError("invalid declared replay prefix length")
    operations = protocol() if required_length is None else protocol()[:required_length]
    if case["format"] not in FORMATS or type(case["api_version"]) is not int or case["api_version"] not in API_VERSIONS or case["arm"] not in ARMS or case["configuration"] not in configurations():
        raise ValueError("undeclared native case")
    if len(case["records"]) != len(operations):
        raise ValueError("incomplete finite caller protocol")
    failures = []
    initial = case["initial"]
    if set(case["owners"]) != {"alice", "bob"} or len({owner["project_id"] for owner in case["owners"].values()}) != 2:
        raise ValueError("owned projects are not distinct")
    initial_semantic = semantic_store(initial)
    if (len(initial_semantic["checks"]) != 2 or initial_semantic["flips"] or
            any(row["status"] != "new" or any(row[k] is not None for k in ("last_start", "last_ping", "alert_after")) for row in initial_semantic["checks"]) or
            any(row["next_nag_date"] is not None for row in initial_semantic["profiles"])):
        raise ValueError("native initial state differs from the declared protocol initial state")
    state = {"alice": "new", "bob": "new", "flips": []}
    previous = initial
    wanted_projects = deepcopy(initial["projects"])
    keys = {name + "_" + role: case["owners"][name][role] for name in ("alice", "bob") for role in ("rw", "ro")}
    for name, owner in case["owners"].items():
        row = project_rows(initial)[owner["project_id"]]
        for role, column in (("rw", "api_key"), ("ro", "api_key_readonly")):
            token = owner[role]
            want = credential_digest(token) if case["format"] == "hashed" else token
            if len(token) != 32 or row[column] != want:
                raise ValueError("native producer and independently computed credential store differ")
    for index, (op, record) in enumerate(zip(operations, case["records"], strict=True)):
        if not typed_equal(record["operation"], op) or not typed_equal(record["before"], previous):
            raise ValueError("native record no longer follows its declared actual prefix")
        expected, after = reference_step(state, op)
        differences = []
        if op["kind"] == "rotate":
            slot = route_slot(configurations()[case["configuration"]], op["owner"] + "_" + op["role"])
            token = record["returned_key"]
            if len(token) != 32 or token == keys[slot] or not token.startswith("hcw_" if op["role"] == "rw" else "hcr_"):
                differences.append("native key producer")
            field = "api_key" if op["role"] == "rw" else "api_key_readonly"
            projects = project_rows(record["after"])
            if projects[case["owners"][op["owner"]]["project_id"]][field] != credential_digest(token):
                differences.append("persisted replacement credential")
            for project in wanted_projects:
                if project["id"] == case["owners"][op["owner"]]["project_id"]:
                    project[field] = credential_digest(token)
            keys["old_" + slot], keys[slot] = keys[slot], token
        else:
            if not typed_equal(record["request"], request_spec(case, op, keys)):
                raise ValueError("native HTTP request differs from its one fixed credential configuration")
            import json
            json_response = record["response_headers"].get("Content-Type", "").startswith("application/json")
            parsed = json.loads(record["response_text"]) if json_response else None
            if not typed_equal(parsed, record["response"]):
                raise ValueError("retained response object and actual body differ")
            if record["response_headers"].get("Content-Length") != str(len(record["response_text"].encode())):
                raise ValueError("actual response body and length metadata differ")
            if not typed_equal(record["http_status"], expected["status"]):
                differences.append("http_status")
            project_id = None if expected["owner"] is None else case["owners"][expected["owner"]]["project_id"]
            if not typed_equal(record["request_project_id"], project_id):
                differences.append("authorization_project")
            if not typed_equal(record["request_readonly"], expected["readonly"]):
                differences.append("authorization_readonly")
            if expected["owner"] is not None and record["request_project_class"] != "hc.accounts.models.Project":
                differences.append("native_project_class")
            managers, transferred = expected_manager(case, op, expected)
            if not typed_equal(record["source_manager_returns"], managers) or not typed_equal(record["manager_result_is_request_project"], transferred):
                differences.append("native_manager_identity_handoff")
            response_contract = expected_http(case, op, expected, after)
            response_actual = dict(json=record["response"], text=None if json_response else record["response_text"],
                headers=normalized_headers(record["response_headers"]), cookies=record["response_cookies"])
            if not typed_equal(response_actual, response_contract):
                differences.append("complete_http_response")
            if expected["status"] == 200:
                payloads = record["response"].get("checks", []) if op["route"] == "list" and isinstance(record["response"], dict) else [record["response"]]
                if len(payloads) != len(expected["targets"]):
                    differences.append("response_objects")
                else:
                    for target, payload in zip(expected["targets"], payloads, strict=True):
                        want = expected_payload(case, target, expected["readonly"], after[target])
                        if not isinstance(payload, dict) or any(not typed_equal(payload.get(k), v) for k, v in want.items()):
                            differences.append("response_content")
                        if isinstance(payload, dict) and expected["readonly"] and any(k in payload for k in SENSITIVE):
                            differences.append("readonly_sensitive_fields")
        observed_store = semantic_store(record["after"])
        checks = {r["id"]: r for r in observed_store["checks"]}
        for name, owner in case["owners"].items():
            r = checks[owner["check_id"]]
            if r["project_id"] != owner["project_id"] or r["status"] != after[name] or any(r[k] is not None for k in ("last_start", "last_ping", "alert_after")):
                differences.append("persisted_check:" + name)
        complete_wanted_store = expected_store(case, after, wanted_projects)
        if not typed_equal(observed_store["flips"], complete_wanted_store["flips"]):
            differences.append("persisted_flip_log")
        if any(r["next_nag_date"] is not None for r in observed_store["profiles"]):
            differences.append("profile_state")
        for table in ("projects", "checks", "profiles", "channels"):
            if not typed_equal(observed_store[table], complete_wanted_store[table]):
                differences.append("complete_persisted_rows:" + table)
        if differences:
            failures.append(dict(index=index, operation=op["name"], fields=sorted(set(differences))))
        previous, state = record["after"], after
    return dict(arm=case["arm"], format=case["format"], api_version=case["api_version"], configuration=case["configuration"], operations=len(operations), http_requests=sum(op["kind"] == "http" for op in operations), disagreements=failures,
                status_disagreements=sum("http_status" in f["fields"] for f in failures),
                first_difference=None if not failures else failures[0])
