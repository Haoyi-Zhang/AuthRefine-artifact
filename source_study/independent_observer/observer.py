"""CPython observations on new owned fixtures; production code is not imported.

Only selected source function definitions execute. Stand-ins implement the
documented query, response, serializer-boundary and persistence contracts.
This does not run Django/DRF, an application module, a server or the historical
direct-observer experiment. The separately gated native replay is untouched.
"""
from collections import Counter, deque
from contextlib import closing
import hmac
import json
import sqlite3
from types import SimpleNamespace, MethodType

from .fixtures import SECRET, code, credential, projects, request, read_fixtures, resume_symbols, pretix_fixtures, wger_fixtures
from .source import nodes_and_manifest, compile_functions
from .evidence import validate_observations
from source_study.observation_evidence import typed_equal


class OutsideBoundary(ValueError):
    pass


class MissingCheck(Exception):
    pass


class Response:
    def __init__(self, payload=None, status=200):
        self.payload, self.status_code = payload, status


class Q:
    def __init__(self, **filters):
        self.alternatives = [filters]

    def __or__(self, other):
        if not isinstance(other, Q):
            raise OutsideBoundary("query OR requires the owned predicate")
        result = Q()
        result.alternatives = self.alternatives + other.alternatives
        return result

    def matches(self, row):
        return any(all(getattr(row, k) == v for k, v in branch.items()) for branch in self.alternatives)


