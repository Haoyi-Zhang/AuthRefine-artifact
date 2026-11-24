"""Actual Django execution with a byte-exact SQLite checkpoint per history."""
import argparse
from copy import deepcopy
from datetime import timedelta
import gzip
import json
import logging
import os
from pathlib import Path
import sys

from . import specification as spec
from source_study.native_healthchecks import contracts


def cookies(jar):
    return {key: value.OutputString() for key, value in jar.items()}


def switch_database(path):
    from django.conf import settings
    from django.db import connection
    connection.close()
    settings.DATABASES["default"]["NAME"] = str(path)
    connection.settings_dict["NAME"] = str(path)


def empty_database(directory):
    from django.core.management import call_command
    from django.db import connection
    path = directory / "_schema.sqlite"
    switch_database(path)
    call_command("migrate", run_syncdb=True, verbosity=0)
    connection.close()
    raw = path.read_bytes()
    path.unlink()
    return raw


def create_initial(path, empty, key_format, initial_status):
    from django.contrib.auth.models import User
    from django.db import connection
    from hc.accounts.models import Project, Profile
    from hc.api.models import Check, Channel
    connection.close()
    path.write_bytes(empty)
    switch_database(path)
    owners = {}
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
        check = Check.objects.create(
            project=project, name=name + " check",
            status=initial_status if name == "alice" else "new", kind="simple",
            timeout=timedelta(seconds=86400), grace=timedelta(seconds=3600),
            last_start=None, last_ping=None, alert_after=None, last_duration=None,
            **contracts.CHECK_SCALARS)
        channel = Channel.objects.create(project=project)
        check.channel_set.add(channel)
        owners[name] = dict(project_id=project.pk, check_id=check.pk,
                            check_uuid=str(check.code), badge_uuid=str(check.badge_key),
                            channel_uuid=str(channel.code), rw=rw, ro=ro)
    connection.close()
    return owners, path.read_bytes()


