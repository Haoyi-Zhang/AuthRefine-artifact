"""Read-only recomputation of native trees, core profiles and fresh replays."""
from collections import Counter
import difflib
import gzip
import hashlib
import json
import math
from pathlib import Path

from source_study.native_healthchecks import run as retained
from . import encoding, specification as spec


ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = "<artifact>"


def recorded_path(value):
    """Resolve a public receipt path without requiring the acquisition machine."""
    if not isinstance(value, str):
        raise ValueError("recorded path is not a string")
    if value == PUBLIC_ROOT:
        return ARTIFACT_ROOT
    prefix = PUBLIC_ROOT + "/"
    if value.startswith(prefix):
        return ARTIFACT_ROOT / value[len(prefix):]
    return Path(value)


def canonical_recorded_mapping(mapping):
    if not isinstance(mapping, dict):
        raise ValueError("recorded module mapping is not an object")
    return {name: str(recorded_path(value).resolve()) for name, value in mapping.items()}


def source_check(output):
    evidence = retained.source_identity()
    source_paths = {row["path"] for row in evidence["files"]}
    if len(source_paths) != 34 or len(evidence["files"]) != 34:
        raise ValueError("original source closure path set differs")
    manifest = spec.read(output / "source-controls.json")
    if [row["arm"] for row in manifest] != list(spec.ARMS):
        raise ValueError("source-control arms differ")
    files = 0
    for arm in manifest:
        if set(arm) != {"arm", "patch", "historical_deployment_executed", "current_complete_source_modules", "files"}:
            raise ValueError("source-control declaration fields differ")
        name = arm["arm"]
        if arm["historical_deployment_executed"] is not False or arm["current_complete_source_modules"] is not True:
            raise ValueError("source-control provenance differs")
        paths = [item["path"] for item in arm["files"]]
        if len(paths) != len(set(paths)) or set(paths) != source_paths:
            raise ValueError("source-control paths are duplicated or incomplete")
        expected_patch = ""
        for item in arm["files"]:
            if set(item) != {"path", "bytes", "sha256"}:
                raise ValueError("source-control file receipt fields differ")
            original = (retained.ROOT / "source" / item["path"]).read_bytes()
            expected = original
            if name != "original":
                relative, before, after, count = retained.controls()[name]
                if item["path"] == relative:
                    source = original.decode()
                    if source.count(before) != count:
                        raise ValueError("source-control anchor differs")
                    edited = source.replace(before, after)
                    expected = edited.encode()
                    expected_patch = "".join(difflib.unified_diff(source.splitlines(keepends=True), edited.splitlines(keepends=True),
                        fromfile="original/" + relative, tofile=name + "/" + relative))
            actual = (output / "source-controls" / name / item["path"]).read_bytes()
            if actual != expected or type(item["bytes"]) is not int or len(actual) != item["bytes"] or hashlib.sha256(actual).hexdigest() != item["sha256"]:
                raise ValueError("executed full source/control bytes differ")
            files += 1
        if len(arm["files"]) != len(evidence["files"]) or arm["patch"] != expected_patch:
            raise ValueError("source-control manifest or exact patch differs")
    return files


def module_paths():
    """The retained closure contains 27 runtime and four upstream-test modules."""
    expected = {}
    for row in retained.source_identity()["files"]:
        path = row["path"]
        if path.endswith(".py") and "/tests/" not in path and path != "hc/test.py":
            module = path[:-3].replace("/", ".")
            if module.endswith(".__init__"):
                module = module[:-9]
            expected[module] = path
    if len(expected) != 27:
        raise ValueError("declared native runtime module closure differs")
    return expected


def dependencies(output):
    wanted = dict(line.split("==") for line in (retained.ROOT / "requirements.lock").read_text().splitlines())
    records = spec.read(output / "native-dependencies.json")
    names = [row["name"] for row in records]
    if len(names) != len(set(names)) or set(names) != set(wanted):
        raise ValueError("native dependency-record set differs")
    for row in records:
        if row["version"] != wanted[row["name"]] or not row["verified_files"]:
            raise ValueError("native pinned dependency record differs")
        paths = [item["path"] for item in row["verified_files"]]
        if len(paths) != len(set(paths)) or any(
                set(item) != {"path", "digest", "bytes"} or type(item["bytes"]) is not int or item["bytes"] < 0 or
                not isinstance(item["digest"], str) or "=" not in item["digest"] for item in row["verified_files"]):
            raise ValueError("native dependency integrity rows are incomplete")
    return wanted


