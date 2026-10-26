import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from update_journal_rankings import parse_scimago, parse_notice, merge, refresh_rankings, SCIMAGO
from update_publication_feed import select_works


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 10, 22)
        self.url = 'https://www.scimagojr.com/journalrank.php?year=2025&out=xls'
        self.csv = b'Title;Issn;SJR Best Quartile;Type\nJournal;1234567X;Q3;journal\nOther;99999999;Q1;journal\n'

    def test_exact_issn_and_downgrade_retained(self):
        records = parse_scimago(self.csv, 2025, self.url, self.today, {'1234567X': 'Journal'})
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['rank'], 'Q3')
        self.assertEqual(records[0]['years'], [2025])

    def test_challenge_and_changed_format_rejected(self):
        for raw in [b'<html>challenge</html>', b'Title;Rank\nJournal;Q1']:
            with self.assertRaises(ValueError):
                parse_scimago(raw, 2025, self.url, self.today, {})

    def test_conflicting_duplicate_issn_rejected(self):
        with self.assertRaises(ValueError):
            parse_scimago(self.csv + b'Journal;1234567X;Q1;journal\n', 2025, self.url, self.today, {'1234567X': 'Journal'})

    def notice(self):
        return {'journal': 'Journal', 'issns': ['1234-567X'], 'url': 'https://publisher.example/accreditation',
                'pattern': r'Sinta (?P<rank>[1-6]) decree (?P<decree>[\w/]+) valid (?P<start>20\d{2}) to (?P<end>20\d{2})'}

    def test_notice_requires_issn_decree_rank_and_period(self):
        raw = b'<p>ISSN 1234-567X. Sinta 2 decree 10/2025 valid 2024 to 2027</p>'
        record = parse_notice(raw, self.notice(), self.today)[0]
        self.assertEqual(record['years'], [2025, 2026])
        for raw in [b'Sinta 2 decree 10/2025 valid 2024 to 2027', b'ISSN 1234-567X Sinta 2 Accredited']:
            with self.assertRaises(ValueError):
                parse_notice(raw, self.notice(), self.today)

    def test_real_publisher_sentence_shape(self):
        config = json.loads((Path(__file__).resolve().parents[1] / 'widgets/publication-feed/ranking-sources.json').read_text(encoding='utf-8'))
        source = config['publisher_notices'][0]
        raw = b'ISSN 0125-9849. Riset Geologi dan Pertambangan is nationally accredited Rank 2 (Sinta 2) by the Director, under Decree No. 10/C/C3/DT.05.00/2025. This accreditation status is valid from Volume 32 Number 2 (2022) to Volume 37 Number 1 (2027)'
        self.assertEqual(parse_notice(raw, source, self.today)[0]['years'], [2023, 2024, 2025, 2026])

    def test_refresh_is_idempotent_and_preserves_manual_evidence(self):
        record = parse_scimago(self.csv, 2025, self.url, self.today, {'1234567X': 'Journal'})[0]
        manual = dict(record, automatic=False)
        once = merge([manual], [record])
        self.assertEqual(merge(once, [record]), once)

    def test_source_failure_retains_previous_evidence_and_queues_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'ranking-sources.json').write_text('{"scimago": true}')
            def fail(url, robots):
                raise ValueError('blocked')
            existing = [{'journal': 'Known', 'issns': ['1234-567X'], 'system': SCIMAGO,
                         'rank': 'Q1', 'verified': True, 'years': [2024]}]
            works = [{'primary_location': {'source': {'type': 'journal', 'issn': ['9999-9999'], 'display_name': 'Unknown'}}}]
            records, report = refresh_rankings(root, works, existing, self.today, fail)
            self.assertEqual(records, existing)
            self.assertEqual(len(report['review']), 1)
            self.assertTrue(all(s['status'] == 'unavailable_or_unverified' for s in report['sources']))

    def test_newer_q3_replaces_old_q1_carry_forward(self):
        records = parse_scimago(self.csv, 2025, self.url, self.today, {'1234567X': 'Journal'})
        old = dict(records[0], rank='Q1', years=[2024])
        work = {'id': 'W1', 'title': 'Paper', 'publication_date': '2026-01-01', 'type': 'article',
                'doi': '10.1234/paper', 'authorships': [{'author': {'id': 'A1'}}],
                'primary_location': {'source': {'type': 'journal', 'issn': ['1234-567X']}}}
        selected, _ = select_works([work], [{'name': 'Staff', 'openalex_id': 'A1', 'verified': True}], [old] + records, self.today)
        self.assertEqual(selected[0]['rankings'][0]['label'], 'Q3')


if __name__ == '__main__':
    unittest.main()