def collect(arm, key_format, api_version, initial_status, directory, empty, replay_word=None):
    from django.db import connection
    from django.test import Client
    directory.mkdir(parents=True)
    runtime = directory / "_running.sqlite"
    owners, initial_bytes = create_initial(runtime, empty, key_format, initial_status)
    case = dict(arm=arm, format=key_format, api_version=api_version, initial_status=initial_status,
                owners=owners, initial=spec.sqlite_snapshot(initial_bytes), records=[],
                replay_word=replay_word, checkpoints={})
    keys = {owner + "_" + role: row[role] for owner, row in owners.items() for role in ("ro", "rw")}
    declared = spec.words()[1:] if replay_word is None else [tuple(replay_word[:n]) for n in range(1, len(replay_word) + 1)]
    checkpoint_bytes = {(): initial_bytes}
    snapshot_by_word = {(): case["initial"]}
    cookie_jars = {(): Client(enforce_csrf_checks=True).cookies}

    def save_checkpoint(word, raw):
        relative = Path("checkpoints") / (spec.name(word) + ".sqlite.gz")
        destination = directory / relative
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(gzip.compress(raw, mtime=0))
        case["checkpoints"][spec.name(word)] = dict(path=str(relative), sqlite_bytes=len(raw))

    save_checkpoint((), initial_bytes)
    for word in declared:
        parent = word[:-1]
        connection.close()
        runtime.write_bytes(checkpoint_bytes[parent])
        if runtime.read_bytes() != checkpoint_bytes[parent]:
            raise ValueError("SQLite checkpoint restoration was not byte exact")
        switch_database(runtime)
        before = spec.sqlite_snapshot(runtime.read_bytes())
        if not spec.typed_equal(before, snapshot_by_word[parent]):
            raise ValueError("restored complete physical history differs")
        client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        client.cookies = deepcopy(cookie_jars[parent])
        before_cookies = cookies(client.cookies)
        op = spec.OPERATIONS[word[-1]]
        request = contracts.request_spec({**case, "configuration": "identity"}, op, keys)
        kwargs = {"HTTP_X_API_KEY": request["header_key"]}
        manager_objects, statements = [], []

        def capture(execute, statement, params, many, context):
            statements.append(dict(statement=statement, params=repr(params), many=many))
            return execute(statement, params, many, context)

        def profile(frame, event, value):
            if event == "return" and frame.f_code.co_name == "for_api_key" and frame.f_globals.get("__name__") == "hc.accounts.models":
                manager_objects.append(value)

        saved_profile = sys.getprofile()
        sys.setprofile(profile)
        try:
            with connection.execute_wrapper(capture):
                if op["method"] == "POST":
                    response = client.post(request["path"], request["body"], content_type="application/json", **kwargs)
                else:
                    response = client.get(request["path"], **kwargs)
        finally:
            sys.setprofile(saved_profile)
        actual = response.wsgi_request
        project = getattr(actual, "project", None)
        body = response.content.decode("utf-8")
        record = dict(
            word=list(word), operation=op, checkpoint_exact_copy=True,
            request=dict(method=actual.method, path=actual.path_info,
                         header_key=actual.headers.get("X-Api-Key"), body=actual.body.decode("utf-8")),
            http_status=response.status_code,
            response=json.loads(body) if response.headers.get("Content-Type", "").startswith("application/json") else None,
            response_text=body, response_headers=dict(response.headers),
            response_cookies=cookies(response.cookies),
            request_project_id=None if project is None else project.pk,
            request_project_class=None if project is None else type(project).__module__ + "." + type(project).__name__,
            request_readonly=getattr(actual, "readonly", None), request_api_version=getattr(actual, "v", None),
            source_manager_returns=[None if obj is None else dict(project_id=obj.pk,
                native_class=type(obj).__module__ + "." + type(obj).__name__) for obj in manager_objects],
            manager_result_is_request_project=None if project is None else bool(manager_objects and manager_objects[-1] is project),
            client_cookies_before=before_cookies, client_cookies_after=cookies(client.cookies), before=before, sql=statements,
        )
        connection.close()
        after_bytes = runtime.read_bytes()
        after = spec.sqlite_snapshot(after_bytes)
        record["after"] = after
        checkpoint_bytes[word], snapshot_by_word[word] = after_bytes, after
        cookie_jars[word] = deepcopy(client.cookies)
        save_checkpoint(word, after_bytes)
        case["records"].append(record)
    connection.close()
    runtime.unlink()
    spec.admit(case, replay_word=replay_word)
    spec.write(directory / "observations.json.gz", case)
    return case


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=spec.ARMS, required=True)
    parser.add_argument("--one", nargs=3, metavar=("FORMAT", "API", "INITIAL"))
    parser.add_argument("--replay-plan", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("native tree collection requires a fresh directory")
    args.output.mkdir(parents=True)
    sys.path.insert(0, str(args.source.resolve()))
    os.environ["DJANGO_SETTINGS_MODULE"] = "source_study.native_healthchecks.settings"
    os.environ["HEALTHCHECKS_DB"] = str(args.output / "_unused.sqlite")
    logging.getLogger("django.request").setLevel(logging.CRITICAL)
    import django
    django.setup()
    empty = empty_database(args.output)
    if args.replay_plan:
        plan = spec.read(args.replay_plan)
    else:
        grid = [tuple(args.one)] if args.one else [(fmt, api, status) for fmt in spec.FORMATS for api in spec.API_VERSIONS for status in spec.INITIAL_STATUSES]
        plan = [dict(format=fmt, api_version=int(api), initial_status=status, word=None,
                     directory=fmt + "-api-" + str(api) + "-" + status) for fmt, api, status in grid]
    rows = []
    for request in plan:
        case = collect(args.arm, request["format"], request["api_version"], request["initial_status"],
                       args.output / request["directory"], empty, request["word"])
        rows.append(dict(directory=request["directory"], format=case["format"], api_version=case["api_version"],
                         initial_status=case["initial_status"], word=request["word"], edges=len(case["records"])))
    loaded = {name: str(Path(module.__file__).resolve()) for name, module in sys.modules.items()
              if name == "hc" or name.startswith("hc.") if getattr(module, "__file__", None)}
    if not all(Path(path).is_relative_to(args.source.resolve()) for path in loaded.values()):
        raise ValueError("native application import escaped its selected source closure")
    receipt = dict(arm=args.arm, cases=rows, imported_application_modules=loaded, framework=django.get_version(),
                   python=sys.version, source_imports_replaced=False, complete_sqlite_checkpoints=True,
                   checkpoint_clock_restored=False, cookie_state_preserved=True)
    spec.write(args.output / "collection.json", receipt)
    print(spec.canonical(dict(arm=args.arm, cases=len(rows), native_http_requests=sum(row["edges"] for row in rows),
                             imported_modules=len(loaded))))


if __name__ == "__main__":
    main()
