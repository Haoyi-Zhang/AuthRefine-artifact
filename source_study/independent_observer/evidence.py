"""Schema and complete-domain checks for the independent source-body study."""
from source_study.observation_evidence import (
    boolean, fixture_rows, integer, object_fields, require, sequence, string, typed_equal,
)
from .fixtures import code, pretix_fixtures, read_fixtures, resume_symbols, wger_fixtures


COHORTS = ("healthchecks_reads", "healthchecks_resume", "pretix", "wger_owner_insert")


def health_observation(value, where, *, write=False):
    fields = ("status", "project", "readonly", "version", "exact_resolved_identity",
              "manager_returns", "serializers", "effects")
    if write:
        fields += ("before", "after", "store", "store_changed", "event_delta", "store_invariant")
    object_fields(value, fields, where)
    integer(value["status"], where + ".status")
    integer(value["project"], where + ".project", minimum=1, maximum=3, nullable=True)
    boolean(value["readonly"], where + ".readonly", nullable=True)
    integer(value["version"], where + ".version", minimum=1, maximum=3, nullable=True)
    boolean(value["exact_resolved_identity"], where + ".exact_resolved_identity")
    for item in sequence(value["manager_returns"], where + ".manager_returns"):
        integer(item, where + ".manager_return", minimum=1, maximum=3, nullable=True)
    for item in sequence(value["effects"], where + ".effects"):
        string(item, where + ".effect")
    serializer_fields = ("check_id", "project_id", "v") if write else ("check_id", "project_id", "readonly", "v")
    for item in sequence(value["serializers"], where + ".serializers"):
        object_fields(item, serializer_fields, where + ".serializer")
        for name in ("check_id", "project_id", "v"):
            integer(item[name], where + ".serializer." + name, minimum=1, maximum=3)
        if not write:
            boolean(item["readonly"], where + ".serializer.readonly")
    if not write:
        return
    for name in ("before", "after"):
        integer(value[name], where + "." + name, minimum=0, maximum=7)
    integer(value["event_delta"], where + ".event_delta", minimum=0)
    boolean(value["store_changed"], where + ".store_changed")
    boolean(value["store_invariant"], where + ".store_invariant")
    store = value["store"]
    object_fields(store, ("records", "events"), where + ".store")
    records = sequence(store["records"], where + ".store.records")
    require(len(records) == 3, where, "complete owned record vector required")
    for index, record in enumerate(records, 1):
        sequence(record, where + ".store.record")
        require(len(record) == 7, where, "persisted record fields differ")
        require(typed_equal(record[:3], [index, code(index), index]), where, "persisted record identity differs")
        string(record[3], where + ".store.status")
        for item in record[4:]:
            string(item, where + ".store.timestamp", nullable=True)
    for record in sequence(store["events"], where + ".store.events"):
        sequence(record, where + ".store.event")
        require(len(record) == 3, where, "persisted event fields differ")
        integer(record[0], where + ".store.event.check", minimum=1, maximum=3)
        string(record[1], where + ".store.event.status")
        integer(record[2], where + ".store.event.processed", minimum=0, maximum=1)


def pretix_observation(value, where):
    object_fields(value, ("allow", "event", "organizer", "permissions", "exact_event_identity",
                          "handoffs", "queries"), where)
    boolean(value["allow"], where + ".allow")
    integer(value["event"], where + ".event", minimum=1, maximum=3, nullable=True)
    integer(value["organizer"], where + ".organizer", minimum=1, maximum=2, nullable=True)
    if value["permissions"] is not None:
        for item in sequence(value["permissions"], where + ".permissions"):
            string(item, where + ".permission")
    boolean(value["exact_event_identity"], where + ".exact_event_identity")
    for item in sequence(value["handoffs"], where + ".handoffs"):
        require(type(item) is dict and item.get("kind") in ("access", "grants"), where, "handoff kind differs")
        fields = ("kind", "organizer", "event", "exact_organizer", "exact_event")
        if item["kind"] == "access":
            fields += ("request_is_same",)
        object_fields(item, fields, where + ".handoff")
        integer(item["organizer"], where + ".handoff.organizer", minimum=1, maximum=2)
        integer(item["event"], where + ".handoff.event", minimum=1, maximum=3)
        for name in ("exact_organizer", "exact_event", *(("request_is_same",) if item["kind"] == "access" else ())):
            boolean(item[name], where + ".handoff." + name)
    for query in sequence(value["queries"], where + ".queries"):
        object_fields(query, ("organizer__slug", "slug"), where + ".query")
        for item in query.values():
            string(item, where + ".query.value")