def execution_receipt(receipt, arm, *, replay=False, recorded_root=None):
    if set(receipt) != {"command", "elapsed_seconds", "returncode", "stdout", "stderr"}:
        raise ValueError("native execution receipt fields differ")
    if type(receipt["returncode"]) is not int or receipt["returncode"] != 0:
        raise ValueError("native execution receipt is unsuccessful")
    elapsed = receipt["elapsed_seconds"]
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("native execution duration is invalid")
    if receipt["stderr"] != "":
        raise ValueError("native execution receipt contains unexplained stderr")
    command = receipt["command"]
    if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
        raise ValueError("native execution command is invalid")
    expected_tail_length = 10 if replay else 8
    try:
        at = command.index("-m")
    except ValueError as error:
        raise ValueError("native execution module argument missing") from error
    if command[1:at] not in (["-B"], ["-O", "-B"], ["-OO", "-B"]):
        raise ValueError("native execution interpreter options differ")
    tail = command[at:]
    if (len(tail) != expected_tail_length or tail[:2] != ["-m", "source_study.native_healthchecks_tree.native"] or
            tail[2] != "--source" or tail[4] != "--output" or tail[6:] !=
            (["--arm", arm, "--replay-plan", tail[9]] if replay else ["--arm", arm])):
        raise ValueError("native execution command does not invoke the declared collector")
    source, destination = recorded_path(tail[3]).resolve(), recorded_path(tail[5]).resolve()
    root = source.parent.parent
    if not source.is_absolute() or source != root / "source-controls" / arm:
        raise ValueError("native source argument leaves its recorded source arm")
    if recorded_root is not None and root != recorded_root:
        raise ValueError("native executions name different acquisition roots")
    if destination != root / ("native-replay" if replay else "native") / arm:
        raise ValueError("native execution output argument differs")
    if replay and recorded_path(tail[9]).resolve() != root / "replay-plans" / (arm + ".json"):
        raise ValueError("native replay-plan argument differs")
    try:
        report = json.loads(receipt["stdout"])
    except (ValueError, TypeError) as error:
        raise ValueError("native execution stdout is not its count receipt") from error
    return root, source, report


def collection_provenance(collection, arm, source, expected_cases, report, pinned, *, python_record=None):
    fields = {"arm", "cases", "imported_application_modules", "framework", "python",
              "source_imports_replaced", "complete_sqlite_checkpoints", "checkpoint_clock_restored", "cookie_state_preserved"}
    if set(collection) != fields or collection["arm"] != arm:
        raise ValueError("native collection declaration differs")
    for field, value in (("source_imports_replaced", False), ("complete_sqlite_checkpoints", True),
                         ("checkpoint_clock_restored", False), ("cookie_state_preserved", True)):
        if collection[field] is not value:
            raise ValueError("native collection provenance flag differs: " + field)
    if collection["framework"] != pinned["Django"] or not isinstance(collection["python"], str) or not collection["python"].startswith("3."):
        raise ValueError("native framework/runtime record differs")
    if python_record is not None and collection["python"] != python_record:
        raise ValueError("native trees and replays record different Python runtimes")
    expected_modules = {module: str((source / relative).resolve()) for module, relative in module_paths().items()}
    recorded_modules = canonical_recorded_mapping(collection["imported_application_modules"])
    if not spec.typed_equal(recorded_modules, expected_modules):
        raise ValueError("native imported module mapping differs from the full source closure")
    if not spec.typed_equal(collection["cases"], expected_cases):
        raise ValueError("native collection case index/stratum/edge count differs")
    expected_report = dict(arm=arm, cases=len(expected_cases), imported_modules=27,
                           native_http_requests=sum(item["edges"] for item in expected_cases))
    if not spec.typed_equal(report, expected_report):
        raise ValueError("native execution stdout counts differ from collected cases")


def validate_acquisition(output):
    checked = source_check(output)
    pinned = dependencies(output)
    acquisition = spec.read(output / "acquisition.json")
    if (set(acquisition) != {"runs", "source_imports_replaced", "source_observations_acquired_before_diagnosis", "original_37_operation_study_modified"} or
            acquisition["source_imports_replaced"] is not False or acquisition["source_observations_acquired_before_diagnosis"] is not True or
            acquisition["original_37_operation_study_modified"] is not False or len(acquisition["runs"]) != len(spec.ARMS)):
        raise ValueError("native acquisition provenance differs")
    expected_cases = [dict(format=fmt, api_version=api, initial_status=status, word=None, edges=39,
                           directory=fmt + "-api-" + str(api) + "-" + status)
                      for fmt in spec.FORMATS for api in spec.API_VERSIONS for status in spec.INITIAL_STATUSES]
    recorded_root, python_record = None, None
    for arm, receipt in zip(spec.ARMS, acquisition["runs"], strict=True):
        root, source, report = execution_receipt(receipt, arm, recorded_root=recorded_root)
        collection = spec.read(output / "native" / arm / "collection.json")
        collection_provenance(collection, arm, source, expected_cases, report, pinned, python_record=python_record)
        recorded_root, python_record = root, collection["python"]
    return checked, pinned, recorded_root, python_record


