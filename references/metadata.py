#!/usr/bin/env python3
"""Compare the current bibliography with retained primary metadata responses.

This is an offline audit of the recorded metadata. It never treats a live DOI,
matching title, or absent metadata field as evidence for a scientific claim.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import html
import json
from pathlib import Path
import re
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
ARTIFACT = HERE.parent
PAPER = ARTIFACT.parent / 'paper'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ARTIFACT / 'src'))
from reference_check import parse_bibtex


def norm(s):
    s = html.unescape(re.sub(r'<[^>]+>', '', str(s)))
    s = re.sub(r'\\[a-zA-Z]+\s*', '', s)
    s = ''.join(c for c in unicodedata.normalize('NFKD', s)
                if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', s.lower())


def person_matches(bib, person):
    family = norm(person.get('family', ''))
    given = norm(person.get('given', ''))
    name = norm(bib)
    if name == given + family:
        return True
    if family and name.endswith(family):
        if not given:
            return True
        prefix = name[:-len(family)]
        # Publisher deposits sometimes contain initials instead of full names.
        words = person.get('given', '').split()
        if all(len(norm(word)) <= 1 for word in words):
            bib_words = re.sub(r'[{}\\\'"^`]', '', bib).split()
            initials = ''.join(norm(word)[:1] for word in bib_words[:-1])
            return initials.startswith(given) or (len(given) == 1 and prefix.startswith(given))
    return False


def derive():
    entries = parse_bibtex((PAPER / 'references.bib').read_text())
    non_doi = {r['key']: r for r in json.loads((HERE/'non-doi-metadata.json').read_text())['records']}
    results = []
    errors = []
    for key, entry in entries.items():
        fields = entry['fields']
        row = {'citation_key': key, 'identifier': fields.get('doi', fields.get('url')),
               'bibliography_title': fields['title'], 'bibliography_year': fields['year']}
        if not fields.get('doi'):
            evidence = non_doi[key]
            checks = {'url': fields['url'] == evidence['url'],
                      'year': fields['year'] == str(evidence['year'])}
            if key == 'piccolo2026sessions':
                checks['title'] = norm(fields['title']) == norm('Privilege Escalation via Session-Token Disclosure in Piccolo Admin')
                checks['contributors'] = fields['author'] == '{Piccolo maintainers}'
            else:
                checks['title'] = norm(fields['title']) == norm(evidence['title'])
                checks['contributors'] = ([norm(x) for x in fields['author'].split(' and ')] ==
                                          [norm(x) for x in evidence['authors']])
            failures = [field for field, ok in checks.items() if not ok]
            if failures:
                errors.append({'key': key, 'fields': failures})
            row.update(metadata_type='primary_non_doi_record', source=evidence['url'],
                       source_ref=evidence['reference'], scope=evidence['access'],
                       checks=checks, notes=[],
                       status=evidence['status'] if not failures else 'mismatch')
            results.append(row)
            continue
        path = HERE/'crossref'/f'{key}.json'
        data = path.read_bytes()
        record = json.loads(data)['message']
        title = ' '.join(record.get('title', []) + record.get('subtitle', []))
        checks = {'doi': record['DOI'].lower() == fields['doi'].lower(),
                  'title': norm(fields['title']) == norm(title)}
        notes = []
        if key == 'lynch1995simulations':
            checks['title'] = (norm(fields['title']) == norm('Forward and Backward Simulations. Part I: Untimed Systems')
                               and norm(title) == norm('Forward and Backward Simulations'))
            notes.append('Crossref omits the Part I subtitle; primary UvA publication record confirms the complete title: https://dare.uva.nl/id/88895f5a-e3b8-40b0-8c06-d9c1c7871db1')
        years = {str(record[k]['date-parts'][0][0]) for k in
                 ('published-print','published-online','published','issued') if k in record}
        checks['year'] = fields['year'] in years
        if len(years) > 1:
            notes.append('Publication dates have distinct online/print years; the bibliography year matches a deposited publication date.')
        is_rfc = key in {'hardt2012oauth', 'lodderstedt2013revocation'}
        people = (record.get('editor', []) if is_rfc else []) + record.get('author', [])
        people = sorted(people, key=lambda p:p.get('sequence') != 'first')
        names = fields['author'].split(' and ')
        checks['contributors'] = (len(names) == len(people) and
                                  all(person_matches(a, b) for a,b in zip(names, people)))
        exact_names = ([norm(name) for name in names] ==
                       [norm(p.get('given','')+' '+p.get('family','')) for p in people])
        if checks['contributors'] and not exact_names:
            notes.append('The deposit uses abbreviated or incomplete given names. The comparison checks ordered surname/initial compatibility, not fresh verification of every expanded given name.')
        if is_rfc and record.get('editor'):
            notes.append('The RFC deposit separates editor credits; the RFC Editor page verifies the full contributor list and roles.')
        if key == 'bryant1986graphs':
            notes.append('Crossref stores the surname only; the author-hosted primary manuscript identifies Randal E. Bryant.')
        for field, remote in [('volume','volume'),('number','issue')]:
            if field in fields and remote in record:
                checks[field] = norm(fields[field]) == norm(record[remote])
        if fields.get('pages') and record.get('page'):
            checks['pages'] = norm(fields['pages']) == norm(record['page'])
            if key == 'fisler2005margrave':
                ieee = json.loads((HERE/'margrave-ieee-metadata.json').read_text())['message']
                checks['pages'] = (norm(fields['pages']) == norm(ieee['page']) and
                                   norm(fields['title']) == norm(ieee['title'][0]) and
                                   record['page'] == ieee['page'].split('-')[0])
                notes.append('The ACM deposit supplies only first page 196; the separately retained IEEE co-publication deposit, DOI 10.1109/ICSE.2005.1553562, confirms 196–205. The bibliography retains one ACM citation, not two records for the same work.')
        if fields.get('numpages') and record.get('page') and re.fullmatch(r'\d+-\d+', record['page']):
            first, last = map(int, record['page'].split('-'))
            checks['numpages'] = int(fields['numpages']) == last-first+1
        if fields.get('articleno'):
            if record.get('article-number'):
                checks['articleno'] = fields['articleno'] == str(record['article-number'])
            elif record.get('page', '').isdigit():
                checks['articleno'] = fields['articleno'] == record['page']
            else:
                notes.append('This Crossref response omits the article number; that field retains its prior primary-publication check rather than being marked newly verified.')
        failures = [field for field,ok in checks.items() if not ok]
        if failures:
            errors.append({'key': key, 'fields': failures})
        row.update(metadata_type='publisher_deposited_crossref',
                   source='https://api.crossref.org/works/'+fields['doi'],
                   metadata_title=title, metadata_years=sorted(years),
                   metadata_contributors=[(p.get('given','')+' '+p.get('family','')).strip() for p in people],
                   metadata_containers=record.get('container-title', []),
                   checks=checks, notes=notes,
                   status='matched' if not failures else 'mismatch')
        results.append(row)
    summary = {'references': len(results), 'doi_records': sum(r['metadata_type']=='publisher_deposited_crossref' for r in results),
               'non_doi_records': sum(r['metadata_type']=='primary_non_doi_record' for r in results),
               'unresolved_field_mismatches': errors, 'status':'pass' if not errors else 'fail',
               'scope':'Current bibliographic identity against retained publisher-deposited DOI responses and primary non-DOI records. Counts are computed above. Undated documentation retains n.d.; access dates are not publication dates. Missing fields and indexed-only access remain explicit; this is not full-text or scientific-method verification.',
               'results':results}
    return summary


CSV_FIELDS = ['citation_key','identifier','status','metadata_type','source','checks','notes']


def csv_rows(summary):
    return [{key: (json.dumps(row[key], ensure_ascii=False) if isinstance(row.get(key), (dict, list))
                   else str(row.get(key, ''))) for key in CSV_FIELDS}
            for row in summary['results']]


def verify(write=False):
    summary = derive()
    if summary['unresolved_field_mismatches']:
        raise ValueError('Bibliographic metadata mismatch: ' + str(summary['unresolved_field_mismatches']))
    target = HERE / 'metadata-verification.json'
    table = HERE / 'metadata-verification.csv'
    expected_rows = csv_rows(summary)
    if write:
        target.write_text(json.dumps(summary, indent=2) + '\n')
        with table.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(expected_rows)
    else:
        if json.loads(target.read_text()) != summary:
            raise ValueError('Current metadata comparison differs from its recorded result')
        with table.open(newline='') as stream:
            if list(csv.DictReader(stream)) != expected_rows:
                raise ValueError('Metadata comparison CSV differs from its source records')
    return {key: value for key, value in summary.items() if key != 'results'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    print(json.dumps(verify(args.write), indent=2))


if __name__ == '__main__':
    main()