class HealthSession:
    def __init__(self, form, nodes, *, control=None):
        if form not in ("plain", "stored_mac"):
            raise OutsideBoundary("unknown credential form")
        self.form, self.nodes, self.control = form, nodes, control
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE owned_check(id INTEGER PRIMARY KEY, code TEXT, project_id INTEGER, status TEXT, last_start TEXT, last_ping TEXT, alert_after TEXT)")
        self.db.execute("CREATE TABLE owned_event(check_id INTEGER, status TEXT, processed INTEGER)")
        self.effects, self.serializers, self.manager_returns = [], [], []
        self.resolved = None
        session = self

        class Project:
            class DoesNotExist(Exception):
                pass

            def __init__(self, fields):
                self.__dict__.update(fields)

            def compare_api_key(self, key):
                return session.functions["compare_key"](self, key)

        class Manager:
            def filter(self, **filters):
                if len(filters) != 1:
                    raise OutsideBoundary("one owned prefix filter required")
                field, prefix = next(iter(filters.items()))
                if field not in ("api_key__startswith", "api_key_readonly__startswith"):
                    raise OutsideBoundary("unknown prefix query")
                attr = field.removesuffix("__startswith")
                return [row for row in session.projects.values() if getattr(row, attr).startswith(prefix)]

            def get(self, *predicates, **filters):
                if predicates and (len(predicates) != 1 or filters or not isinstance(predicates[0], Q)):
                    raise OutsideBoundary("unknown disjunctive query")
                if not predicates and (len(filters) != 1 or not set(filters) <= {"api_key", "api_key_readonly"}):
                    raise OutsideBoundary("unknown exact query")
                rows = [r for r in session.projects.values() if
                        (predicates[0].matches(r) if predicates else all(getattr(r, k) == v for k, v in filters.items()))]
                if not rows:
                    raise Project.DoesNotExist()
                if len(rows) != 1:
                    raise OutsideBoundary("ambiguous owned credential")
                return rows[0]

            def for_api_key(self, key, accept_rw, accept_ro):
                value = session.functions["manager"](self, key, accept_rw, accept_ro)
                session.resolved = value
                session.manager_returns.append(None if value is None else value.id)
                return value

        class Check:
            def __init__(self, row):
                self.__dict__.update(zip(("id", "code", "project_id", "status", "last_start", "last_ping", "alert_after"), row))

            def to_dict(self, **kwargs):
                if set(kwargs) not in ({"readonly", "v"}, {"v"}):
                    raise OutsideBoundary("unknown serializer boundary")
                if type(kwargs.get("v")) is not int or not 1 <= kwargs["v"] <= 3:
                    raise OutsideBoundary("unknown API version")
                if "readonly" in kwargs and type(kwargs["readonly"]) is not bool:
                    raise OutsideBoundary("non-Boolean readonly argument")
                session.serializers.append({"check_id": self.id, "project_id": self.project_id, **kwargs})
                session.effects.append("serialize")
                return {"owned_serializer_boundary": {"check_id": self.id, "status": self.status}}

            def create_flip(self, status, *, mark_as_processed):
                if status != "new" or mark_as_processed is not True:
                    raise OutsideBoundary("unknown event primitive")
                session.db.execute("INSERT INTO owned_event VALUES(?,?,?)", (self.id, status, 1))
                session.effects.append("flip")

            def save(self, *, update_fields):
                if update_fields != ("status", "last_start", "last_ping", "alert_after"):
                    raise OutsideBoundary("unknown save columns")
                values = tuple(getattr(self, name) for name in update_fields) + (self.id,)
                session.db.execute("UPDATE owned_check SET status=?, last_start=?, last_ping=?, alert_after=? WHERE id=?", values)
                session.effects.append("save")

        self.Project, self.Check = Project, Check
        self.projects = {r["id"]: Project(r) for r in projects(form)}
        Project.objects = Manager()
        self.install(nodes)
        self.reset()

    def install(self, nodes):
        def lookup(model, *, code):
            if model is not self.Check:
                raise OutsideBoundary("unknown model lookup")
            row = self.db.execute("SELECT id,code,project_id,status,last_start,last_ping,alert_after FROM owned_check WHERE code=?", (code,)).fetchone()
            if row is None:
                raise MissingCheck()
            return self.Check(row)

        globals = {"Project": self.Project, "Check": self.Check, "Q": Q, "json": json, "hmac": hmac,
                   "settings": SimpleNamespace(SECRET_KEY=SECRET), "get_object_or_404": lookup,
                   "JsonResponse": Response, "HttpResponse": Response,
                   "HttpResponseForbidden": lambda: Response(status=403)}
        self.functions = compile_functions({k: nodes[k] for k in ("manager", "compare_key", "error", "version", "authorize", "authorize_read", "get_check", "resume")}, globals)
        for fn in self.functions.values():
            fn.__globals__.update(error=self.functions["error"], _get_api_version=self.functions["version"])
        self.read_entry = self.functions["authorize_read"](self.functions["get_check"])
        self.write_entry = self.functions["authorize"](self.functions["resume"])

    def close(self):
        self.db.close()

    def reset(self):
        self.db.execute("DELETE FROM owned_check")
        self.db.execute("DELETE FROM owned_event")
        self.db.executemany("INSERT INTO owned_check VALUES(?,?,?,?,?,?,?)",
                            [(i, code(i), i, "paused", "start", "ping", "alert") for i in (1, 2, 3)])

    def snapshot(self):
        return {"records": [list(r) for r in self.db.execute("SELECT id,code,project_id,status,last_start,last_ping,alert_after FROM owned_check ORDER BY id")],
                "events": [list(r) for r in self.db.execute("SELECT check_id,status,processed FROM owned_event ORDER BY check_id,status,processed")]}

    @staticmethod
    def mask(snapshot):
        return sum(1 << (row[0] - 1) for row in snapshot["records"] if row[3] == "new")

    @staticmethod
    def invariant(snapshot):
        mask = HealthSession.mask(snapshot)
        expected_records = [[i, code(i), i, "new" if mask & (1 << (i - 1)) else "paused",
                             *([None] * 3 if mask & (1 << (i - 1)) else ["start", "ping", "alert"])] for i in (1, 2, 3)]
        expected_events = [[i, "new", 1] for i in (1, 2, 3) if mask & (1 << (i - 1))]
        return typed_equal(snapshot, {"records": expected_records, "events": expected_events})

    def invoke(self, spec, target, *, write=False):
        self.effects, self.serializers, self.manager_returns = [], [], []
        self.resolved = None
        req = SimpleNamespace(method=spec["method"], headers=dict(spec["headers"]),
                              body=bytes.fromhex(spec["body_hex"]), path_info=spec["path_info"])
        before = self.snapshot()
        try:
            status = (self.write_entry if write else self.read_entry)(req, code(target)).status_code
        except MissingCheck:
            status = 404
        current = getattr(req, "project", None)
        observation = {"status": status, "project": None if current is None else current.id,
                       "readonly": getattr(req, "readonly", None), "version": getattr(req, "v", None),
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


def observe_reads(nodes):
    rows = []
    for form in ("plain", "stored_mac"):
        session = HealthSession(form, nodes)
        try:
            for fixture in read_fixtures():
                if fixture["form"] == form:
                    rows.append({"id": fixture["id"], "observation": session.invoke(fixture["request"], fixture["target"])})
        finally:
            session.close()
    return rows


def observe_resume_graph(nodes):
    symbols, profiles = resume_symbols(), []
    for form in ("plain", "stored_mac"):
        session = HealthSession(form, nodes)
        paths, rows, queue = {0: []}, [], deque([0])
        try:
            while queue:
                state = queue.popleft()
                for index, symbol in enumerate(symbols):
                    session.reset()
                    prefix = [session.resume(symbols[i]) for i in paths[state]]
                    if session.mask(session.snapshot()) != state or not session.invariant(session.snapshot()):
                        raise ValueError("concrete source prefix did not establish graph state")
                    got = session.resume(symbol)
                    if not got["store_invariant"]:
                        raise ValueError("source store outside declared projection")
                    rows.append({"state": state, "index": index, "prefix_indices": paths[state],
                                 "prefix_observations": prefix, "observation": got})
                    if got["after"] not in paths:
                        paths[got["after"]] = paths[state] + [index]
                        queue.append(got["after"])
            if len(paths) != 8 or len(rows) != 224:
                raise ValueError("resume reachable graph incomplete")
            profiles.append({"form": form, "paths": {str(k): v for k, v in paths.items()}, "rows": rows})
        finally:
            session.close()
    return profiles


class Model:
    def __init__(self, kind, pk, **values):
        self.kind, self.pk = kind, pk
        self.__dict__.update(values)

    def __eq__(self, other):
        return isinstance(other, Model) and self.kind == other.kind and self.pk == other.pk


def observe_pretix(fixture, nodes):
    organizers = {i: Model("Organizer", i, slug=f"o{i}") for i in (1, 2)}
    events = {i: Model("Event", i, slug="b" if i == 2 else "a", organizer=organizers[1 if i != 3 else 2]) for i in (1, 2, 3)}
    handoffs, queries = [], []

    class TeamAPIToken:
        pass

    class InactiveProfile:
        pass

    class EventQuery:
        def __init__(self, filters):
            if set(filters) != {"slug", "organizer__slug"}:
                raise OutsideBoundary("unknown event query")
            self.filters = filters

        def select_related(self, name):
            if name != "organizer":
                raise OutsideBoundary("unknown selected relation")
            return self

        def first(self):
            queries.append(dict(self.filters))
            return next((e for e in events.values() if e.slug == self.filters["slug"] and
                         e.organizer.slug == self.filters["organizer__slug"]), None)

    token = TeamAPIToken()
    token.team = SimpleNamespace(organizer=organizers[1], all_events=fixture["all_events"],
                                 limit_events=SimpleNamespace(all=lambda: [events[i] for i in fixture["limited_events"]]),
                                 event_permission_set=lambda: set(fixture["permissions"]))
    globals = {"SAFE_METHODS": ("GET", "HEAD", "OPTIONS"), "TeamAPIToken": TeamAPIToken,
               "Device": InactiveProfile, "User": InactiveProfile, "OAuthAccessToken": InactiveProfile,
               "Event": SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: EventQuery(kw))),
               "EventPermissionSet": set, "owned_other_organizer": organizers[2]}
    functions = compile_functions({k: nodes[k] for k in ("event_permission", "event_access", "event_grants")}, globals)

    def access(self, organizer, event, **kwargs):
        handoffs.append({"kind": "access", "organizer": organizer.pk, "event": event.pk,
                         "exact_organizer": organizer is event.organizer, "exact_event": event is events[event.pk],
                         "request_is_same": kwargs.get("request") is req})
        return functions["event_access"](self, organizer, event, **kwargs)

    def grants(self, organizer, event):
        handoffs.append({"kind": "grants", "organizer": organizer.pk, "event": event.pk,
                         "exact_organizer": organizer is event.organizer, "exact_event": event is events[event.pk]})
        return functions["event_grants"](self, organizer, event)

    token.has_event_permission, token.get_event_permission_set = MethodType(access, token), MethodType(grants, token)
    target = {"own-a": 1, "own-b": 2, "other": 3, "missing": None}[fixture["query"]]
    selected = events.get(target)
    req = SimpleNamespace(user=SimpleNamespace(is_authenticated=False), auth=token, method=fixture["method"],
                          resolver_match=SimpleNamespace(kwargs={"event": selected.slug if selected else "absent",
                                                                  "organizer": selected.organizer.slug if selected else "o1"}))
    view = SimpleNamespace(permission=None, write_permission="event.items:write")
    allow = functions["event_permission"](SimpleNamespace(), req, view)
    event, organizer, grants = getattr(req, "event", None), getattr(req, "organizer", None), getattr(req, "eventpermset", None)
    return {"allow": allow, "event": None if event is None else event.pk,
            "organizer": None if organizer is None else organizer.pk,
            "permissions": None if grants is None else sorted(grants),
            "exact_event_identity": event is selected, "handoffs": handoffs, "queries": queries}


