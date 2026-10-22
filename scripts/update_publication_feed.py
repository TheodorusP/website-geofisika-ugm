"""Collect the teaching-staff publication feed. Standard library only; no Scholar scraping."""
from pathlib import Path
from datetime import date, datetime, timezone, timedelta
from urllib.parse import urlencode, urlsplit, unquote
from html import escape
from format_page_html import format_html
from update_journal_rankings import refresh_rankings
import argparse
import json
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1] / 'widgets/publication-feed'
ALLOWED = {'Q1', 'Q2', 'Sinta 1', 'Sinta 2'}
MONTHS = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
          'Agustus', 'September', 'Oktober', 'November', 'Desember']


def publication_date(work):
    value = str(work.get('publication_date') or '')
    for pattern, suffix in ((r'\d{4}-\d{2}-\d{2}', ''), (r'\d{4}-\d{2}', '-01'), (r'\d{4}', '-01-01')):
        if re.fullmatch(pattern, value):
            try:
                return date.fromisoformat(value + suffix), value
            except ValueError:
                pass
    year = str(work.get('publication_year') or '')
    if re.fullmatch(r'\d{4}', year) and 1 <= int(year) <= 9999:
        return date(int(year), 1, 1), year
    return None, None


def date_label(value):
    parts = value.split('-')
    if len(parts) == 3:
        return f'{int(parts[2])} {MONTHS[int(parts[1])-1]} {parts[0]}'
    if len(parts) == 2:
        return f'{MONTHS[int(parts[1])-1]} {parts[0]}'
    return parts[0]


def join_names(names):
    if len(names) < 2:
        return ''.join(names)
    if len(names) == 2:
        return ' and '.join(names)
    return ', '.join(names[:-1]) + ', and ' + names[-1]


def author_label(names):
    if len(names) <= 3:
        return join_names(names)
    return names[0].split()[-1] + ' et al.'


def staff_label(names):
    def short(name):
        parts = name.split()
        return parts[0] + (' ' + ''.join(p[0] + '.' for p in parts[1:]) if len(parts) > 1 else '')
    return join_names([short(name) for name in names]) + ' terlibat sebagai penulis publikasi ini.'


def safe_url(value):
    if not isinstance(value, str):
        return None
    parts = urlsplit(value)
    return value if parts.scheme in ('https', 'http') and parts.netloc and not parts.username else None


def doi_url(value):
    if not value:
        return None
    value = unquote(value.strip())
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value, flags=re.I)
    return 'https://doi.org/' + value.lower() if re.fullmatch(r'10\.\d{4,9}/[^\s<>"\x00-\x1f]+', value) else None