def checkpoints(directory, case, *, replay_word=None):
    rows = spec.admit(case, replay_word=replay_word)
    expected = {(): case["initial"], **{word: row["after"] for word, row in rows.items()}}
    if set(case["checkpoints"]) != {spec.name(word) for word in expected}:
        raise ValueError("physical checkpoint set differs from the actual history nodes")
    physical = 0
    for word, snapshot in expected.items():
        item = case["checkpoints"][spec.name(word)]
        path = directory / item["path"]
        if not path.resolve().is_relative_to(directory.resolve()) or path.suffix != ".gz":
            raise ValueError("checkpoint path leaves its native history directory")
        raw = gzip.decompress(path.read_bytes())
        if type(item["sqlite_bytes"]) is not int or len(raw) != item["sqlite_bytes"] or not spec.typed_equal(spec.sqlite_snapshot(raw), snapshot):
            raise ValueError("complete native SQLite checkpoint differs from recorded rows/schema")
        physical += 1
    return physical


def verify(output):
    from .run import cases, stratum
    output = Path(output)
    checked_source_files, pinned, recorded_root, python_record = validate_acquisition(output)
    if not spec.typed_equal(encoding.bound_probe(), spec.read(output / "encoding-bound-check.json")):
        raise ValueError("production bound receipt differs")
    language = spec.read(output / "language.json")
    if not spec.typed_equal(language, spec.language_manifest()):
        raise ValueError("declared bounded language differs")
    index = spec.read(output / "profiles.json")
    wanted_index = []
    counts = Counter()
    by_group = {}
    expected_replays = {arm: {} for arm in spec.ARMS}
    main_uuids = set()
    for directory, case in cases(output):
        counts["native_trees"] += 1
        counts["main_physical_checkpoints"] += checkpoints(directory, case)
        counts["native_http_edges"] += len(case["records"])
        counts["native_sql_statements"] += sum(len(row["sql"]) for row in case["records"])
        main_uuids.update(row["check_uuid"] for row in case["owners"].values())
        profile_path = Path("profiles") / case["arm"] / (stratum(case) + ".json.gz")
        profiles = encoding.diagnose(case)
        if not spec.typed_equal(spec.read(output / profile_path), profiles):
            raise ValueError("retained complete production profiles differ")
        wanted_index.append(dict(arm=case["arm"], format=case["format"], api_version=case["api_version"],
            initial_status=case["initial_status"], profile=str(profile_path),
            source_record=str((directory / "observations.json.gz").relative_to(output))))
        for profile in profiles:
            counts["global_profiles"] += 1
            counts["root_branch_components"] += len(profile["components"])
            counts["production_method_comparisons"] += sum(len(component["methods"]) for component in profile["components"])
            counts["minimal_bad_prefix_results"] += len(profile["first_bad_prefixes"])
            signature = (profile["equivalent"], profile["shortest_length"], tuple(profile["shortest_word"] or []),
                         tuple(tuple(failure["word"]) for failure in profile["first_bad_prefixes"]),
                         profile["differing_edges"])
            group = (case["arm"], case["initial_status"], profile["mode"])
            by_group.setdefault(group, []).append(signature)
            for failure in profile["first_bad_prefixes"]:
                slot = (case["format"], case["api_version"], case["initial_status"], tuple(failure["word"]))
                expected_replays[case["arm"]].setdefault(slot, []).append(profile["mode"])
    if not spec.typed_equal(wanted_index, index):
        raise ValueError("profile index is incomplete or reordered")
    if counts["native_trees"] != 60 or counts["native_http_edges"] != 2340 or counts["main_physical_checkpoints"] != 2400:
        raise ValueError("complete bounded native grid denominator differs")
    strata = []
    for (arm, status, mode), signatures in sorted(by_group.items()):
        if len(signatures) != 6 or len(set(signatures)) != 1:
            raise ValueError("key-format/API strata do not have the same declared summary")
        matched, length, word, failures, differing = signatures[0]
        strata.append(dict(arm=arm, initial_status=status, observation=mode, repeated_strata=6,
            equivalent=matched, shortest_length=length, shortest_word=list(word) if word else None,
            minimal_bad_prefixes=len(failures), differing_edges=differing))
        if arm == "original" and not matched:
            raise ValueError("original source violates the supplied bounded lifecycle contract")
    replay_uuids = set()
    replay_receipts = spec.read(output / "native-replay.json")
    receipt_arms = [item["arm"] for item in replay_receipts]
    required_arms = {arm for arm in spec.ARMS if expected_replays[arm]}
    if len(receipt_arms) != len(set(receipt_arms)) or set(receipt_arms) != required_arms or any(set(item) != {"arm", "receipt"} for item in replay_receipts):
        raise ValueError("native replay execution receipt set differs")
    replay_receipts = {item["arm"]: item["receipt"] for item in replay_receipts}
    for arm in spec.ARMS:
        plan = spec.read(output / "replay-plans" / (arm + ".json"))
        obtained = set()
        collection = spec.read(output / "native-replay" / arm / "collection.json") if plan else None
        if collection is not None:
            _, source, report = execution_receipt(replay_receipts[arm], arm, replay=True, recorded_root=recorded_root)
            expected_cases = [dict(directory=item["directory"], format=item["format"], api_version=item["api_version"],
                initial_status=item["initial_status"], word=item["word"], edges=len(item["word"])) for item in plan]
            collection_provenance(collection, arm, source, expected_cases, report, pinned, python_record=python_record)
        elif (output / "native-replay" / arm).exists():
            raise ValueError("unexpected native replay collection for an empty plan")
        for ordinal, item in enumerate(plan):
            expected_fields = {"format", "api_version", "initial_status", "word", "modes", "directory", "main_profile", "main_record"}
            expected_stratum = item["format"] + "-api-" + str(item["api_version"]) + "-" + item["initial_status"]
            if (set(item) != expected_fields or item["directory"] != "word-" + str(ordinal).zfill(4) or
                    item["main_profile"] != str(Path("profiles") / arm / (expected_stratum + ".json.gz")) or
                    item["main_record"] != str(Path("native") / arm / expected_stratum / "observations.json.gz")):
                raise ValueError("native replay plan/index/source record differs")
            slot = (item["format"], item["api_version"], item["initial_status"], tuple(item["word"]))
            if slot in obtained or slot not in expected_replays[arm] or not spec.typed_equal(item["modes"], sorted(expected_replays[arm][slot])):
                raise ValueError("fresh negative-prefix replay plan differs")
            obtained.add(slot)
            directory = output / "native-replay" / arm / item["directory"]
            case = spec.read(directory / "observations.json.gz")
            if not spec.typed_equal((case["arm"], case["format"], case["api_version"], case["initial_status"], case["replay_word"]),
                                   (arm, item["format"], item["api_version"], item["initial_status"], item["word"])):
                raise ValueError("fresh native replay stratum differs")
            counts["replay_physical_checkpoints"] += checkpoints(directory, case, replay_word=item["word"])
            current_uuids = {row["check_uuid"] for row in case["owners"].values()}
            if current_uuids & (main_uuids | replay_uuids):
                raise ValueError("replay did not construct independent fresh native rows")
            replay_uuids |= current_uuids
            for mode in item["modes"]:
                result = spec.independent_profile(case, mode, replay_word=item["word"])
                if result["equivalent"] is not False or not spec.typed_equal(result["shortest_word"], item["word"]):
                    raise ValueError("fresh native prefix did not reproduce its exact first failure")
                counts["native_replayed_negative_results"] += 1
            counts["native_replay_words"] += 1
            counts["native_replay_http_requests"] += len(case["records"])
        if obtained != set(expected_replays[arm]):
            raise ValueError("not every minimal negative prefix was actually replayed")
    if counts["native_replayed_negative_results"] != counts["minimal_bad_prefix_results"]:
        raise ValueError("fresh replay did not cover every negative prefix outcome")
    return dict(status="PASS", applications=1, source_arms=5, key_formats=2, api_versions=3,
        initial_statuses=list(spec.INITIAL_STATUSES), native_operations=list(spec.SYMBOLS), maximum_request_length=3,
        nodes_per_tree=40, edges_per_tree=39, complete_bounded_word_language=True,
        complete_unbounded_physical_state_graph=False, physical_histories_merged=False,
        shared_correspondence_family=False, checked_source_files=checked_source_files, **dict(counts),
        observation_clock_projection="Flip created/processed literals remain in exact checkpoints; rich comparison retains presence and processed-at-creation relation.",
        strata=strata)