def observe_wger(fixture, nodes):
    users = {i: SimpleNamespace(pk=i, is_authenticated=i != 3) for i in (1, 2, 3)}
    user = {"user-1": users[1], "user-2": users[2], "unauthenticated-record": users[3], "absent-record": None}[fixture["actor"]]
    req = SimpleNamespace(user=user)
    view = SimpleNamespace(request=req)
    functions = compile_functions({k: nodes[k] for k in ("wger_permission", "wger_create")}, {})
    allowed = bool(functions["wger_permission"](SimpleNamespace(), req, view))
    saves = []
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE owned_routine(id INTEGER PRIMARY KEY,user_id INTEGER,title TEXT)")
        db.execute("INSERT INTO owned_routine VALUES(7,2,'unrelated-row')")

        def save(*, user):
            if user is None or not any(user is value for value in users.values()):
                raise OutsideBoundary("unowned user passed to insert")
            saves.append({"user_id": user.pk, "exact_request_user": user is req.user})
            db.execute("INSERT INTO owned_routine VALUES(8,?,'owned-new-row')", (user.pk,))

        serializer = SimpleNamespace(save=save, client_user=users[fixture["supplied_owner"] or 3])
        if allowed:
            functions["wger_create"](view, serializer)
        rows = [list(r) for r in db.execute("SELECT id,user_id,title FROM owned_routine ORDER BY id")]
    return {"allowed": allowed, "saves": saves, "rows": rows}


