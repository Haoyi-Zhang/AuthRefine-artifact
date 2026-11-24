"""Third-reader audit of retained native histories; no application execution.

Uses only the standard library. It reconstructs language/operation counts and
lifecycle effects directly, reads every complete SQLite image, and decodes
the retained production policies, tables and individual replay rows.
"""
import argparse
from collections import Counter
import difflib
import re
from copy import deepcopy
import base64
import gzip
import hashlib
import itertools
import json
from pathlib import Path, PurePosixPath
import sqlite3

ART = Path(__file__).resolve().parents[1]
DATA = ART / 'results/native-healthchecks-tree'
ARMS = ('original', 'omit_readonly_context', 'wrong_project_context',
        'omit_pause_persistence', 'reject_readonly_get')
OPS = ('get', 'pause', 'resume')
ALL = [()] + [w for n in range(1, 4) for w in itertools.product(OPS, repeat=n)]
ORDER = lambda w: (len(w), w)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def equal(a, b, message):
    require(canon(a) == canon(b), message)


def fingerprint():
    return {str(p.relative_to(DATA)): (p.stat().st_size, p.stat().st_mtime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest())
            for p in DATA.rglob('*') if p.is_file()}


def snapshot(raw):
    db = sqlite3.connect(':memory:')
    try:
        db.deserialize(raw)
        db.execute('PRAGMA query_only=ON')
        require(db.execute('PRAGMA integrity_check').fetchone() == ('ok',), 'SQLite integrity')
        schema = [dict(zip(('type', 'name', 'tbl_name', 'sql'), row))
                  for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        tables = {}
        for entry in schema:
            if entry['type'] != 'table':
                continue
            name = entry['name']
            query = db.execute('SELECT rowid AS __rowid__, * FROM "' + name.replace('"', '""') + '" ORDER BY rowid')
            columns = [col[0] for col in query.description]
            tables[name] = [dict(zip(columns, [({'sqlite_blob': base64.b64encode(x).decode()} if isinstance(x, bytes) else x) for x in row])) for row in query]
        return {'schema': schema, 'tables': tables}
    finally:
        db.close()


def reduced_store(value):
    result = deepcopy(value)
    for row in result['tables']['api_flip']:
        created = row.pop('created')
        processed = row.pop('processed')
        row['created_present'] = created is not None
        row['processed_present'] = processed is not None
        row['processed_at_creation'] = created == processed
    return result


def actual_value(row, mode):
    if mode == 'http_status':
        return {'http_status': row['http_status']}
    headers = {k.lower(): v for k, v in row['response_headers'].items()}
    if 'access-control-allow-methods' in headers:
        headers['access-control-allow-methods'] = sorted(x.strip() for x in headers['access-control-allow-methods'].split(','))
    return dict(store=reduced_store(row['after']), http_status=row['http_status'],
        project_id=row['request_project_id'], project_class=row['request_project_class'],
        readonly=row['request_readonly'], api_version=row['request_api_version'],
        manager_returns=row['source_manager_returns'],
        manager_result_is_request_project=row['manager_result_is_request_project'],
        response=dict(json=row['response'], text=None if headers['content-type'].startswith('application/json') else row['response_text'],
                      headers=headers, cookies=row['response_cookies']),
        client_cookies_before=row['client_cookies_before'], client_cookies_after=row['client_cookies_after'])


def life(initial, word, omit_save=False):
    status, flips, code = initial, [], 200
    for op in word:
        code = 200
        if op == 'pause' and status != 'paused':
            flips.append((status, 'paused'))
            if not omit_save:
                status = 'paused'
        elif op == 'resume':
            if status == 'paused':
                flips.append(('paused', 'new'))
                status = 'new'
            else:
                code = 409
    return status, flips, code


def different(case, word, mode):
    arm = case['arm']
    ref = life(case['initial_status'], word)
    measured = life(case['initial_status'], word, arm == 'omit_pause_persistence')
    if arm == 'reject_readonly_get' and word[-1] == 'get':
        return True
    if mode == 'http_status':
        return ref[2] != measured[2]
    return (ref != measured or arm == 'wrong_project_context' or
            (arm == 'omit_readonly_context' and word[-1] == 'get'))


def prefixes(case, words, mode):
    bad = {w for w in words if different(case, w, mode)}
    return sorted([w for w in bad if not any(w[:i] in bad for i in range(1, len(w)))], key=ORDER), bad


def physical(case, directory, expected_words, counts):
    rows = {tuple(row['word']): row for row in case['records']}
    require(len(rows) == len(case['records']) and set(rows) == set(expected_words), 'Unique complete word set')
    nodes = {(): case['initial'], **{w: row['after'] for w, row in rows.items()}}
    names = {'root' if not w else '-'.join(w) for w in nodes}
    require(set(case['checkpoints']) == names, 'Complete checkpoint name set')
    for w, state in nodes.items():
        name = 'root' if not w else '-'.join(w)
        entry = case['checkpoints'][name]
        path = directory / entry['path']
        require(path.resolve().is_relative_to(directory.resolve()), 'Local checkpoint path')
        raw = gzip.decompress(path.read_bytes())
        equal(len(raw), entry['sqlite_bytes'], 'Physical SQLite byte count')
        equal(snapshot(raw), state, 'Every complete table, schema and sequence matches physical image')
        counts['sqlite_images'] += 1
        counts['sqlite_uncompressed_bytes'] += len(raw)
    check_id = case['owners']['alice']['check_id']
    for w, row in rows.items():
        parent = nodes[w[:-1]]
        equal(row['before'], parent, 'Physical parent continuity')
        equal(row['client_cookies_before'], {} if len(w) == 1 else rows[w[:-1]]['client_cookies_after'], 'Client cookie parent continuity')
        require(row['checkpoint_exact_copy'] is True, 'Exact-copy runtime receipt')
        expected = life(case['initial_status'], w, case['arm'] == 'omit_pause_persistence')
        actual_check = next(x for x in row['after']['tables']['api_check'] if x['id'] == check_id)
        equal(actual_check['status'], expected[0], 'Independent actual lifecycle status')
        equal([(x['old_status'], x['new_status']) for x in row['after']['tables']['api_flip']], expected[1], 'Independent Flip transition sequence')
        expected_http = 401 if case['arm'] == 'reject_readonly_get' and w[-1] == 'get' else expected[2]
        equal(row['http_status'], expected_http, 'Independent HTTP lifecycle status')
        require(row['response_headers']['Content-Length'] == str(len(row['response_text'].encode())), 'Wire body byte count')
        if row['response_headers']['Content-Type'].startswith('application/json'):
            equal(json.loads(row['response_text']), row['response'], 'Complete JSON body equality')
        counts['native_record_edges'] += 1
        counts['sql_statements'] += len(row['sql'])
    return rows


def production(case, rows, profile, counts):
    mode = profile['mode']
    minimal, bad = prefixes(case, rows, mode)
    equal([x['word'] for x in profile['first_bad_prefixes']], [list(x) for x in minimal], 'Independent first-bad-prefix set')
    equal(profile['differing_edges'], len(bad), 'Independent differing-edge count')
    equal(profile['shortest_word'], list(minimal[0]) if minimal else None, 'Independent global shortest word')
    equal(profile['equivalent'], not bad, 'Independent complete language verdict')
    counts['global_profiles'] += 1
    counts['minimal_bad_prefix_results'] += len(minimal)
    union = set()
    for component in profile['components']:
        value = component['inputs']
        machine, caller, policy, codebook = (value[x] for x in ('machine', 'caller', 'policy', 'codebook'))
        require(len({canon(x) for x in codebook}) == len(codebook), 'Injective rich/status codebook')
        require(len(machine['observations']) == 14 and len(caller['transitions']) == 6, 'Existing state limits')
        require(len(policy['state']) <= 5 and len(policy['principals']) == 5, 'Existing bit/principal limits')
        require(sum(1 + len(x['guard']) + len(x['updates']) for x in policy['rules']) <= 104, 'Existing AST limit')
        queue = [(0, 0, ())]
        positions, found = {}, set()
        reference_codes = {}
        while queue:
            q, t, w = queue.pop()
            require(w not in found, 'No merged or duplicated native history')
            found.add(w);positions[w] = (q, t)
            equal(value['target_histories'][q], list(w), 'History erasure is exact')
            for index, next_t in enumerate(caller['transitions'][t]):
                if next_t is None:
                    continue
                decision, next_q = machine['transitions'][q][index]
                principal, symbol, action = machine['alphabet'][index]
                require(action == 'capture' and decision == 'allow', 'Capture semantics')
                require(principal == value['history_principals']['root' if not w else '-'.join(w)], 'Caller history label')
                next_w = (*w, symbol)
                matches = [rule for rule in policy['rules'] if all(not atom['negated'] and atom['name'] == {'principal':principal, 'resource':symbol}[atom['field']] for atom in rule['guard'])]
                require(len(matches) == 1, 'Exactly one reference transition rule')
                updates = {u['name']: u['value'] for u in matches[0]['updates']}
                require(set(updates) == {x[0] for x in policy['state']}, 'Full constant code assignment')
                ref_code = sum(1 << i for i, (name, _) in enumerate(policy['state']) if updates[name])
                actual_code = machine['observations'][next_q]
                equal(codebook[actual_code], actual_value(rows[next_w], mode), 'Complete raw observation retained by target code')
                equal(ref_code != actual_code, different(case, next_w, mode), 'Source control mismatch predicted independently')
                reference_codes[next_w] = ref_code
                queue.append((next_q, next_t, next_w))
        expected = {()} | {w for w in ALL[1:] if w[0] == value['first_operation']}
        require(found == expected and len(found) == 14, 'Full root-branch language bijection')
        union |= found
        branch_bad = sorted(bad & found, key=ORDER)
        counts['root_branch_components'] += 1
        require(set(component['methods']) == {'protocol-scan', 'protocol-grouped'}, 'Both production algorithms')
        for method in component['methods'].values():
            equal(method['matching_family'], [] if branch_bad else [{}], 'Singleton family output')
            result = method['profiles'][0]
            equal(result['equivalent'], not branch_bad, 'Branch profile classification')
            if branch_bad:
                w, q, t, source = (), 0, 0, 0
                equal(len(result['trace']), len(result['indices']), 'Complete individual replay rows')
                for number, (index, trace) in enumerate(zip(result['indices'], result['trace'])):
                    request = machine['alphabet'][index]
                    next_w = (*w, request[1])
                    edge = machine['transitions'][q][index]
                    equal(trace['binding'], {}, 'Replay fixed binding')
                    equal(trace['request'], request, 'Replay request')
                    equal(trace['source'], ['allow', reference_codes[next_w]], 'Replay reference code')
                    equal(trace['target'], ['allow', machine['observations'][edge[1]]], 'Replay actual code')
                    equal((trace['source_state'], trace['target_state'], trace['protocol_state']), (source,q,t), 'Replay state continuity')
                    equal(trace['compared_equal'], number < len(result['trace'])-1, 'Agreeing proper replay prefixes')
                    source=reference_codes[next_w];q=edge[1];t=caller['transitions'][t][index];w=next_w
                    counts['decoded_replay_rows'] += 1
                equal(list(w), list(branch_bad[0]), 'Canonical shortest decoded native branch word')
            counts['production_method_comparisons'] += 1
    require(union == set(ALL), 'Exact union of three branch languages')
    return minimal


def provenance():
    source_root = ART / 'source_study/native_healthchecks'
    source_evidence = read(source_root / 'source-evidence.json')['files']
    paths = [row['path'] for row in source_evidence]
    require(len(paths) == 34 and len(set(paths)) == 34, 'Original source closure has 34 unique paths')
    originals = {}
    for item in source_evidence:
        relative = item['path']
        path = source_root/'source'/relative
        require(path.resolve().is_relative_to((source_root/'source').resolve()), 'Original source path is local')
        raw = path.read_bytes()
        equal(len(raw), item['upstream_bytes'], 'Original source byte count')
        equal(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(), item['upstream_git_blob'], 'Original source identity')
        originals[relative] = raw
    manifest = read(DATA/'source-controls.json')
    equal([x['arm'] for x in manifest], list(ARMS), 'Source arms in exact order')
    for entry in manifest:
        arm = entry['arm']
        observed = [x['path'] for x in entry['files']]
        require(len(observed) == len(set(observed)) and set(observed) == set(paths), 'Unique complete executed source path set')
        require(entry['current_complete_source_modules'] is True and entry['historical_deployment_executed'] is False, 'Source provenance declaration')
        patches = []
        for item in entry['files']:
            relative = item['path']
            current = (DATA/'source-controls'/arm/relative).read_bytes()
            equal(len(current), item['bytes'], 'Executed source byte count')
            equal(hashlib.sha256(current).hexdigest(), item['sha256'], 'Executed source digest')
            if current != originals[relative]:
                patches.append(''.join(difflib.unified_diff(originals[relative].decode().splitlines(keepends=True), current.decode().splitlines(keepends=True), fromfile='original/'+relative, tofile=arm+'/'+relative)))
        equal(''.join(patches), entry['patch'], 'Every actual source change appears in retained patch')
        equal(len(patches), 0 if arm == 'original' else 1, 'Declared source-control file count')
    imported = {}
    for path in paths:
        if not path.endswith('.py') or path == 'hc/test.py' or path.startswith('hc/api/tests/'):
            continue
        name = path[:-3].replace('/', '.')
        if name.endswith('.__init__'):
            name = name[:-9]
        imported[name] = path
    require(len(imported) == 27, 'Declared native module closure')
    normalize_name = lambda value: re.sub(r'[-_.]+','-',value).lower()
    locks = dict(line.split('==') for line in (source_root/'requirements.lock').read_text().splitlines() if line.strip())
    locks = {normalize_name(k):v for k,v in locks.items()}
    dependencies = read(DATA/'native-dependencies.json')
    require(len({normalize_name(x['name']) for x in dependencies}) == len(dependencies), 'Unique dependency receipt identities')
    equal({normalize_name(x['name']): x['version'] for x in dependencies}, locks, 'Dependency receipt agrees with explicit lock')
    for dependency in dependencies:
        files = dependency['verified_files']
        require(files and len({x['path'] for x in files}) == len(files), 'Unique recorded dependency files')
        require(all(type(x['bytes']) is int and x['bytes'] >= 0 and x['digest'].startswith('sha256=') for x in files), 'Recorded dependency file identities')
    acquisition = read(DATA/'acquisition.json')
    require(acquisition['source_imports_replaced'] is False and acquisition['source_observations_acquired_before_diagnosis'] is True and acquisition['original_37_operation_study_modified'] is False, 'Main acquisition declarations')
    require(len(acquisition['runs']) == len(ARMS), 'Every source arm has a process receipt')
    process_rows = [(arm, 'native', receipt) for arm, receipt in zip(ARMS, acquisition['runs'])]
    replay_receipts = read(DATA/'native-replay.json')
    require([r['arm'] for r in replay_receipts] == list(ARMS[1:]), 'Replay process arm coverage')
    process_rows += [(item['arm'], 'native-replay', item['receipt']) for item in replay_receipts]
    collection_cases = 0
    for arm, stage, receipt in process_rows:
        require(type(receipt['returncode']) is int and receipt['returncode'] == 0, 'Native process actually succeeded')
        command = receipt['command']
        for flag in ('-m','--source','--output','--arm'):
            require(command.count(flag) == 1, 'Unique native command arguments')
        argument = lambda flag: command[command.index(flag)+1]
        equal(argument('-m'), 'source_study.native_healthchecks_tree.native', 'Native module entry point')
        equal(argument('--arm'), arm, 'Process source arm')
        recorded_source = PurePosixPath(argument('--source'))
        require(recorded_source.parts[-2:] == ('source-controls', arm), 'Recorded source closure path')
        recorded_root = recorded_source.parent.parent
        equal(argument('--output'), str(recorded_root/stage/arm), 'Recorded process output path')
        collection = read(DATA/stage/arm/'collection.json')
        equal(collection['arm'], arm, 'Collection source arm')
        for field, value in [('source_imports_replaced',False),('complete_sqlite_checkpoints',True),('checkpoint_clock_restored',False),('cookie_state_preserved',True)]:
            equal(collection[field], value, 'Collection declaration '+field)
        equal(collection['framework'], locks['django'], 'Actual framework receipt')
        equal(collection['imported_application_modules'], {name:str(recorded_source/relative) for name,relative in imported.items()}, 'Exact native module identities inside selected closure')
        if stage == 'native':
            wanted = [dict(format=fmt, api_version=api, initial_status=status, word=None,
                directory=fmt+'-api-'+str(api)+'-'+status, edges=39)
                for fmt in ('legacy','hashed') for api in (1,2,3) for status in ('new','paused')]
        else:
            require(command.count('--replay-plan') == 1, 'One fresh native replay plan')
            equal(argument('--replay-plan'), str(recorded_root/'replay-plans'/(arm+'.json')), 'Recorded replay plan path')
            wanted = [dict(format=x['format'], api_version=x['api_version'], initial_status=x['initial_status'], word=x['word'], directory=x['directory'], edges=len(x['word'])) for x in read(DATA/'replay-plans'/(arm+'.json'))]
        equal(collection['cases'], wanted, 'Complete case-to-directory collection index')
        equal(json.loads(receipt['stdout']), dict(arm=arm, cases=len(wanted), imported_modules=27, native_http_requests=sum(x['edges'] for x in wanted)), 'Process stdout agrees with actual indexed counts')
        collection_cases += len(wanted)
    return dict(original_source_files=34, executed_source_files=170, exact_control_patches=4,
        successful_native_process_receipts=len(process_rows), checked_collection_cases=collection_cases,
        native_modules_per_process=27, dependency_lock_entries=len(dependencies),
        dependency_receipt_scope='Retained package/file identity records and lock agreement; no current environment import or dependency reacquisition.')


def derive(data):
    global DATA
    DATA = data.resolve()
    before = fingerprint()
    source_receipts = provenance()
    index = read(DATA / 'profiles.json')
    expected_grid = set(itertools.product(ARMS, ('legacy','hashed'), (1,2,3), ('new','paused')))
    grid, counts, replays = set(), Counter(), {}
    uuids = set()
    for item in index:
        case = read(DATA / item['source_record'])
        key = tuple(case[k] for k in ('arm','format','api_version','initial_status'))
        require(key not in grid, 'Unique primary stratum');grid.add(key)
        rows = physical(case, (DATA/item['source_record']).parent, ALL[1:], counts)
        current = {x['check_uuid'] for x in case['owners'].values()}
        require(len(current) == 2 and not uuids & current, 'Fresh distinct primary UUID fixtures');uuids |= current
        counts['native_trees'] += 1
        for profile in read(DATA/item['profile']):
            for word in production(case, rows, profile, counts):
                replays.setdefault((*key, word), []).append(profile['mode'])
    require(grid == expected_grid, 'All 60 distinct native strata')
    main_counts = dict(counts)
    require((counts['native_record_edges'],counts['sqlite_images']) == (2340,2400), 'Primary physical denominators')
    actual_replays = set()
    for arm in ARMS:
        for item in read(DATA/'replay-plans'/(arm+'.json')):
            key=(arm,item['format'],item['api_version'],item['initial_status'],tuple(item['word']))
            require(key in replays and key not in actual_replays, 'Exact unique replay plan');actual_replays.add(key)
            equal(sorted(replays[key]),item['modes'],'Observation deduplication')
            directory=DATA/'native-replay'/arm/item['directory'];case=read(directory/'observations.json.gz')
            equal(tuple(case[k] for k in ('arm','format','api_version','initial_status')), key[:-1], 'Replay record stratum')
            equal(case['replay_word'], list(key[-1]), 'Replay record word')
            words=[key[-1][:i] for i in range(1,len(key[-1])+1)]
            physical(case,directory,words,counts)
            current={x['check_uuid'] for x in case['owners'].values()}
            require(len(current)==2 and not uuids & current, 'Every replay constructs fresh distinct UUIDs');uuids|=current
            for mode in item['modes']:
                minimal,_=prefixes(case,words,mode)
                equal(minimal,[key[-1]],'Replayed first conflicting prefix')
            counts['native_replay_words']+=1
            counts['native_replayed_negative_results']+=len(item['modes'])
    require(actual_replays==set(replays),'Every minimal negative prefix is physically replayed')
    counts['native_replay_http_requests']=counts['native_record_edges']-main_counts['native_record_edges']
    counts['replay_physical_checkpoints']=counts['sqlite_images']-main_counts['sqlite_images']
    counts['replay_sql_statements']=counts['sql_statements']-main_counts['sql_statements']
    equal(fingerprint(),before,'Scientific files and modification times unchanged')
    report=dict(status='PASS',independent_native_executions=0,production_checker_executions=0,
        evidence_files_unchanged=len(before),main=main_counts,combined=dict(counts),
        unique_fixture_check_uuids=len(uuids), provenance=source_receipts,
        scope='Independent standard-library lifecycle equations, complete physical SQLite readback and retained production replay decoding; no application or builder/auditor modules imported.')
    return report


README = """# Independent native-history audit

The standard-library command in proofs/audit_native_healthchecks_tree.py checks
all complete physical SQLite images, admitted histories, raw response values,
independent lifecycle equations, complete branch encodings and individual
production replay rows. It separately verifies executed source-file sets,
exact control patches, module identities and process/collection receipts.

No native application or production checker is imported or executed by this
audit. Native acquisition and fresh replay counts belong to the input study;
this audit adds zero native executions. SQLite images are decompressed into
memory and checked with query_only plus integrity_check. Comparison is JSON
type-sensitive: false, 0 and 0.0 are distinct values.

From artifact/, run:

    python -B proofs/audit_native_healthchecks_tree.py --verify-retained results/native-healthchecks-tree-review
    python -B -OO -W error proofs/audit_native_healthchecks_tree.py --verify-retained results/native-healthchecks-tree-review

The default input is results/native-healthchecks-tree; --results selects a
relocated copy. Default mode is read-only and prints the recomputed summary.
--output writes a new audit directory and rejects existing destinations, input
ancestors, and locations inside protected source/evidence directories.
The input byte contents and modification times must be unchanged after a run.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ART/'results/native-healthchecks-tree')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--output', type=Path)
    group.add_argument('--verify-retained', type=Path)
    args = parser.parse_args()
    data = args.results.resolve(strict=True)
    if args.output is not None:
        destination = args.output.resolve()
        protected = [data, ART/'results/native-healthchecks-tree', *[ART/name for name in ('proofs','source_study','src','tests','references','figures')]]
        if destination.exists() or any(destination.is_relative_to(path.resolve()) or path.resolve().is_relative_to(destination) for path in protected):
            parser.error('choose a fresh output outside the scientific inputs and protected source directories')
    report = derive(data)
    if args.verify_retained is not None:
        retained = args.verify_retained.resolve(strict=True)
        equal(read(retained/'summary.json'), report, 'Retained independent scientific audit summary')
        equal((retained/'README.md').read_text(), README, 'Retained independent audit instructions')
    if args.output is not None:
        destination.mkdir(parents=True, exist_ok=False)
        (destination/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        (destination/'README.md').write_text(README)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
