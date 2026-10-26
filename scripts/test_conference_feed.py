import copy
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import update_conference_feed as collector
from update_conference_feed import select_conferences, merge_contributions, date_range_label


class ConferenceTests(unittest.TestCase):
    def test_compact_date_ranges(self):
        self.assertEqual(date_range_label('2025-07-23', '2025-07-25'), '23–25 Juli 2025')
        self.assertEqual(date_range_label('2025-07-23', '2025-08-25'), '23 Juli–25 Agustus 2025')
        self.assertEqual(date_range_label('2025-12-23', '2026-01-25'), '23 Desember 2025–25 Januari 2026')
        self.assertEqual(date_range_label('2025-07-23'), '23 Juli 2025')

    def setUp(self):
        self.today = date(2026, 10, 26)
        self.authors = [{'name': 'Sismanto', 'verified': True, 'openalex_id': 'A1'}]
        self.work = {'id': 'W1', 'title': 'Conference paper', 'type': 'conference-paper',
                     'doi': '10.1234/conference', 'publication_date': '2024-07-01',
                     'authorships': [{'author': {'id': 'A1', 'display_name': 'Sismanto Sismanto'}}]}
        self.metadata = {'https://doi.org/10.1234/conference': {'type': 'proceedings-article',
            'published': {'date-parts': [[2024, 7, 1]]}, 'container-title': ['Proceedings Collection'],
            'event': {'name': 'Example conference', 'start': {'date-parts': [[2024, 3, 1]]},
                      'end': {'date-parts': [[2024, 3, 3]]}, 'location': 'Yogyakarta, Indonesia'}}}

    def select(self, overrides=None):
        return select_conferences([self.work], self.authors, self.metadata, overrides or [], self.today)

    def test_event_date_different_from_publication_date(self):
        record = self.select()[0][0]
        self.assertEqual(record['conference_start'], '2024-03-01')
        self.assertEqual(record['publication_date'], '2024-07-01')
        self.assertEqual(record['city'], 'Yogyakarta')
        self.assertEqual(record['country'], 'Indonesia')
        self.assertEqual(record['staff_author_names'], ['Sismanto'])

    def test_no_oral_poster_or_online_inference(self):
        self.metadata['https://doi.org/10.1234/conference']['event']['location'] = 'Vienna, Austria & Online'
        record = self.select()[0][0]
        self.assertIsNone(record['online'])
        self.assertIsNone(record['presentation_type'])

    def test_explicit_reviewed_presentation_flags(self):
        patch = {'doi': 'https://doi.org/10.1234/conference', 'verified': True,
                 'presentation_type': 'Poster', 'online': True, 'evidence_url': 'https://organizer.example/program'}
        record = self.select([patch])[0][0]
        self.assertEqual(record['presentation_type'], 'Poster')
        self.assertTrue(record['online'])

    def test_abstract_not_promoted_by_crossref_generic_type(self):
        self.work['type'] = 'conference-abstract'
        self.assertEqual(self.select()[0][0]['publication_kind'], 'Abstrak')

    def test_unknown_event_date_is_not_publication_date(self):
        self.metadata['https://doi.org/10.1234/conference'].pop('event')
        record = self.select()[0][0]
        self.assertIsNone(record['conference_start'])

    def test_missing_event_pills_move_to_publication_line(self):
        self.metadata['https://doi.org/10.1234/conference'].pop('event')
        record = self.select()[0][0]
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            page = base / 'page'
            page.mkdir()
            (page / 'conferences.js').write_text('', encoding='utf-8')
            with patch.multiple(collector, BASE=base, PAGE=page):
                collector.render({'conferences': [record], 'authors': self.authors,
                                  'as_of': '2026-10-26', 'start_year': 2022})
            html = (page / '01-conferences-wordpress.html').read_text(encoding='utf-8')
            self.assertNotIn('class="gf-conf-meta"', html)
            self.assertNotIn('belum tersedia', html)
            publication = html.split('class="gf-conf-publication"', 1)[1].split('</p>', 1)[0]
            self.assertIn('gf-conf-prosiding', publication)

    def test_country_only_and_ambiguous_location(self):
        event = self.metadata['https://doi.org/10.1234/conference']['event']
        event['location'] = 'Indonesia'
        self.assertEqual(self.select()[0][0]['country'], 'Indonesia')
        self.assertIsNone(self.select()[0][0]['city'])
        event['location'] = 'Boston, MA'
        self.assertIsNone(self.select()[0][0]['country'])

    def test_proceedings_priority_with_explicit_group(self):
        abstract = self.select()[0][0]
        abstract.update(contribution_id='confirmed-same-contribution', publication_kind='Abstrak')
        paper = dict(abstract, doi='https://doi.org/10.1234/paper', publication_kind='Prosiding')
        merged = merge_contributions([abstract, paper])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['publication_kind'], 'Prosiding')

    def test_similar_titles_alone_do_not_establish_duplicates(self):
        first = self.select()[0][0]
        second = dict(first, id='W2', doi='https://doi.org/10.1234/other')
        self.assertEqual(len(merge_contributions([first, second])), 2)

    def test_standalone_presentation_without_link_or_publication(self):
        entry = {'id': 'organizer-1', 'verified': True, 'title': 'Oral presentation',
                 'conference_name': 'Example', 'conference_start': '2025-01-01',
                 'authors': ['Sismanto'], 'staff': ['Sismanto'], 'presentation_type': 'Oral',
                 'evidence_url': 'https://organizer.example/program'}
        record = select_conferences([], self.authors, {}, [entry], self.today)[0][0]
        self.assertIsNone(record['url'])
        self.assertIsNone(record['publication_date'])
        self.assertIsNone(record['publication_kind'])
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            page = base / 'page'
            page.mkdir()
            (page / 'conferences.js').write_text('', encoding='utf-8')
            with patch.multiple(collector, BASE=base, PAGE=page):
                collector.render({'conferences': [record], 'authors': self.authors,
                                  'as_of': '2026-10-26', 'start_year': 2022})
            html = (page / '01-conferences-wordpress.html').read_text(encoding='utf-8')
            self.assertNotIn('class="gf-conf-access"', html)
            self.assertNotIn('class="gf-conf-publication"', html)
            self.assertIn('gf-conf-oral', html)

    def test_namesakes_retracted_and_old_events_excluded(self):
        self.authors[0]['required_institution_id'] = 'IUGM'
        self.assertEqual(self.select()[0], [])
        self.work['authorships'][0]['institutions'] = [{'id': 'IUGM'}]
        self.assertTrue(self.select()[0])
        self.work['is_retracted'] = True
        self.assertEqual(self.select()[0], [])
        self.work['is_retracted'] = False
        self.metadata['https://doi.org/10.1234/conference']['event']['start'] = {'date-parts': [[2021]]}
        self.assertEqual(self.select()[0], [])


if __name__ == '__main__':
    unittest.main()