def select_works(works, authors, rankings, as_of):
    """Return eligible unique works and review records; never infer a ranking."""
    staff = {aid: a for a in authors if a.get('verified') is True
             for aid in a.get('openalex_ids', [a['openalex_id']])}
    included, review = {}, []
    start = date(as_of.year - 2, 1, 1)
    for work in works:
        wid = work.get('id', '')
        names = set()
        staff_author_names = set()
        for authorship in work.get('authorships', []):
            aid = ((authorship.get('author') or {}).get('id') or '').rsplit('/', 1)[-1]
            person = staff.get(aid)
            if not person:
                continue
            institution = person.get('required_institution_id')
            if institution and not any((i.get('id') or '').rsplit('/', 1)[-1] == institution
                                       for i in authorship.get('institutions', [])):
                continue
            names.add(person['name'])
            staff_author_names.add((authorship.get('author') or {}).get('display_name') or authorship.get('raw_author_name') or person['name'])
        names = sorted(names)
        reason = None
        published, date_value = publication_date(work)
        source = (work.get('primary_location') or {}).get('source') or {}
        if not names:
            reason = 'unverified_author'
        elif not published or not start <= published <= as_of:
            reason = 'outside_date_window'
        elif work.get('is_retracted'):
            reason = 'retracted'
        elif work.get('type') not in ('article', 'review') or source.get('type') != 'journal':
            reason = 'not_journal_article_or_review'
        issns = {s.upper().replace('-', '') for s in source.get('issn') or []}
        candidates = [r for r in rankings if r.get('verified') is True and published
                      and safe_url(r.get('evidence_url'))
                      and issns.intersection(s.upper().replace('-', '') for s in r['issns'])]
        matched = []
        # User-approved fallback: latest verified year within the three-year window.
        # Resolve each ranking system before checking eligibility, so a newer Q3/Q4
        # cannot be overridden by an older Q1/Q2 in the same system.
        for system in sorted({r['system'] for r in candidates}):
            choices = [(year, r) for r in candidates if r['system'] == system
                       for year in r.get('years', [])
                       if start.year <= year <= published.year]
            if not choices:
                continue
            latest = max(year for year, _ in choices)
            current = [r for year, r in choices if year == latest]
            if len({r['rank'] for r in current}) != 1:
                continue  # Conflicting evidence needs review.
            ranking = current[0]
            if ranking['rank'] in ALLOWED:
                matched.append(dict(ranking, evidence_year=latest))
        if not reason and not matched:
            reason = 'unverified_or_ineligible_ranking'
        doi = doi_url(work.get('doi'))
        # Only article landing pages, never a generic journal homepage or PDF.
        locations = [work.get('primary_location') or {}, work.get('best_oa_location') or {}] + (work.get('locations') or [])
        landing = next((safe_url(loc.get('landing_page_url')) for loc in locations
                        if safe_url(loc.get('landing_page_url')) and not loc['landing_page_url'].lower().endswith('.pdf')), None)
        target = doi or landing
        if not reason and not target:
            reason = 'missing_article_link'
        if reason:
            review.append({'id': wid, 'title': work.get('title'), 'reason': reason, 'staff': names,
                           'journal': source.get('display_name'), 'issns': source.get('issn') or []})
            continue
        key = doi or 'title:' + re.sub(r'\W+', '', (work.get('title') or '').lower()) + ':' + str(published.year)
        if key in included:
            included[key]['staff'] = sorted(set(included[key]['staff'] + names))
            included[key]['staff_author_names'] = sorted(set(included[key]['staff_author_names']) | staff_author_names)
            continue
        included[key] = {'id': wid, 'title': work.get('title') or 'Tanpa judul',
                         'publication_date': date_value, 'journal': source.get('display_name'),
                         'all_authors': [(a.get('author') or {}).get('display_name') or a.get('raw_author_name') or 'Penulis tidak diketahui' for a in work.get('authorships', [])],
                         'staff': names, 'staff_author_names': sorted(staff_author_names),
                         'biblio': work.get('biblio') or {}, 'url': target, 'doi': doi,
                         'rankings': [{'label': r['rank'], 'system': r['system'], 'year': published.year,
                                       'evidence_year': r['evidence_year'],
                                       'assumed': r['evidence_year'] != published.year,
                                       'evidence_url': r['evidence_url']} for r in matched]}
    return sorted(included.values(), key=lambda w: (w['publication_date'], w['title']), reverse=True), review


def fetch_works(author, as_of):
    works, cursor, seen = [], '*', set()
    for _ in range(100):
        params = {'filter': f"author.id:{author['openalex_id']},from_publication_date:{as_of.year-2}-01-01,to_publication_date:{as_of}",
                  'per_page': 100, 'sort': 'publication_date:desc', 'cursor': cursor}
        if os.environ.get('OPENALEX_API_KEY'):
            params['api_key'] = os.environ['OPENALEX_API_KEY']
        url = 'https://api.openalex.org/works?' + urlencode(params)
        # Do not print URL/errors: optional API credentials must stay out of logs.
        response = subprocess.run(['curl.exe' if os.name == 'nt' else 'curl', '-f', '-sS', '-L',
                                   '--retry', '2', '--max-time', '45', url], capture_output=True)
        if response.returncode:
            raise RuntimeError(f"OpenAlex request failed for {author['name']}; previous feed preserved.")
        data = json.loads(response.stdout)
        if 'results' not in data:
            raise RuntimeError('Invalid OpenAlex response; previous feed preserved.')
        works.extend(data['results'])
        cursor = (data.get('meta') or {}).get('next_cursor')
        if not data['results'] or not cursor:
            return works
        if cursor in seen:
            raise RuntimeError('Repeated pagination cursor; previous feed preserved.')
        seen.add(cursor)
    raise RuntimeError('Pagination safety limit reached; previous feed preserved.')


