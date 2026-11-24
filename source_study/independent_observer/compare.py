"""A separate comparison stage: production interpreters consume new fixtures.

The CPython collector never imports this module. Healthchecks uses a separate
in-memory primitive provider here, while the CPython collector uses SQLite.
The two providers implement the same declared boundary contract independently.
Pretix and Wger use their existing production providers.
"""
from copy import deepcopy
import hmac
import itertools
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from .fixtures import SECRET, code, projects, read_fixtures, resume_symbols, pretix_fixtures, wger_fixtures, request
from .observer import HealthSession
from .source import nodes_and_manifest
from .evidence import (health_observation, pretix_observation, validate_fixture_cohort,
                       validate_observations, validate_resume_graphs, wger_observation)
from source_study.observation_evidence import typed_equal

ART = Path(__file__).resolve().parents[2]


def production_imports():
    for path in (ART / "src", ART / "source_study/code", ART / "adaptation_study"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from credential_flow_ir import Machine, Record, Ref, QueryMiss, NotFound, compile_function
    # Import defines the existing evaluator; it does not call its Django setup.
    # Use the qualified package path so another study's flat ``profiles`` module
    # cannot be selected from sys.path or an earlier import cache.
    from adaptation_study.profiles import Body
    return Machine, Record, Ref, QueryMiss, NotFound, compile_function, Body


class IRSession:
    """Independent in-memory provider for the production source interpreter.

    This class deliberately does not inherit the CPython collector or call its
    query, save, event, serializer, snapshot or response functions. Its ordinary
    dictionary stores and explicit typed IR values implement the same public
    finite primitive contracts that the other arm exercises through SQLite.
    """
    def __init__(self, form, nodes):
        self.form, self.nodes = form, nodes
        Machine, Record, Ref, QueryMiss, NotFound, compile_function, Body = production_imports()
        self.Machine, self.Record, self.Ref, self.QueryMiss, self.NotFound, self.Body = Machine, Record, Ref, QueryMiss, NotFound, Body
        self.programs = {name: compile_function(nodes[key]) for name, key in {
            "ProjectManager.for_api_key": "manager", "Project.compare_api_key": "compare_key",
            "error": "error", "_get_api_version": "version", "get_check": "get_check"}.items()}
        for entry in ("authorize", "authorize_read"):
            wrappers = [n for n in nodes[entry].body if getattr(n, "name", None) == "wrapper"]
            if len(wrappers) != 1:
                raise ValueError("one source authorization closure required")
            self.programs[entry + ".wrapper"] = compile_function(wrappers[0])
        self.ir_projects = {row["id"]: Record("Project", dict(row)) for row in projects(form)}
        self.reset()

    def close(self):
        pass

    def reset(self):
        self.records = {i: {"id": i, "code": code(i), "project_id": i, "status": "paused",
                            "last_start": "start", "last_ping": "ping", "alert_after": "alert"} for i in (1, 2, 3)}
        self.events = []

    def snapshot(self):
        columns = ("id", "code", "project_id", "status", "last_start", "last_ping", "alert_after")
        return {"records": [[self.records[i][column] for column in columns] for i in sorted(self.records)],
                "events": [list(e) for e in sorted(self.events)]}

    @staticmethod
    def mask(snapshot):
        # Independent decoding from the observed record vector.
        value = 0
        for row in snapshot["records"]:
            if row[3] == "new":
                value += 2 ** (row[0] - 1)
        return value

    @staticmethod
    def invariant(snapshot):
        rows = snapshot["records"]
        if not typed_equal([r[:3] for r in rows], [[i, code(i), i] for i in (1, 2, 3)]):
            return False
        wanted_events = []
        for row in rows:
            if row[3] == "paused":
                if not typed_equal(row[4:], ["start", "ping", "alert"]):
                    return False
            elif row[3] == "new":
                if not typed_equal(row[4:], [None, None, None]):
                    return False
                wanted_events.append([row[0], "new", 1])
            else:
                return False
        return typed_equal(snapshot["events"], wanted_events)

    def bindings(self, write):
        R, F = self.Record, self.Ref
        return {"Project": R("Namespace", {"objects": R("ProjectManager", {}), "DoesNotExist": self.QueryMiss}),
                "Check": F("CheckModel"), "settings": R("Namespace", {"SECRET_KEY": SECRET}),
                "hmac": R("Namespace", {"digest": F("hmac.digest"), "compare_digest": F("hmac.compare_digest")}),
                "json": R("Namespace", {"loads": F("json.loads")}), "dict": dict, "ValueError": ValueError,
                **{n: F(n) for n in ("len", "str", "isinstance", "Q", "error", "_get_api_version",
                                    "get_object_or_404", "HttpResponseForbidden", "HttpResponse", "JsonResponse")},
                "f": F("resume" if write else "get_check")}

    def attribute(self, obj, name):
        if obj.kind == "ProjectManager" and name in ("filter", "get"):
            return self.Ref("ProjectQuery." + name)
        if obj.kind == "Check" and name in ("to_dict", "save", "create_flip"):
            return self.Ref("Check." + name, obj)
        raise ValueError("IR primitive outside owned boundary: " + obj.kind + "." + name)

    def query_or(self, left, right):
        if not all(isinstance(v, tuple) and v and v[0] == "query" for v in (left, right)):
            raise ValueError("unbound query disjunction")
        return ("query", *left[1:], *right[1:])

    def on_source_return(self, name, value, env):
        if name == "ProjectManager.for_api_key":
            self.resolved = value
            self.manager_returns.append(None if value is None else value.fields["id"])

    def call(self, ref, args, kwargs):
        name = ref.name
        if name == "len":
            return len(*args, **kwargs)
        if name == "str":
            return str(*args, **kwargs)
        if name == "isinstance":
            return isinstance(*args, **kwargs)
        if name == "hmac.digest":
            return hmac.digest(*args, **kwargs)
        if name == "hmac.compare_digest":
            return hmac.compare_digest(*args, **kwargs)
        if name == "json.loads":
            return json.loads(*args, **kwargs)
        if name.startswith("scalar."):
            method = name.partition(".")[2]
            if method not in ("startswith", "split", "encode", "decode", "hex"):
                raise ValueError("unreviewed scalar primitive")
            return getattr(ref.receiver, method)(*args, **kwargs)
        if name == "Q":
            if args or not kwargs or not set(kwargs) <= {"api_key", "api_key_readonly"}:
                raise ValueError("unbound query constructor")
            return ("query", tuple(sorted(kwargs.items())))
        if name in ("ProjectQuery.filter", "ProjectQuery.get"):
            if name.endswith("filter"):
                if args or len(kwargs) != 1:
                    raise ValueError("unbound IR prefix lookup")
                field, prefix = next(iter(kwargs.items()))
                if field not in ("api_key__startswith", "api_key_readonly__startswith"):
                    raise ValueError("unbound IR prefix column")
                field = field[:-12]
                return [row for row in self.ir_projects.values() if row.fields[field][:len(prefix)] == prefix]
            if args:
                if len(args) != 1 or kwargs or not isinstance(args[0], tuple) or args[0][0] != "query":
                    raise ValueError("unbound IR disjunctive lookup")
                alternatives = args[0][1:]
            else:
                if len(kwargs) != 1 or not set(kwargs) <= {"api_key", "api_key_readonly"}:
                    raise ValueError("unbound IR exact lookup")
                alternatives = (tuple(kwargs.items()),)
            matches = [row for row in self.ir_projects.values() if
                       any(all(row.fields[k] == value for k, value in terms) for terms in alternatives)]
            if not matches:
                raise self.QueryMiss()
            if len(matches) != 1:
                raise ValueError("ambiguous IR credential")
            return matches[0]
        if name == "get_object_or_404":
            if args != [self.Ref("CheckModel")] or set(kwargs) != {"code"}:
                raise ValueError("unexpected IR check lookup")
            row = next((r for r in self.records.values() if r["code"] == kwargs["code"]), None)
            if row is None:
                raise self.NotFound()
            return self.Record("Check", dict(row))
        if name in ("Check.to_dict", "Check.save", "Check.create_flip"):
            f = ref.receiver.fields
            if f["id"] not in self.records:
                raise ValueError("unowned IR record")
            if name == "Check.create_flip":
                if args != ["new"] or set(kwargs) != {"mark_as_processed"} or kwargs["mark_as_processed"] is not True:
                    raise ValueError("unbound IR event arguments")
                self.events.append((f["id"], "new", 1))
                self.effects.append("flip")
                return None
            if name == "Check.save":
                if args or kwargs != {"update_fields": ("status", "last_start", "last_ping", "alert_after")}:
                    raise ValueError("unbound IR save columns")
                for field in kwargs["update_fields"]:
                    self.records[f["id"]][field] = f[field]
                self.effects.append("save")
                return None
            if args or set(kwargs) not in ({"readonly", "v"}, {"v"}):
                raise ValueError("unbound IR serializer arguments")
            if type(kwargs["v"]) is not int or kwargs["v"] not in (1, 2, 3):
                raise ValueError("unbound IR version")
            if "readonly" in kwargs and type(kwargs["readonly"]) is not bool:
                raise ValueError("unbound IR readonly flag")
            self.serializers.append({"check_id": f["id"], "project_id": f["project_id"], **kwargs})
            self.effects.append("serialize")
            return {"owned_serializer_boundary": {"check_id": f["id"], "status": f["status"]}}
        if name == "resume":
            return self.Body(self.nodes["resume"], self, self.bindings(True)).run(args)
        if name in ("JsonResponse", "HttpResponse"):
            if len(args) != 1 or not set(kwargs) <= {"status"}:
                raise ValueError("unbound IR response arguments")
            return SimpleNamespace(status_code=kwargs.get("status", 200), payload=args[0])
        if name == "HttpResponseForbidden":
            if args or kwargs:
                raise ValueError("unexpected denial arguments")
            return SimpleNamespace(status_code=403, payload=None)
        raise ValueError("unreviewed IR primitive: " + name)

    def invoke(self, spec, target, *, write=False):
        self.effects, self.serializers, self.manager_returns = [], [], []
        self.resolved = None
        req = self.Record("Request", {"method": spec["method"], "headers": dict(spec["headers"]),
                                    "body": bytes.fromhex(spec["body_hex"]), "path_info": spec["path_info"]})
        before = self.snapshot()
        machine = self.Machine(self.programs, self.bindings(write), self)
        try:
            status = machine.call(self.Ref("authorize.wrapper" if write else "authorize_read.wrapper"), [req, code(target)]).status_code
        except self.NotFound:
            status = 404
        current = req.fields.get("project")
        observation = {"status": status, "project": None if current is None else current.fields["id"],
                       "readonly": req.fields.get("readonly"), "version": req.fields.get("v"),
                       "exact_resolved_identity": current is not None and current is self.resolved,
                       "manager_returns": list(self.manager_returns), "serializers": list(self.serializers),
                       "effects": list(self.effects)}
        if write:
            after = self.snapshot()
            observation.update(before=self.mask(before), after=self.mask(after), store=after,
                               store_changed=not typed_equal(before, after), event_delta=len(after["events"]) - len(before["events"]),
                               store_invariant=self.invariant(after))
        return observation

    def resume(self, symbol):
        return self.invoke(request(self.form, symbol["key"], method="POST"), symbol["target"], write=True)


def compare_healthchecks(base, nodes):
    validate_fixture_cohort(base["healthchecks_reads"], read_fixtures(), health_observation, "healthchecks_reads")
    validate_resume_graphs(base["healthchecks_resume"])
    read_rows, graph_rows = [], []
    by_id = {r["id"]: r["observation"] for r in base["healthchecks_reads"]}
    for form in ("plain", "stored_mac"):
        session = IRSession(form, nodes)
        try:
            for fixture in read_fixtures():
                if fixture["form"] != form:
                    continue
                got = session.invoke(fixture["request"], fixture["target"])
                read_rows.append({"id": fixture["id"], "production": got, "agrees": typed_equal(got, by_id[fixture["id"]])})
            symbols = resume_symbols()
            graph = next(r for r in base["healthchecks_resume"] if r["form"] == form)
            for row in graph["rows"]:
                session.reset()
                prefix = [session.resume(symbols[i]) for i in row["prefix_indices"]]
                got = session.resume(symbols[row["index"]])
                graph_rows.append({"form": form, "state": row["state"], "index": row["index"],
                                   "production": got, "prefix_observations": prefix,
                                   "agrees": typed_equal(got, row["observation"]) and typed_equal(prefix, row["prefix_observations"])})
        finally:
            session.close()
    return read_rows, graph_rows


def compare_pretix(base):
    validate_fixture_cohort(base["pretix"], pretix_fixtures(), pretix_observation, "pretix")
    import pretix_event_profile as production
    compiled = production.programs(production.source())
    rows = []
    for fixture, direct in zip(pretix_fixtures(), base["pretix"], strict=True):
        context = {**fixture, "authenticated": False, "token_kind": "TeamAPIToken", "validated_active_token": True,
                   "resolved_view_contract": "event.items"}
        got, meta = production.observe(context, compiled)
        want = {k: direct["observation"][k] for k in ("allow", "event", "organizer", "permissions")}
        rows.append({"id": fixture["id"], "production": got, "meta": meta,
                     "agrees": typed_equal(got, want) and typed_equal(meta["exact_event_identity"], direct["observation"]["exact_event_identity"])})
    return rows


def compare_wger(base):
    validate_fixture_cohort(base["wger_owner_insert"], wger_fixtures(), wger_observation, "wger_owner_insert")
    import owner_insert as production
    got = production.run()
    rows = []
    for fixture, produced, direct in zip(wger_fixtures(), got["rows"], base["wger_owner_insert"], strict=True):
        observed = direct["observation"]
        rows.append({"id": fixture["id"], "production": produced,
                     "agrees": typed_equal(produced["actor"], fixture["actor"]) and typed_equal(produced["supplied_owner"], fixture["supplied_owner"]) and
                     typed_equal(produced["allowed"], observed["allowed"]) and typed_equal(produced["observed_rows"], observed["rows"]) and
                     typed_equal(produced["save_calls"], len(observed["saves"])) and
                     typed_equal(produced["exact_request_user_transferred"], bool(observed["saves"]) and all(r["exact_request_user"] for r in observed["saves"]))})
    if len(rows) != 16:
        raise ValueError("Wger comparison domain incomplete")
    return rows


def diagnose_stateful(base):
    validate_resume_graphs(base["healthchecks_resume"])
    from language import normalize
    from source_family import diagnose_source_family
    from baseline_checks import ordinary_bfs
    # This policy is separately declared from observed tables. Its owner aliases
    # are fixed across a whole trace and its bits record successful resumptions.
    policy = normalize({"principals": list(("1w", "1r", "2w", "2r", "3w", "3r", "missing")),
                        "resources": ["check-1", "check-2", "check-3", "absent"], "actions": ["resume"],
                        "roles": ["project-1", "project-2", "project-3"],
                        "members": [[f"{i}w", f"project-{i}"] for i in (1, 2, 3)],
                        "state": [[f"resumed-{i}", False] for i in (1, 2, 3)],
                        "aliases": [{"name": f"owner-{i}", "kind": "role", "candidates": [f"project-{j}" for j in (1, 2, 3)]} for i in (1, 2, 3)],
                        "rules": [{"decision": "allow", "guard": [{"field": "resource", "name": f"check-{i}", "negated": False},
                                                                     {"field": "role", "alias": f"owner-{i}", "negated": False},
                                                                     {"field": "state", "name": f"resumed-{i}", "value": False}],
                                   "updates": [{"name": f"resumed-{i}", "value": True}]} for i in (1, 2, 3)]})
    symbols = resume_symbols()
    source_alphabet = [[s["key"], "absent" if s["target"] == 99 else f"check-{s['target']}", "resume"] for s in symbols]
    alphabet = [list(r) for r in itertools.product(policy["principals"], policy["resources"], policy["actions"])]
    # normalize() canonically orders declared names; preserve explicit maps
    # between that interface and the independent collector's fixture order.
    source_to_model = {i: alphabet.index(symbol) for i, symbol in enumerate(source_alphabet)}
    model_to_source = {v: k for k, v in source_to_model.items()}
    nodes, _ = nodes_and_manifest()
    profiles = []
    for observed in base["healthchecks_resume"]:
        table = [[None] * len(alphabet) for _ in range(8)]
        for edge in observed["rows"]:
            o = edge["observation"]
            table[edge["state"]][source_to_model[edge["index"]]] = ["allow" if o["status"] == 200 else "deny", o["after"]]
        if any(cell is None for row in table for cell in row):
            raise ValueError("incomplete observed transition table")
        model = {"state_names": [r[0] for r in policy["state"]], "alphabet": alphabet,
                 "observations": list(range(8)), "initial": 0, "transitions": table}
        diagnosis = diagnose_source_family(policy, model)
        correct = {f"owner-{i}": f"project-{i}" for i in (1, 2, 3)}
        if diagnosis["matching_interpretations"] != [correct] or diagnosis["strata"] != {"1": 26, "infinity": 1}:
            raise ValueError("stateful observed family differs")
        fixed = deepcopy(policy)
        for alias in fixed["aliases"]:
            alias["candidates"] = [correct[alias["name"]]]
        bfs = ordinary_bfs(normalize(fixed), model)
        if bfs["equivalent"] is not True:
            raise ValueError("fixed correct binding BFS differs")
        session = HealthSession(observed["form"], nodes)
        witnesses = []
        try:
            for profile in diagnosis["profiles"]:
                if profile["equivalent"]:
                    continue
                session.reset()
                trace = [session.resume(symbols[model_to_source[i]]) for i in profile["indices"]]
                if any(not typed_equal(["allow" if o["status"] == 200 else "deny", o["after"]], expected["target"])
                       for o, expected in zip(trace, profile["trace"], strict=True)):
                    raise ValueError("diagnostic witness does not execute in CPython collector")
                witnesses.append({"binding": profile["binding"], "indices": profile["indices"], "observations": trace})
        finally:
            session.close()
        profiles.append({"form": observed["form"], "policy": policy, "model": model,
                         "source_fixture_index_to_model_index": source_to_model,
                         "diagnosis": diagnosis, "fixed_reference_bfs": bfs, "cpython_witness_replays": witnesses})
    return profiles


def compare(base):
    validate_observations(base)
    nodes, _ = nodes_and_manifest()
    production_imports()
    reads, graph = compare_healthchecks(base, nodes)
    result = {"healthchecks_reads": reads, "healthchecks_resume": graph,
              "pretix": compare_pretix(base), "wger_owner_insert": compare_wger(base)}
    for profile, rows in result.items():
        if not rows or not all(r["agrees"] is True for r in rows):
            raise ValueError("fresh production comparison disagrees: " + profile)
    result["stateful_diagnosis"] = diagnose_stateful(base)
    return result