def baseline():
    nodes, manifest = nodes_and_manifest()
    reads, graph = observe_reads(nodes), observe_resume_graph(nodes)
    event = [{"id": c["id"], "observation": observe_pretix(c, nodes)} for c in pretix_fixtures()]
    owner = [{"id": c["id"], "observation": observe_wger(c, nodes)} for c in wger_fixtures()]
    return {"source_manifest": manifest, "healthchecks_reads": reads, "healthchecks_resume": graph,
            "pretix": event, "wger_owner_insert": owner}


def control_observations(base):
    validate_observations(base)
    controls = []
    baseline_nodes, _ = nodes_and_manifest()
    for control in ("read_wrong_version", "read_foreign_serializer", "resume_omit_save", "resume_repeat_flip", "resume_stale_ping", "pretix_wrong_organizer", "pretix_omit_grants", "wger_client_owner"):
        nodes, manifest = nodes_and_manifest(control)
        rows = []
        if control.startswith("read_"):
            altered = observe_reads(nodes)
            for original, modified in zip(base["healthchecks_reads"], altered, strict=True):
                if original["id"] != modified["id"]:
                    raise ValueError("control input order differs")
                rows.append((original["id"], original["observation"], modified["observation"], "status"))
        elif control.startswith("resume_"):
            symbols = resume_symbols()
            for profile in base["healthchecks_resume"]:
                session = HealthSession(profile["form"], baseline_nodes)
                try:
                    for original in profile["rows"]:
                        session.install(baseline_nodes)
                        session.reset()
                        for index in original["prefix_indices"]:
                            session.resume(symbols[index])
                        session.install(nodes)
                        modified = session.resume(symbols[original["index"]])
                        identity = f"{profile['form']}-{original['state']}-{original['index']}"
                        rows.append((identity, original["observation"], modified, "status"))
                finally:
                    session.close()
        elif control.startswith("pretix_"):
            for fixture, original in zip(pretix_fixtures(), base["pretix"], strict=True):
                rows.append((fixture["id"], original["observation"], observe_pretix(fixture, nodes), "allow"))
        else:
            for fixture, original in zip(wger_fixtures(), base["wger_owner_insert"], strict=True):
                rows.append((fixture["id"], original["observation"], observe_wger(fixture, nodes), "allowed"))
        changes = [{"id": key, "baseline": a, "modified": b, "response_changed": not typed_equal(a[response], b[response]),
                    "differing_fields": sorted(k for k in set(a) | set(b)
                                              if k not in a or k not in b or not typed_equal(a[k], b[k]))}
                   for key, a, b, response in rows if not typed_equal(a, b)]
        if not changes:
            raise ValueError("executable source control was not detected: " + control)
        controls.append({"control": control, "tested_inputs": len(rows), "changed_observations": len(changes),
                         "response_differences": sum(r["response_changed"] for r in changes),
                         "field_only_differences": sum(not r["response_changed"] for r in changes),
                         "source": next(r for r in manifest["functions"] if r["mutation"]), "rows": changes})
    return controls
