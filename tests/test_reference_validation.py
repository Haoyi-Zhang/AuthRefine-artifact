"""Bibliography revisions preserve metadata integrity without frozen dates."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import reference_check


class ReferenceValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='owned-reference-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inventory = reference_check.load_csv(ROOT / 'reference_inventory.csv')
        self.audit = reference_check.load_csv(ROOT / 'reference_audit.csv')

    def validate(self):
        paths = []
        for name, rows in (('inventory.csv', self.inventory), ('audit.csv', self.audit)):
            path = self.root / name
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            paths.append(path)
        return reference_check.validate(inventory_path=paths[0], audit_path=paths[1])

    def test_valid_updated_reading_date_is_recorded_not_rejected_as_stale(self):
        self.audit[0]['access_date'] = '2026-11-18'
        report = self.validate()
        self.assertEqual(report['audit_access_dates'], sorted({row['access_date'] for row in self.audit}))
        self.assertEqual(report['references'], len(self.inventory))

    def test_invalid_calendar_date_does_not_enter_metadata_report(self):
        self.audit[0]['access_date'] = '2026-02-30'
        with self.assertRaisesRegex(ValueError, 'invalid access date'):
            self.validate()

    def test_doi_case_cannot_double_count_one_publication(self):
        first, second = [row for row in self.inventory if row['identifier_type'] == 'doi'][:2]
        second['publication_identifier'] = 'https://doi.org/' + first['publication_identifier'].removeprefix('https://doi.org/').upper()
        for row in self.audit:
            if row['citation_key'] == second['citation_key']:
                row['publication_identifier'] = second['publication_identifier']
        with self.assertRaisesRegex(ValueError, 'duplicate publication identifier'):
            self.validate()

    def test_primary_software_sources_keep_their_publication_kind(self):
        examples = (
            ('manual', 'https://healthchecks.io/docs/api/', 'software_documentation'),
            ('misc', 'https://github.com/healthchecks/healthchecks/issues/346', 'software_issue'),
            ('misc', 'https://github.com/healthchecks/healthchecks/commit/1f1b1aedca949a52a592f8aefc523ad47b054ed9', 'software_change'),
        )
        for entry_type, url, expected_kind in examples:
            with self.subTest(kind=expected_kind):
                self.assertEqual(reference_check.entry_identifier(
                    {'entry_type': entry_type, 'fields': {'url': url}}), (expected_kind, url))
        for url in ('https://github.com/healthchecks/healthchecks/issues/not-an-issue',
                    'https://github.com/healthchecks/healthchecks/commit/1f1b1aed'):
            with self.subTest(invalid=url):
                with self.assertRaisesRegex(ValueError, 'no recognized'):
                    reference_check.entry_identifier({'entry_type': 'misc', 'fields': {'url': url}})


if __name__ == '__main__':
    unittest.main()
