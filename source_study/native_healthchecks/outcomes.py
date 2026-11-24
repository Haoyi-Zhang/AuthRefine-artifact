"""Exact finite observation vectors for the declared, already executed protocol."""
from copy import deepcopy

from . import contracts

def vectors(case, *, required_length=None):
    contracts.check_case(case, required_length=required_length)
    references, observations = [], []
    state = {"alice": "new", "bob": "new", "flips": []}
    keys = {name + "_" + role: case["owners"][name][role] for name in ("alice", "bob") for role in ("rw", "ro")}
    projects = deepcopy(case["initial"]["projects"])
    for op, record in zip(contracts.protocol()[:len(case["records"])], case["records"], strict=True):
        expected, after = contracts.reference_step(state, op)
        if op["kind"] == "rotate":
            for project in projects:
                if project["id"] == case["owners"][op["owner"]]["project_id"]:
                    project["api_key" if op["role"] == "rw" else "api_key_readonly"] = contracts.credential_digest(record["returned_key"])
        wanted = dict(kind=op["kind"], store=contracts.expected_store(case, after, projects))
        actual = dict(kind=op["kind"], store=contracts.semantic_store(record["after"]))
        if op["kind"] == "http":
            project_id = None if expected["owner"] is None else case["owners"][expected["owner"]]["project_id"]
            wanted.update(http_status=expected["status"], project_id=project_id, readonly=expected["readonly"],
                          api_version=None if project_id is None else case["api_version"],
                          project_class=None if project_id is None else "hc.accounts.models.Project",
                          response=contracts.expected_http(case, op, expected, after))
            managers, transferred = contracts.expected_manager(case, op, expected)
            wanted.update(manager_returns=managers, manager_result_is_request_project=transferred)
            actual.update(http_status=record["http_status"], project_id=record["request_project_id"], readonly=record["request_readonly"],
                          api_version=record["request_api_version"], project_class=record["request_project_class"],
                          manager_returns=record["source_manager_returns"], manager_result_is_request_project=record["manager_result_is_request_project"],
                          response=dict(json=record["response"], text=None if record["response_headers"].get("Content-Type", "").startswith("application/json") else record["response_text"],
                                        headers=contracts.normalized_headers(record["response_headers"]), cookies=record["response_cookies"]))
        else:
            slot = contracts.route_slot(contracts.configurations()[case["configuration"]], op["owner"] + "_" + op["role"])
            owner, role = slot.split("_")
            token = record["returned_key"]
            column = "api_key" if role == "rw" else "api_key_readonly"
            stored = contracts.project_rows(record["after"])[case["owners"][owner]["project_id"]][column]
            wanted["producer"] = dict(project=op["owner"], role=op["role"], native_class="hc.accounts.models.Project", prefix="hcw_" if op["role"] == "rw" else "hcr_", length=32, fresh=True, persisted=True)
            actual["producer"] = dict(project=record["producer_project"], role=record["producer_role"], native_class=record["producer_class"], prefix=token[:4], length=len(token), fresh=token != keys[slot], persisted=stored == contracts.credential_digest(token))
            keys["old_" + slot], keys[slot] = keys[slot], token
        references.append(wanted)
        observations.append(actual)
        state = after
    return references, observations


def project(rows, mode):
    if mode == "complete": return deepcopy(rows)
    if mode == "http_status":
        return [{"http_status": row.get("http_status")} for row in rows]
    raise ValueError("unknown observation mode")


def independent_profile(case, caller, mode, *, replay_length=None):
    """Admit a full protocol, or explicitly check a measured failing prefix."""
    length = contracts.CALLERS[caller]
    expected, actual = (project(rows[:length], mode) for rows in vectors(case, required_length=replay_length))
    first = next((i for i, (left, right) in enumerate(zip(expected, actual, strict=True)) if not contracts.typed_equal(left, right)), None)
    if first is None and len(case["records"]) < length:
        raise ValueError("an incomplete replay cannot establish agreement on the declared caller")
    return dict(caller=caller, mode=mode, configuration=case["configuration"], equivalent=first is None,
                length=None if first is None else first + 1,
                indices=[] if first is None else list(range(first + 1)),
                prefix_only=True, admitted_operations=length)