def atomic_write(path, text):
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
        f.write(text)
        tmp = Path(f.name)
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def render(feed):
    rows = []
    for work in feed['publications']:
        badges = ''.join(f'<span class="gf-pub-badge" title="{escape(r["system"])} {r["evidence_year"]}' + (f'; diasumsikan berlaku untuk {r["year"]}' if r['assumed'] else '') + f'">{escape(r["label"])}</span>' for r in work['rankings'])
        authors_line = author_label(work['all_authors'])
        staff_line = ' &#8226; <span class="gf-pub-staff">' + escape(staff_label(work['staff'])) + '</span>' if len(work['all_authors']) > 3 else ''
        rows.append(f'''<li class="gf-pub-item" data-year="{work['publication_date'][:4]}" data-ranks="{escape('|'.join(r['label'] for r in work['rankings']))}" data-staff="{escape('|'.join(work['staff']), quote=True)}">
  <a class="gf-pub-post" href="{escape(work['url'], quote=True)}" target="_blank" rel="noopener noreferrer">
    <span class="gf-pub-meta"><time datetime="{work['publication_date']}">{date_label(work['publication_date'])}</time> &#8226; <span class="gf-pub-journal">{escape(work['journal'])}</span> {badges}</span>
    <span class="gf-pub-title">{escape(work['title'])}</span>
    <span class="gf-pub-authors">{escape(authors_line)}{staff_line}</span>
    <span class="gf-pub-arrow" aria-hidden="true">›</span>
  </a>
</li>''')
    body = f'''<section class="gf-publication-feed" aria-label="Publikasi jurnal staf pendidik">
  <div class="gf-pub-heading"><div class="gf-pub-heading-text"><h2>Publikasi Jurnal</h2><p>Publikasi terbaru staf pendidik Program Studi Geofisika.</p><p class="gf-pub-note">Data publikasi dari OpenAlex, diperbarui {date_label(feed['as_of'])}.</p></div></div>
  <ul class="gf-pub-list">{''.join(rows)}</ul>
  <p class="gf-pub-empty" role="status" {'hidden' if rows else ''}>Belum ada publikasi dengan peringkat terverifikasi pada pilihan ini.</p>
</section>'''
    page_root = ROOT.parents[1] / 'pages-v2/publikasi-jurnal'
    page_root.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / 'display-config.json').read_text(encoding='utf-8'))
    page_url = safe_url(config['all_publications_url'])
    if not page_url:
        raise ValueError('Configure a valid publication page URL.')
    options = ''.join(f'<option value="{escape(a["name"], quote=True)}">{escape(a["name"])}</option>' for a in feed['authors'])
    years = ''.join(f'<option>{year}</option>' for year in range(int(feed['as_of'][:4]), feed['start_year']-1, -1))
    controls = f'''<div class="gf-pub-controls" hidden>
      <label>Peringkat jurnal<select data-pub-rank><option value="">Semua peringkat</option><option>Q1</option><option>Q2</option><option>Sinta 1</option><option>Sinta 2</option></select></label>
      <label>Staf pendidik<select data-pub-author><option value="">Semua staf</option>{options}</select></label>
      <label>Tahun<select data-pub-year><option value="">Semua tahun</option>{years}</select></label>
      <button type="button" data-pub-reset>Reset Filter</button>
    </div><p class="gf-pub-count" role="status" aria-live="polite">{len(rows)} publikasi</p>'''
    page_rows = []
    rank_class = lambda label: label.lower().replace(' ', '-')
    for work in feed['publications']:
        badges = ''.join(f'<span class="gf-pub-badge gf-pub-rank-{rank_class(r["label"])}">{escape(r["label"])}</span>' for r in work['rankings'])
        biblio = work.get('biblio') or {}
        citation = []
        if biblio.get('volume'):
            citation.append('Vol. ' + str(biblio['volume']))
        if biblio.get('issue'):
            citation.append('No. ' + str(biblio['issue']))
        first, last = biblio.get('first_page'), biblio.get('last_page')
        if first:
            citation.append(('hlm. ' + str(first) + '–' + str(last)) if last and last != first else str(first))
        if biblio.get('article_number'):
            citation.append('Artikel ' + str(biblio['article_number']))
        citation_html = ', ' + escape(', '.join(citation)) if citation else ''
        staff_names = set(work.get('staff_author_names', work['staff']))
        author_html = ', '.join('<strong>' + escape(name) + '</strong>' if name in staff_names else escape(name) for name in work['all_authors'])
        link_label = ('DOI: ' + work['doi'].removeprefix('https://doi.org/')) if work.get('doi') else work['url']
        page_rows.append(f'''<li class="gf-pub-item" data-year="{work['publication_date'][:4]}" data-ranks="{escape('|'.join(r['label'] for r in work['rankings']))}" data-staff="{escape('|'.join(work['staff']), quote=True)}">
          <article class="gf-pub-paper">
            <p class="gf-pub-meta"><time datetime="{work['publication_date']}">{date_label(work['publication_date'])}</time> &#8226; <span class="gf-pub-journal">{escape(work['journal'])}{citation_html}</span> {badges}</p>
            <h2 class="gf-pub-title">{escape(work['title'])}</h2>
            <p class="gf-pub-authors">{author_html}</p>
            <a class="gf-pub-access" href="{escape(work['url'], quote=True)}" target="_blank" rel="noopener noreferrer">{escape(link_label)} <span aria-hidden="true">&#8599;</span></a>
          </article>
        </li>''')
    legend = ' '.join(f'<span class="gf-pub-badge gf-pub-rank-{rank_class(label)}">{label}</span>' for label in ['Q1', 'Q2', 'Sinta 1', 'Sinta 2'])
    full = f'''<section class="gf-publication-feed gf-pub-page" aria-label="Publikasi jurnal staf pendidik">
      <div class="gf-pub-page-notice"><p>Berikut adalah daftar publikasi dari staf pendidik Program Studi Geofisika dalam tiga tahun terakhir dari jurnal-jurnal dengan peringkat berikut:</p><p class="gf-pub-legend" aria-label="Legenda peringkat jurnal">{legend}</p><p>Data publikasi dari OpenAlex dan diperbarui mingguan. Terakhir diperbarui {date_label(feed['as_of'])}. Peringkat jurnal berdasarkan peringkat terbaru dalam rentang {feed['start_year']}-{feed['as_of'][:4]}.</p></div>
      {controls}
      <ul class="gf-pub-list">{''.join(page_rows)}</ul>
      <p class="gf-pub-empty" role="status" {'hidden' if rows else ''}>Belum ada publikasi dengan peringkat terverifikasi pada pilihan ini.</p>
    </section>'''
    home = body.replace(''.join(rows), ''.join(rows[:3]), 1) if rows else body
    navigation = f'<nav class="gf-pub-navigation" aria-label="Arsip publikasi"><a href="{escape(page_url, quote=True)}">Lihat Semua</a></nav>'
    home = home.replace('<p>Publikasi terbaru staf', '<div class="gf-pub-description-row"><p>Publikasi terbaru staf', 1)
    home = home.replace('Program Studi Geofisika.</p>', 'Program Studi Geofisika.</p>' + navigation + '</div>', 1)
    full, home = format_html(full), format_html(home)
    js = (ROOT / 'publication-feed.js').read_text(encoding='utf-8')
    atomic_write(ROOT / 'publication-feed-wordpress.html', home + '\n')
    atomic_write(page_root / '01-publications-wordpress.html', full + '\n<script>\n' + js + '\n</script>\n')
    # The dedicated page stylesheet is maintained locally, independently of widget CSS.
    def preview(content, css, title, script=''):
        return '<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title><link rel="stylesheet" href="' + css + '"><style>body{margin:0;padding:24px;background:#f5f7f9}main{max-width:1140px;margin:auto;background:white;padding:24px}@media(max-width:540px){body,main{padding:16px}}</style></head><body><main>' + content + '</main>' + script + '</body></html>'
    atomic_write(ROOT / 'preview.html', preview(home.replace(page_url, '../../pages-v2/publikasi-jurnal/preview.html'), 'publication-feed.css', 'Publikasi Jurnal — Homepage'))
    atomic_write(page_root / 'preview.html', preview('<h1 style="margin:0 0 24px;color:#073c64;font:700 30px/1.3 Open Sans,Arial,sans-serif">Publikasi Jurnal</h1>' + full, 'publikasi-jurnal.css', 'Publikasi Jurnal', '<script>' + js + '</script>'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Use saved OpenAlex snapshots; never claims a fresh fetch.')
    parser.add_argument('--as-of', type=date.fromisoformat)
    args = parser.parse_args()
    today = args.as_of or datetime.now(timezone(timedelta(hours=7))).date()
    authors = json.loads((ROOT / 'authors.json').read_text(encoding='utf-8'))
    rankings = json.loads((ROOT / 'journal-rankings.json').read_text(encoding='utf-8'))
    all_works, snapshots = [], []
    for author in authors:
        if author.get('verified') is not True:
            raise RuntimeError('Verify every author ID before updating.')
        path = ROOT / 'research' / (author['name'].replace(' ', '-') + '-works.json')
        if args.offline:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not data['meta'].get('captured_as_of') or str(today) > data['meta']['captured_as_of']:
                raise RuntimeError('Offline date exceeds the saved capture date; refresh online or choose the capture date.')
            if len(data['results']) != data['meta']['count']:
                raise RuntimeError('Offline snapshot is incomplete.')
            works = data['results']
        else:
            unique = {}
            for aid in author.get('openalex_ids', [author['openalex_id']]):
                for work in fetch_works(dict(author, openalex_id=aid), today):
                    unique[work['id']] = work
            works = list(unique.values())
            snapshots.append((path, {'meta': {'count': len(works), 'captured_as_of': str(today)}, 'results': works}))
        all_works.extend(works)
    all_works = list({w['id']: w for w in all_works}.values())
    ranking_report = None
    if not args.offline:
        rankings, ranking_report = refresh_rankings(ROOT, all_works, rankings, today)
    publications, review = select_works(all_works, authors, rankings, today)
    feed = {'schema_version': 1, 'as_of': str(today), 'start_year': today.year-2,
            'mode': 'saved_snapshot' if args.offline else 'live_fetch',
            'authors': authors, 'publications': publications}
    # Publish only after every author's request and selection succeeds.
    if ranking_report is not None:
        atomic_write(ROOT / 'journal-rankings.json', json.dumps(rankings, ensure_ascii=False, indent=2))
        atomic_write(ROOT / 'ranking-review.json', json.dumps(ranking_report, ensure_ascii=False, indent=2))
        unavailable = sum(s['status'] != 'verified' for s in ranking_report['sources'])
        if unavailable:
            print(f'::warning::{unavailable} ranking sources could not be verified; previous evidence retained. See ranking-review.json.')
    for path, data in snapshots:
        atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
    atomic_write(ROOT / 'review.json', json.dumps(review, ensure_ascii=False, indent=2))
    coverage = [{'name': a['name'], 'status': a.get('status', ''),
                 'openalex_ids': a.get('openalex_ids', [a['openalex_id']]),
                 'displayed_publications': sum(a['name'] in w['staff'] for w in publications)} for a in authors]
    atomic_write(ROOT / 'coverage.json', json.dumps(coverage, ensure_ascii=False, indent=2))
    render(feed)
    atomic_write(ROOT / 'publications.json', json.dumps(feed, ensure_ascii=False, indent=2))
    print(f"Generated {len(publications)} unique publications; {len(review)} records excluded. Mode: {feed['mode']}.")


if __name__ == '__main__':
    main()
