import copy
from datetime import date
import unittest
from update_publication_feed import select_works, doi_url, safe_url, publication_date, date_label, author_label, staff_label


class PublicationSelectionTests(unittest.TestCase):
    def setUp(self):
        self.authors = [{'name': 'A', 'openalex_id': 'A1', 'verified': True},
                        {'name': 'B', 'openalex_id': 'A2', 'verified': True}]
        self.ranks = [{'rank': 'Q1', 'system': 'SCImago', 'years': [2024], 'verified': True,
                       'issns': ['1234-567X'], 'evidence_url': 'https://example.org/ranking'}]
        self.work = {'id': 'W1', 'title': 'A real-shaped record', 'publication_date': '2024-03-01',
                     'type': 'article', 'doi': 'https://doi.org/10.1234/TEST',
                     'authorships': [{'author': {'id': 'https://openalex.org/A1'}}],
                     'primary_location': {'source': {'type': 'journal', 'issn': ['1234567x'], 'display_name': 'Journal'},
                                          'landing_page_url': 'https://example.org/article/1'}}

    def select(self, works, ranks=None):
        return select_works(works, self.authors, self.ranks if ranks is None else ranks, date(2026, 10, 21))

    def test_doi_normalization_and_coauthor_deduplication(self):
        duplicate = copy.deepcopy(self.work)
        duplicate['doi'] = 'doi:10.1234/test'
        duplicate['authorships'] = [{'author': {'id': 'https://openalex.org/A2'}}]
        rows, _ = self.select([self.work, duplicate])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['staff'], ['A', 'B'])

    def test_no_doi_uses_article_landing_page(self):
        self.work['doi'] = None
        rows, _ = self.select([self.work])
        self.assertEqual(rows[0]['url'], 'https://example.org/article/1')

    def test_ranking_must_be_verified_and_match_year_and_issn(self):
        for change in ({'verified': False}, {'years': [2025]}, {'issns': ['0000-0000']}, {'rank': 'Sinta 3'}):
            ranking = dict(self.ranks[0], **change)
            rows, review = self.select([self.work], [ranking])
            self.assertFalse(rows)
            self.assertEqual(review[0]['reason'], 'unverified_or_ineligible_ranking')

    def test_retractions_future_dates_and_proceedings_are_excluded(self):
        for change in ({'is_retracted': True}, {'publication_date': '2026-12-01'}, {'type': 'proceedings-article'}):
            rows, _ = self.select([dict(self.work, **change)])
            self.assertFalse(rows)

    def test_unverified_author_and_unsafe_links_are_excluded(self):
        self.work['authorships'].append({'author': {'id': None}})
        self.assertEqual(len(self.select([self.work])[0]), 1)
        self.authors[0]['verified'] = False
        self.assertFalse(self.select([self.work])[0])
        self.assertIsNone(safe_url('javascript:alert(1)'))
        self.assertIsNone(doi_url('https://example.org/not-a-doi'))

    def test_date_precision_fallbacks(self):
        for value, label in [('2024-10-27', '27 Oktober 2024'), ('2024-10', 'Oktober 2024'), ('2024', '2024')]:
            published, display = publication_date({'publication_date': value})
            self.assertEqual(published.year, 2024)
            self.assertEqual(date_label(display), label)
        self.assertEqual(publication_date({'publication_date': 'invalid', 'publication_year': 2024})[1], '2024')
        self.assertIsNone(publication_date({})[0])

    def test_author_display_rules(self):
        self.assertEqual(author_label(['First Writer', 'Second Writer', 'Third Writer']), 'First Writer, Second Writer, and Third Writer')
        self.assertEqual(author_label(['First Writer', 'B', 'C', 'D']), 'Writer et al.')
        self.assertEqual(staff_label(['Ade Anggraini', 'Herlan Darmawan', 'Wiwit Suryanto']), 'Ade A., Herlan D., and Wiwit S. terlibat sebagai penulis publikasi ini.')

    def test_2024_ranking_carries_forward_with_provenance(self):
        for year in (2025, 2026):
            rows, _ = self.select([dict(self.work, publication_date=f'{year}-03-01')])
            self.assertEqual(rows[0]['rankings'][0]['evidence_year'], 2024)
            self.assertTrue(rows[0]['rankings'][0]['assumed'])

    def test_newer_rank_overrides_fallback_and_older_window_is_rejected(self):
        work = dict(self.work, publication_date='2026-03-01')
        newer = dict(self.ranks[0], years=[2025], rank='Q2')
        rows, _ = self.select([work], self.ranks + [newer])
        self.assertEqual(rows[0]['rankings'][0]['label'], 'Q2')
        self.assertEqual(self.select([work], self.ranks + [dict(newer, rank='Q3')])[0][0]['rankings'][0]['label'], 'Q3')
        self.assertFalse(self.select([work], [dict(newer, years=[2021])])[0])

    def test_split_author_ids_and_institution_guard(self):
        self.authors[0]['openalex_ids'] = ['A1', 'A3']
        self.authors[0]['required_institution_id'] = 'IUGM'
        self.work['authorships'] = [{'author': {'id': 'https://openalex.org/A3'},
                                     'institutions': [{'id': 'https://openalex.org/IOTHER'}]}]
        self.assertFalse(self.select([self.work])[0])
        self.work['authorships'][0]['institutions'] = [{'id': 'https://openalex.org/IUGM'}]
        self.assertEqual(self.select([self.work])[0][0]['staff'], ['A'])

    def test_five_year_window_and_q3_q4(self):
        for rank in ['Q3', 'Q4']:
            ranking = dict(self.ranks[0], years=[2022], rank=rank)
            work = dict(self.work, publication_date='2022-01-01')
            self.assertEqual(self.select([work], [ranking])[0][0]['rankings'][0]['label'], rank)
            self.assertFalse(self.select([dict(work, publication_date='2021-12-31')], [ranking])[0])
            self.assertFalse(self.select([work], self.ranks)[0])  # No backwards extrapolation from 2024.

    def test_mononym_display_variants_are_canonical_and_boldable(self):
        self.authors[0]['name'] = 'Sismanto'
        for variant in ['Sismanto', 'Sismanto Sismanto', 'S. Sismanto']:
            self.work['authorships'] = [{'author': {'id': 'A1', 'display_name': variant}}]
            record = self.select([self.work])[0][0]
            self.assertEqual(record['all_authors'], ['Sismanto'])
            self.assertEqual(record['staff_author_names'], ['Sismanto'])

    def test_name_alone_does_not_attach_a_namesake(self):
        self.authors[0]['name'] = 'Sismanto'
        self.work['authorships'] = [{'author': {'id': 'A_OTHER', 'display_name': 'Sismanto'}}]
        self.assertFalse(self.select([self.work])[0])

    def test_pending_support_staff_do_not_break_selection(self):
        self.authors.append({'name': 'Support Staff', 'verified': False, 'openalex_ids': []})
        self.assertEqual(len(self.select([self.work])[0]), 1)

    def test_sudarmaji_saroji_variant_uses_verified_alias_id(self):
        self.authors[0].update(name='Sudarmaji', openalex_ids=['A1', 'A_SAROJI'], required_institution_id='IUGM')
        self.work['authorships'] = [{'author': {'id': 'A_SAROJI', 'display_name': 'Sudarmaji Saroji'},
                                     'institutions': [{'id': 'IUGM'}]}]
        record = self.select([self.work])[0][0]
        self.assertEqual(record['staff'], ['Sudarmaji'])
        self.assertEqual(record['staff_author_names'], ['Sudarmaji Saroji'])


if __name__ == '__main__':
    unittest.main()
