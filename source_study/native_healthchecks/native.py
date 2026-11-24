"""Collect actual original-module HTTP requests and SQLite reads in a subprocess."""
import argparse
from contextlib import closing
import gzip
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
from datetime import timedelta

from . import contracts


def raw_store(database):
    tables = {"projects": "accounts_project", "checks": "api_check", "flips": "api_flip", "profiles": "accounts_profile", "channels": "api_channel"}
    database = Path(database).resolve()
    if not database.is_file(): raise ValueError("retained native SQLite file is missing")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        return {name: [dict(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY id")] for name, table in tables.items()}


def collect_case(arm, key_format, api_version, configuration_name, directory, limit=None):
    import django
    from django.conf import settings
    from django.contrib.auth.models import User
    from django.core.management import call_command
    from django.db import connection
    from django.test import Client
    from hc.accounts.models import Project, Profile
    from hc.api.models import Check, Channel
    connection.close()
    database = directory / (key_format + "-api-" + str(api_version) + "-" + configuration_name + ".sqlite")
    if database.exists(): raise ValueError("native collection requires a fresh SQLite path")
    settings.DATABASES["default"]["NAME"] = str(database)
    connection.settings_dict["NAME"] = str(database)
    call_command("migrate", run_syncdb=True, verbosity=0)
    owners, keys, objects = {}, {}, {}
    for name in ("alice", "bob"):
        user = User.objects.create(username=name)
        Profile.objects.create(user=user)
        project = Project(owner=user, name=name, badge_key=name)
        project.set_ping_key()
        if key_format == "hashed":
            rw, ro = project.set_api_key(), project.set_api_key_readonly()
        else:
            rw, ro = ("A" * 32, "R" * 32) if name == "alice" else ("B" * 32, "S" * 32)
            project.api_key, project.api_key_readonly = rw, ro
        project.save()
        check = Check.objects.create(project=project, name=name + " check", status="new", kind="simple",
            timeout=timedelta(seconds=86400), grace=timedelta(seconds=3600), last_start=None,
            last_ping=None, alert_after=None, last_duration=None, **contracts.CHECK_SCALARS)
        channel = Channel.objects.create(project=project)
        check.channel_set.add(channel)
        owners[name] = dict(project_id=project.pk, check_id=check.pk, check_uuid=str(check.code), badge_uuid=str(check.badge_key), channel_uuid=str(channel.code), rw=rw, ro=ro)
        keys[name + "_rw"], keys[name + "_ro"] = rw, ro
        objects[name] = project
    case = dict(arm=arm, format=key_format, api_version=api_version, configuration=configuration_name, owners=owners,
                initial=raw_store(database), records=[], sqlite_file=database.name)
    client = Client(enforce_csrf_checks=True, raise_request_exception=False)
    for op in contracts.protocol()[:limit]:
        before = raw_store(database)
        statements = []
        def capture(execute, statement, params, many, context):
            statements.append(statement)
            return execute(statement, params, many, context)
        with connection.execute_wrapper(capture):
            if op["kind"] == "rotate":
                slot = contracts.route_slot(contracts.configurations()[configuration_name], op["owner"] + "_" + op["role"])
                name, role = slot.split("_")
                project = objects[name]
                returned = project.set_api_key() if role == "rw" else project.set_api_key_readonly()
                project.save(update_fields=("api_key" if role == "rw" else "api_key_readonly",))
                keys["old_" + slot], keys[slot] = keys[slot], returned
                record = dict(returned_key=returned, producer_project=name, producer_role=role, producer_class=type(project).__module__ + "." + type(project).__name__)
            else:
                request = contracts.request_spec(case, op, keys)
                kwargs = {} if request["header_key"] is None else {"HTTP_X_API_KEY": request["header_key"]}
                manager_objects = []
                def profile(frame, event, value):
                    if event == "return" and frame.f_code.co_name == "for_api_key" and frame.f_globals.get("__name__") == "hc.accounts.models":
                        manager_objects.append(value)
                saved_profile = sys.getprofile()
                sys.setprofile(profile)
                try:
                    if op["method"] == "POST":
                        response = client.post(request["path"], request["body"], content_type="application/json", **kwargs)
                    else:
                        response = getattr(client, op["method"].lower())(request["path"], **kwargs)
                finally:
                    sys.setprofile(saved_profile)
                actual = response.wsgi_request
                project = getattr(actual, "project", None)
                body = response.content.decode("utf-8")
                record = dict(request=dict(method=actual.method, path=actual.path_info, header_key=actual.headers.get("X-Api-Key"), body=actual.body.decode("utf-8")),
                    http_status=response.status_code, response=json.loads(body) if response.headers.get("Content-Type", "").startswith("application/json") else None,
                    response_text=body, response_headers=dict(response.headers), response_cookies={name: value.OutputString() for name, value in response.cookies.items()}, request_project_id=None if project is None else project.pk,
                    request_project_class=None if project is None else type(project).__module__ + "." + type(project).__name__,
                    request_readonly=getattr(actual, "readonly", None), request_api_version=getattr(actual, "v", None),
                    source_manager_returns=[None if obj is None else dict(project_id=obj.pk, native_class=type(obj).__module__ + "." + type(obj).__name__) for obj in manager_objects],
                    manager_result_is_request_project=None if project is None else bool(manager_objects and manager_objects[-1] is project))
        record.update(operation=op, before=before, after=raw_store(database), sql=statements)
        case["records"].append(record)
    connection.close()
    return case


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=contracts.ARMS, required=True)
    parser.add_argument("--one", nargs=3, metavar=("FORMAT", "API", "BINDING"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError("native output directory already exists")
    args.output.mkdir(parents=True)
    sys.path.insert(0, str(args.source.resolve()))
    os.environ["DJANGO_SETTINGS_MODULE"] = __package__ + ".settings"
    os.environ["HEALTHCHECKS_DB"] = str(args.output / "unused.sqlite")
    logging.getLogger("django.request").setLevel(logging.CRITICAL)
    import django
    django.setup()
    combinations = [(args.one[0], int(args.one[1]), args.one[2])] if args.one else [(fmt, api, configuration) for fmt in contracts.FORMATS for api in contracts.API_VERSIONS for configuration in contracts.configurations()]
    cases = [collect_case(args.arm, fmt, api, configuration, args.output, args.limit) for fmt, api, configuration in combinations]
    loaded = {name: str(Path(module.__file__).resolve()) for name, module in sys.modules.items() if name == "hc" or name.startswith("hc.") if getattr(module, "__file__", None)}
    if not all(Path(path).is_relative_to(args.source.resolve()) for path in loaded.values()):
        raise ValueError("application import escaped the selected complete source tree")
    document = dict(arm=args.arm, cases=cases, imported_application_modules=loaded,
                    framework=django.get_version(), python=sys.version, sqlite=sqlite3.sqlite_version,
                    source_imports_replaced=False, original_models=True, native_http_client=True,
                    selected_api_boundary=True, full_service_deployment=False)
    (args.output / "observations.json.gz").write_bytes(gzip.compress(json.dumps(document, sort_keys=True, separators=(",", ":")).encode(), mtime=0))
    print(json.dumps(dict(arm=args.arm, cases=len(cases), operations=sum(len(c["records"]) for c in cases), imported_modules=len(loaded))))


if __name__ == "__main__":
    main()