def wger_observation(value, where):
    object_fields(value, ("allowed", "rows", "saves"), where)
    boolean(value["allowed"], where + ".allowed")
    for row in sequence(value["rows"], where + ".rows"):
        sequence(row, where + ".row")
        require(len(row) == 3, where, "persisted owner-row fields differ")
        integer(row[0], where + ".row.id", minimum=1)
        integer(row[1], where + ".row.user", minimum=1, maximum=3)
        string(row[2], where + ".row.title")
    for row in sequence(value["saves"], where + ".saves"):
        object_fields(row, ("user_id", "exact_request_user"), where + ".save")
        integer(row["user_id"], where + ".save.user", minimum=1, maximum=3)
        boolean(row["exact_request_user"], where + ".save.exact_request_user")


def validate_fixture_cohort(rows, fixtures, validator, where):
    fixture_rows(rows, fixtures, where)
    for row in rows:
        object_fields(row, ("id", "observation"), where + "." + row["id"])
        validator(row["observation"], where + "." + row["id"])


def validate_resume_graphs(graphs):
    sequence(graphs, "healthchecks_resume")
    require(len(graphs) == 2, "healthchecks_resume", "both credential forms required")
    forms = []
    symbol_count = len(resume_symbols())
    wanted_grid = {(state, index) for state in range(8) for index in range(symbol_count)}
    for graph in graphs:
        object_fields(graph, ("form", "paths", "rows"), "healthchecks_resume")
        string(graph["form"], "healthchecks_resume.form")
        forms.append(graph["form"])
        where = "healthchecks_resume." + graph["form"]
        paths = graph["paths"]
        object_fields(paths, tuple(str(i) for i in range(8)), where + ".paths")
        for path in paths.values():
            for index in sequence(path, where + ".path"):
                integer(index, where + ".path.index", minimum=0, maximum=symbol_count - 1)
        require(paths["0"] == [], where, "initial state requires an empty prefix")
        rows = sequence(graph["rows"], where + ".rows")
        require(len(rows) == len(wanted_grid), where, "complete state/input grid required")
        by_edge = {}
        for row in rows:
            object_fields(row, ("state", "index", "prefix_indices", "prefix_observations", "observation"), where + ".row")
            integer(row["state"], where + ".state", minimum=0, maximum=7)
            integer(row["index"], where + ".index", minimum=0, maximum=symbol_count - 1)
            key = (row["state"], row["index"])
            require(key not in by_edge, where, "duplicate state/input edge")
            by_edge[key] = row["observation"]
            require(typed_equal(row["prefix_indices"], paths[str(row["state"])]), where, "declared prefix differs")
            prefix = sequence(row["prefix_observations"], where + ".prefix_observations")
            require(len(prefix) == len(row["prefix_indices"]), where, "complete prefix observations required")
            for observation in prefix:
                health_observation(observation, where + ".prefix", write=True)
            health_observation(row["observation"], where + ".observation", write=True)
            require(row["observation"]["before"] == row["state"], where, "edge starts at another state")
        require(set(by_edge) == wanted_grid, where, "state/input grid differs")
        for row in rows:
            state = 0
            for index, observed in zip(row["prefix_indices"], row["prefix_observations"], strict=True):
                require(typed_equal(observed, by_edge[(state, index)]), where, "prefix observation differs from graph edge")
                state = observed["after"]
            require(state == row["state"], where, "prefix does not establish declared state")
    require(typed_equal(forms, ["plain", "stored_mac"]), "healthchecks_resume", "credential form identity or order differs")


def validate_observations(base):
    object_fields(base, COHORTS, "direct observations")
    validate_fixture_cohort(base["healthchecks_reads"], read_fixtures(), health_observation, "healthchecks_reads")
    validate_resume_graphs(base["healthchecks_resume"])
    validate_fixture_cohort(base["pretix"], pretix_fixtures(), pretix_observation, "pretix")
    validate_fixture_cohort(base["wger_owner_insert"], wger_fixtures(), wger_observation, "wger_owner_insert")
    return {"healthchecks_reads": len(base["healthchecks_reads"]),
            "healthchecks_resume": sum(len(graph["rows"]) for graph in base["healthchecks_resume"]),
            "pretix": len(base["pretix"]), "wger_owner_insert": len(base["wger_owner_insert"])}
