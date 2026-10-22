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
        for change in ({'verified': False}, {'years': [2025]}, {'issns': ['0000-0000']}, {'rank': 'Q3'}):
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
        self.assertFalse(self.select([work], self.ranks + [dict(newer, rank='Q3')])[0])
        self.assertFalse(self.select([work], [dict(newer, years=[2023])])[0])

    def test_split_author_ids_and_institution_guard(self):
        self.authors[0]['openalex_ids'] = ['A1', 'A3']
        self.authors[0]['required_institution_id'] = 'IUGM'
        self.work['authorships'] = [{'author': {'id': 'https://openalex.org/A3'},
                                     'institutions': [{'id': 'https://openalex.org/IOTHER'}]}]
        self.assertFalse(self.select([self.work])[0])
        self.work['authorships'][0]['institutions'] = [{'id': 'https://openalex.org/IUGM'}]
        self.assertEqual(self.select([self.work])[0][0]['staff'], ['A'])


if __name__ == '__main__':
    unittest.main()
