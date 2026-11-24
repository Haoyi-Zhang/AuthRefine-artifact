#!/usr/bin/env python3
"""Check or refresh citations and claim locations in the included manuscripts.

The three CSV files in artifact/ are canonical. Reading scopes, supported
claims, access limits and access dates are preserved from reading-records.json.
Only an explicit --write updates derived locations and metadata. No network
request or historical-process receipt is needed by this command.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ARTIFACT = HERE.parent
PROJECT = ARTIFACT.parent
PAPER = PROJECT / 'paper'
sys.path.insert(0, str(ARTIFACT / 'src'))
from reference_check import CITE_RE, entry_identifier, parse_bibtex

CSV_NAMES = ('reference_inventory.csv', 'reference_audit.csv', 'claim_evidence_ledger.csv')
INCLUDE_RE = re.compile(r'\\(?:input|include)\s*\{([^{}]+)\}')
LABEL_RE = re.compile(r'\\label\{([^{}]+)\}|\blabel\s*=\s*\{([^{}]+)\}')
PATH_RE = re.compile(r'(?<![\w./-])(?:source_study|results|src|tests|proofs|figures|benchmarks|empirical_study|adaptation_study|prospective_study|reference_completion|external_inputs|references|paper|\.github)/[^\s;]+')
BARE_FILE_RE = re.compile(r'(?<![\w./-])[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:py|csv|md|json|tex|lean|gz)(?![\w./-])')
EXCLUDED_HISTORY_RE = re.compile(r'results/(?:revision|completion|research-depth|journal-audit)-\d{8}(?:/|\b)')
DERIVED_OUTPUTS = {'references/reference-integrity.json', 'references/citation-locations.json'}


def uncomment(text):
    """Mask TeX comments while retaining positions and line numbers."""
    output = list(text)
    for line in re.finditer(r'[^\n]*(?:\n|$)', text):
        segment = line.group()
        for index, char in enumerate(segment):
            if char != '%':
                continue
            backslashes = 0
            prior = index - 1
            while prior >= 0 and segment[prior] == '\\':
                backslashes += 1
                prior -= 1
            if backslashes % 2 == 0:
                for pos in range(line.start() + index, line.end()):
                    if output[pos] != '\n':
                        output[pos] = ' '
                break
    return ''.join(output)


def included_sources(with_trees=False):
    """Follow actual local input trees; count a shared source file only once."""
    sources, external, trees = set(), set(), {}
    def visit(path, visited):
        path = path.resolve()
        if not path.is_relative_to(PAPER.resolve()):
            raise ValueError('Manuscript include escapes paper/: ' + str(path))
        if path in visited:
            return
        if not path.is_file():
            raise ValueError('Missing manuscript entry: ' + str(path))
        visited.add(path)
        sources.add(path)
        text = uncomment(path.read_text())
        for include in INCLUDE_RE.findall(text):
            target = PAPER / include
            if not target.suffix:
                target = target.with_suffix('.tex')
            if target.is_file():
                visit(target, visited)
            elif target.suffix in {'.fd', '.sty', '.cls'}:
                external.add(include)
            else:
                raise ValueError('Missing local manuscript include: ' + include)
    for name in ('main.tex', 'supplement.tex'):
        trees[name] = set()
        visit(PAPER / name, trees[name])
    result = (sorted(sources), sorted(external))
    return result + (trees,) if with_trees else result


def read_csv(name):
    with (ARTIFACT / name).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def write_csv(name, fields, rows):
    target = ARTIFACT / name
    temporary = target.with_suffix('.csv.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(target)


def check_readings(audits):
    retained = json.loads((HERE / 'reading-records.json').read_text())
    records = {row['citation_key']: row for row in retained['records']}
    if len(records) != len(retained['records']) or set(records) != set(audits):
        raise ValueError('Reading records and current bibliography differ')
    for key, previous in records.items():
        for field in retained['fields']:
            if audits[key][field] != previous[field]:
                raise ValueError(f'Recorded reading changed without a separate source event: {key}/{field}')
        date.fromisoformat(audits[key]['access_date'])
    passages = json.loads((HERE / 'source-passage-checks.json').read_text())
    if {row['key'] for row in passages['reviews']} != set(audits):
        raise ValueError('Claim-specific source passages do not cover the bibliography')
    return len(records)


def expand_braces(value):
    match = re.search(r'\{([^{}]*)\}', value)
    if match is None:
        yield value
        return
    for alternative in match.group(1).split(','):
        yield from expand_braces(value[:match.start()] + alternative + value[match.end():])


def evidence_paths(ledger):
    """Resolve literal scientific/source paths, including braces and globs.

    A suffix after ':' can name a JSON field, theorem or explanation. URLs
    and prose are not interpreted as local paths. Commands remain instructions,
    rather than being executed by a reference check.
    """
    checked = set()
    missing = []
    for row in ledger:
        if any(EXCLUDED_HISTORY_RE.search(value) for value in row.values()):
            raise ValueError('Claim depends on an excluded historical work directory: ' + row['claim'])
        for field in ('proof', 'source_or_test', 'raw_evidence'):
            text = re.sub(r'https?://\S+', '', row[field])
            for match in list(PATH_RE.finditer(text)) + list(BARE_FILE_RE.finditer(text)):
                value = match.group().split(':', 1)[0].rstrip('.,)')
                for expanded in expand_braces(value):
                    # Evidence entries are relative to artifact/ unless they
                    # explicitly name paper/. A CI configuration may live in
                    # artifact/.github without proving it has run remotely.
                    base = PROJECT if expanded.startswith('paper/') else ARTIFACT
                    candidate = base / expanded
                    if not candidate.resolve().is_relative_to(PROJECT.resolve()):
                        missing.append((row['claim'], field, expanded))
                        continue
                    # These outputs are constructed by this same refresh and
                    # checked for exact content by read-only verification.
                    found = (list(base.glob(expanded)) if any(c in expanded for c in '*?[')
                             else [candidate] if candidate.exists() or expanded in DERIVED_OUTPUTS else [])
                    if not found:
                        missing.append((row['claim'], field, expanded))
                    else:
                        checked.update(str(path.relative_to(PROJECT)) for path in found)
    if missing:
        raise ValueError('Missing declared evidence paths: ' + repr(missing))
    return sorted(checked)


def derive():
    entries = parse_bibtex((PAPER / 'references.bib').read_text())
    tables = {name: read_csv(name) for name in CSV_NAMES}
    rows = tables['reference_audit.csv'][1]
    audits = {row['citation_key']: dict(row) for row in rows}
    if len(audits) != len(rows) or set(audits) != set(entries):
        raise ValueError('Every bibliography entry needs a unique claim-specific reading record')
    reading_rows = check_readings(audits)
    sources, external, trees = included_sources(with_trees=True)
    counts = dict.fromkeys(entries, 0)
    locations = {key: [] for key in entries}
    contexts = {key: [] for key in entries}
    labels = {}
    for path in sources:
        source = uncomment(path.read_text())
        relative = path.relative_to(PAPER).as_posix()
        for match in LABEL_RE.finditer(source):
            key = match.group(1) or match.group(2)
            location = f'{relative}:{source.count(chr(10), 0, match.start()) + 1}'
            prior = labels.setdefault(key, [])
            if any(path in tree and old_path in tree
                   for old_path, _ in prior for tree in trees.values()):
                raise ValueError(f'Duplicate label in one manuscript: {key}')
            # Main and supplement are independent TeX documents. Their local
            # labels may coincide; xr prefixes distinguish external links.
            prior.append((path, location))
        for match in CITE_RE.finditer(source):
            location = f'{relative}:{source.count(chr(10), 0, match.start()) + 1}'
            start = source.rfind('\n\n', 0, match.start())
            start = start + 2 if start >= 0 else 0
            end = source.find('\n\n', match.end())
            context = ' '.join(source[start:end if end >= 0 else len(source)].split())
            for key in (part.strip() for part in match.group(1).split(',')):
                if key not in entries:
                    raise ValueError(f'Citation missing from bibliography: {key} at {location}')
                counts[key] += 1
                if location not in locations[key]:
                    locations[key].append(location)
                if context not in contexts[key]:
                    contexts[key].append(context)
    inventory, identifiers = [], set()
    for key, entry in entries.items():
        if counts[key] == 0:
            raise ValueError('Uncited bibliography entry in actual input trees: ' + key)
        fields = entry['fields']
        kind, identifier = entry_identifier(entry)
        identity = identifier.lower() if kind == 'doi' else identifier
        if identity in identifiers:
            raise ValueError('Duplicate publication identifier: ' + identifier)
        identifiers.add(identity)
        row = dict(citation_key=key, title=fields['title'], authors=fields['author'],
                   year=fields['year'], publication_identifier=identifier,
                   identifier_type=kind, citation_occurrences=str(counts[key]))
        inventory.append(row)
        for field in ('title', 'authors', 'year', 'publication_identifier'):
            audits[key][field] = row[field]
        audits[key]['manuscript_locations'] = '; '.join(locations[key])
        audits[key]['citation_context'] = ' || '.join(contexts[key])
    anchors = json.loads((HERE / 'claim-anchors.json').read_text())
    ledger = [dict(row) for row in tables['claim_evidence_ledger.csv'][1]]
    if len({row['claim'] for row in ledger}) != len(ledger):
        raise ValueError('Duplicate scientific claim')
    for row in ledger:
        claim = row['claim']
        if claim.startswith('literature-'):
            key = claim[len('literature-'):]
            if key not in audits:
                raise ValueError('Literature claim has no bibliography key: ' + key)
            row['manuscript_location'] = audits[key]['manuscript_locations']
        else:
            wanted = anchors.get(claim, [claim] if claim in labels else [])
            if wanted:
                missing = [key for key in wanted if key not in labels]
                if missing:
                    raise ValueError(f'Missing reachable manuscript anchors for {claim}: {missing}')
                row['manuscript_location'] = '; '.join(location for key in wanted
                                                       for _, location in labels[key])
            elif '.tex:' in row['manuscript_location'] or row['manuscript_location'].startswith('Pending'):
                raise ValueError('Claim needs a current semantic anchor: ' + claim)
    checked_paths = evidence_paths(ledger)
    expected = {'reference_inventory.csv': inventory,
                'reference_audit.csv': [audits[key] for key in entries],
                'claim_evidence_ledger.csv': ledger}
    report = {'status': 'PASS', 'references': len(entries),
              'identifier_distribution': dict(Counter(row['identifier_type'] for row in inventory)),
              'citation_occurrences': sum(counts.values()), 'claim_rows': len(ledger),
              'preserved_reading_records': reading_rows,
              'included_manuscript_sources': [path.relative_to(PAPER).as_posix() for path in sources],
              'template_inputs': external, 'verified_evidence_paths': checked_paths,
              'scope': 'Current included manuscript citations, retained reading scopes and declared local evidence paths; no new external retrieval is implied.'}
    location_report = {'references': {key: {'occurrences': counts[key], 'locations': locations[key]} for key in entries},
                       'claim_locations': {row['claim']: row['manuscript_location'] for row in ledger}}
    return tables, expected, report, location_report


def verify(write=False):
    tables, expected, report, locations = derive()
    changed = [name for name in CSV_NAMES if tables[name][1] != expected[name]]
    if changed and not write:
        raise ValueError('Stale citation or claim locations: ' + ', '.join(changed))
    outputs = {'reference-integrity.json': report, 'citation-locations.json': locations}
    if write:
        for name in CSV_NAMES:
            write_csv(name, tables[name][0], expected[name])
        for name, value in outputs.items():
            (HERE / name).write_text(json.dumps(value, indent=2) + '\n')
    else:
        for name, value in outputs.items():
            if json.loads((HERE / name).read_text()) != value:
                raise ValueError('Stale reference companion: ' + name)
    return {key: value for key, value in report.items() if key not in {'included_manuscript_sources', 'verified_evidence_paths'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.write), indent=2))


if __name__ == '__main__':
    main()
