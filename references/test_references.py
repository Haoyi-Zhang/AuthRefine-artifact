"""Focused failure controls for standalone reference and data verification."""
from __future__ import annotations

import copy
import csv
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import claims
import metadata
import refresh


class ReferenceControls(unittest.TestCase):
    def test_included_sources_exclude_comments_and_unreachable_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paper = Path(directory)
            (paper / 'main.tex').write_text('\\input{body}\n% \\input{unreachable}\n')
            (paper / 'supplement.tex').write_text('\\input{details}\n')
            (paper / 'body.tex').write_text('\\input{shared}\n')
            (paper / 'details.tex').write_text('\\input{shared}\n')
            (paper / 'shared.tex').write_text('A shared macro file.\n')
            (paper / 'unreachable.tex').write_text('\\cite{not_a_current_citation}\n')
            with mock.patch.object(refresh, 'PAPER', paper):
                sources, external, trees = refresh.included_sources(with_trees=True)
            self.assertEqual({path.name for path in sources},
                             {'main.tex', 'supplement.tex', 'body.tex', 'details.tex', 'shared.tex'})
            self.assertEqual(external, [])
            self.assertIn(paper / 'shared.tex', trees['main.tex'])
            self.assertIn(paper / 'shared.tex', trees['supplement.tex'])

    def test_comment_mask_keeps_escaped_percent_and_line_positions(self):
        source = 'A \\% token. % \\cite{commented}\n\\cite{included}\n'
        masked = refresh.uncomment(source)
        self.assertEqual(len(masked), len(source))
        self.assertEqual(masked.count('\n'), source.count('\n'))
        self.assertIn('\\%', masked)
        self.assertEqual(refresh.CITE_RE.findall(masked), ['included'])

    def test_preserved_reading_scope_cannot_be_silently_upgraded(self):
        with (refresh.ARTIFACT / 'reference_audit.csv').open(newline='') as stream:
            rows = {row['citation_key']: row for row in csv.DictReader(stream)}
        self.assertEqual(refresh.check_readings(rows), len(rows))
        key = next(iter(rows))
        rows[key]['reading_scope'] = 'Claimed complete full-text reading'
        with self.assertRaisesRegex(ValueError, 'Recorded reading changed'):
            refresh.check_readings(rows)

    def test_wrong_bibliography_title_fails_primary_metadata(self):
        parsed = metadata.parse_bibtex((metadata.PAPER / 'references.bib').read_text())
        changed = copy.deepcopy(parsed)
        changed['classen2011symbolic']['fields']['title'] = 'An unrelated publication'
        with mock.patch.object(metadata, 'parse_bibtex', return_value=changed):
            report = metadata.derive()
        self.assertEqual(report['status'], 'fail')
        self.assertIn({'key': 'classen2011symbolic', 'fields': ['title']},
                      report['unresolved_field_mismatches'])

    def test_undated_documentation_does_not_take_its_access_year(self):
        parsed = metadata.parse_bibtex((metadata.PAPER / 'references.bib').read_text())
        self.assertEqual(parsed['healthchecks_api']['fields']['year'], 'n.d.')
        report = metadata.derive()
        row = next(row for row in report['results'] if row['citation_key'] == 'healthchecks_api')
        self.assertTrue(all(row['checks'].values()))
        changed = copy.deepcopy(parsed)
        changed['healthchecks_api']['fields']['year'] = changed['healthchecks_api']['fields']['urldate'][:4]
        with mock.patch.object(metadata, 'parse_bibtex', return_value=changed):
            report = metadata.derive()
        self.assertIn({'key': 'healthchecks_api', 'fields': ['year']},
                      report['unresolved_field_mismatches'])

    def test_excluded_history_is_not_a_delivery_dependency(self):
        row = {'claim': 'example', 'proof': '', 'source_or_test': '',
               'raw_evidence': 'results/journal-audit-20261119/evidence/metadata-verification.json'}
        with self.assertRaisesRegex(ValueError, 'excluded historical work directory'):
            refresh.evidence_paths([row])

    def test_missing_evidence_path_is_rejected(self):
        row = {'claim': 'example', 'proof': '', 'source_or_test': '',
               'raw_evidence': 'results/absent-reference-control/summary.json'}
        with self.assertRaisesRegex(ValueError, 'Missing declared evidence paths'):
            refresh.evidence_paths([row])

    def test_replay_must_keep_binding_and_stop_at_first_failure(self):
        row = {'binding': {'x': 'r'}, 'equivalent': False, 'length': 1,
               'indices': [0], 'trace': [{'binding': {'x': 'r'}, 'compared_equal': False}]}
        self.assertEqual(claims.profile_length(row), 1)
        changed = copy.deepcopy(row)
        changed['trace'][0]['binding']['x'] = 's'
        with self.assertRaisesRegex(ValueError, 'changed the fixed binding'):
            claims.profile_length(changed)
        changed = copy.deepcopy(row)
        changed['trace'][0]['compared_equal'] = True
        with self.assertRaisesRegex(ValueError, 'no final recorded failure'):
            claims.profile_length(changed)

    def test_changed_timing_median_is_rejected(self):
        read = claims.read
        def modified(relative):
            value = read(relative)
            if relative == 'results/session-correspondence/timing.json':
                value['cases'][0]['methods']['support-indexed']['diagnosis_wall_ns']['median'] += 1
            return value
        with mock.patch.object(claims, 'read', side_effect=modified):
            with self.assertRaisesRegex(ValueError, 'Native timing full summary'):
                claims.native_timing()

    def test_changed_complete_symbolic_timing_is_rejected(self):
        read = claims.read
        def modified(relative):
            value = read(relative)
            if relative == 'results/symbolic-comparison/summary.json':
                value['records'][0]['methods']['cudd']['diagnosis_wall_ns']['median'] += 1
            return value
        with mock.patch.object(claims, 'read', side_effect=modified):
            with self.assertRaisesRegex(ValueError, 'Unified timing summary'):
                claims.complete_symbolic_comparison()

    def test_richer_replay_identity_cannot_be_dropped(self):
        read = claims.read
        def modified(relative):
            value = read(relative)
            if relative == 'results/session-observation/identity-profiles.json.gz':
                rows = [r for case in value for records in case['callers'].values()
                        for r in records if not r['equivalent'] and not r['trace'][-1]['identity_equal']]
                rows[0]['trace'][-1]['identity_equal'] = True
            return value
        with mock.patch.object(claims, 'read', side_effect=modified):
            with self.assertRaisesRegex(ValueError, 'Identity-determined exclusions'):
                claims.additional_native_records()


if __name__ == '__main__':
    unittest.main()
