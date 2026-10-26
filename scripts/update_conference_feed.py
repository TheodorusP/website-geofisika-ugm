"""Conference archive: event metadata stays separate from publication metadata."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
from html import escape, unescape
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote
from update_publication_feed import (ROOT, author_ids, author_display, atomic_write,
                                     date_label, doi_url, fetch_works, publication_date, safe_url)
from format_page_html import format_html

BASE = Path(__file__).resolve().parents[1]
PAGE = BASE / 'pages-v2/konferensi'
SERIES = re.compile(r'IOP Conference Series|Journal of Physics.*Conference Series|AIP Conference Proceedings|Web of Conferences', re.I)
COUNTRIES = {name.casefold(): name for name in ['Indonesia', 'Austria', 'Australia', 'Japan', 'Germany',
    'France', 'Italy', 'Spain', 'Portugal', 'Netherlands', 'Belgium', 'Switzerland', 'Sweden', 'Norway',
    'Finland', 'Denmark', 'United Kingdom', 'United States', 'Canada', 'China', 'India', 'Malaysia',
    'Singapore', 'Thailand', 'Vietnam', 'Philippines', 'South Korea', 'Taiwan', 'New Zealand',
    'South Africa', 'Brazil', 'Mexico', 'Turkey', 'Greece', 'Czech Republic', 'Poland', 'Russia']}


def clean(value):
    return ' '.join(unescape(re.sub(r'<[^>]*>', '', str(value or ''))).split())


def request(url, allow_missing=False):
    response = subprocess.run(['curl.exe' if os.name == 'nt' else 'curl', '-sS', '-L', '--retry', '4',
                               '--retry-delay', '3', '--retry-max-time', '180',
                               '--connect-timeout', '15', '--max-time', '45',
                               '--user-agent', 'UGM-Geophysics-Conference-Feed/1.0',
                               '-H', 'Accept: application/json',
                               '-w', '\n%{http_code}', url], capture_output=True)
    if response.returncode:
        raise RuntimeError(f'Conference metadata request failed (curl {response.returncode}) for {url}; previous output preserved')
    body, status = response.stdout.rsplit(b'\n', 1)
    if status == b'404' and allow_missing:
        return None
    if status != b'200':
        raise RuntimeError(f'Conference metadata HTTP {status.decode("ascii", errors="replace")} for {url}; previous output preserved')
    return json.loads(body)


def date_parts(value):
    parts = (value or {}).get('date-parts') or []
    if not parts or not parts[0]:
        return None
    text = '-'.join(str(p) if i == 0 else f'{p:02d}' for i, p in enumerate(parts[0]))
    return publication_date({'publication_date': text})[1]


def date_range_label(start, end=None):
    if not start:
        return date_label(end) if end else ''
    if not end or start == end:
        return date_label(start)
    left, right = start.split('-'), end.split('-')
    if len(left) == len(right) == 3 and left[0] == right[0]:
        if left[1] == right[1]:
            return str(int(left[2])) + '–' + date_label(end)
        return date_label(start).rsplit(' ', 1)[0] + '–' + date_label(end)
    return date_label(start) + '–' + date_label(end)


def is_candidate(work):
    source = ((work.get('primary_location') or {}).get('source') or {})
    return (work.get('type') in ('conference-paper', 'conference-abstract', 'proceedings-article') or
            source.get('type') == 'conference' or bool(SERIES.search(source.get('display_name') or '')))


def staff_byline(work, people):
    staff, bold, names = set(), set(), []
    for by in work.get('authorships', []):
        person = people.get(((by.get('author') or {}).get('id') or '').rsplit('/', 1)[-1])
        display = author_display(by, person)
        names.append(display)
        required = person.get('required_institution_id') if person else None
        if required and not any((inst.get('id') or '').rsplit('/', 1)[-1] == required for inst in by.get('institutions', [])):
            person = None
        if person:
            staff.add(person['name'])
            bold.add(display)
    return sorted(staff), sorted(bold), names


def merge_contributions(records):
    """Only explicit shared contribution IDs or identical DOIs establish a merge."""
    result = {}
    for record in records:
        key = record.get('contribution_id') or record.get('doi') or record['id']
        if key not in result:
            result[key] = dict(record)
            continue
        old = result[key]
        if record.get('publication_kind') == 'Prosiding' and old.get('publication_kind') != 'Prosiding':
            chosen, other = dict(record), old
        else:
            chosen, other = old, record
        for field in ['staff', 'staff_author_names']:
            chosen[field] = sorted(set(chosen[field]) | set(other[field]))
        for field in ['conference_name', 'conference_start', 'conference_end', 'city', 'country',
                      'presentation_type', 'online']:
            if chosen.get(field) in (None, '') and other.get(field) not in (None, ''):
                chosen[field] = other[field]
        result[key] = chosen
    return list(result.values())


def select_conferences(works, authors, metadata, overrides, today):
    people = {aid: person for person in authors if person.get('verified') for aid in author_ids(person)}
    patches = {entry['doi']: entry for entry in overrides if entry.get('doi') and entry.get('verified') is True}
    records, review = [], []
    for work in works:
        staff, bold, names = staff_byline(work, people)
        doi = doi_url(work.get('doi'))
        crossref = metadata.get(doi) or {}
        event = crossref.get('event') or {}
        override = patches.get(doi, {})
        pub_date = next((value for field in ['published', 'published-online', 'published-print']
                         if (value := date_parts(crossref.get(field)))), None)
        if pub_date is None:
            pub_date = publication_date(work)[1]
        source = ((work.get('primary_location') or {}).get('source') or {})
        conference_name = clean(event.get('name'))
        start, end = date_parts(event.get('start')), date_parts(event.get('end'))
        reason = None
        if not staff:
            reason = 'unverified_staff_identity'
        elif work.get('is_retracted') or not is_candidate(work):
            reason = 'not_eligible_conference_record'
        if work.get('type') == 'conference-abstract' or crossref.get('subtype') == 'abstract':
            kind = 'Abstrak'
        elif crossref.get('type') == 'proceedings-article' or (work.get('type') == 'conference-paper' and crossref):
            kind = 'Prosiding'
        else:
            kind = None
        if not kind and not override:
            reason = reason or 'conference_type_unverified'
        locations = [work.get('primary_location') or {}] + (work.get('locations') or [])
        landing = next((safe_url(loc.get('landing_page_url')) for loc in locations if safe_url(loc.get('landing_page_url'))), None)
        collection = ' — '.join(clean(v) for v in crossref.get('container-title', [])) or clean(source.get('display_name'))
        record = {'id': work.get('id') or doi, 'doi': doi, 'title': clean(work.get('title')),
                  'conference_name': conference_name, 'conference_start': start, 'conference_end': end,
                  'city': None, 'country': None, 'publication_kind': kind,
                  'publication_date': pub_date if crossref or work.get('type') == 'conference-abstract' else None,
                  'collection': collection, 'presentation_type': None, 'online': None,
                  'authors': names, 'staff': staff, 'staff_author_names': bold, 'url': doi or landing,
                  'event_location_raw': clean(event.get('location')), 'evidence_url': doi}
        if override:
            if not safe_url(override.get('evidence_url')):
                raise ValueError('Conference overrides need organizer/publisher evidence')
            for field in ['contribution_id', 'conference_name', 'conference_start', 'conference_end',
                          'city', 'country', 'publication_kind', 'presentation_type', 'online', 'url']:
                if field in override:
                    record[field] = override[field]
            record['evidence_url'] = override['evidence_url']
        # Do not guess a city/country from an address, institution, or conference acronym.
        # Preserve a single country-only event location; reviewed city/country fields use overrides.
        raw_location = record['event_location_raw']
        if not record['city'] and not record['country'] and raw_location and ',' in raw_location:
            parts = [part.strip() for part in raw_location.split(',')]
            if len(parts) == 2 and parts[1].casefold() in COUNTRIES and not re.search(r'\d|online|virtual|hybrid', raw_location, re.I):
                record['city'], record['country'] = parts[0], COUNTRIES[parts[1].casefold()]
        if not record['country'] and raw_location.casefold() in COUNTRIES:
            record['country'] = COUNTRIES[raw_location.casefold()]
        if not record['country'] and raw_location and re.fullmatch(r'[A-Za-z ]+', raw_location) and not re.search(r'online|virtual|hybrid', raw_location, re.I):
            record['location_unresolved'] = raw_location  # Report, never label an unverified city as a country.
        effective = record['conference_start'] or record['publication_date']
        published, _ = publication_date({'publication_date': effective})
        if not published or not date(today.year-4, 1, 1) <= published <= today:
            reason = reason or 'outside_five_year_window_or_missing_date'
        if record['publication_kind'] not in (None, 'Prosiding', 'Abstrak') or record['presentation_type'] not in (None, 'Oral', 'Poster') or record['online'] not in (None, True, False):
            raise ValueError('Invalid reviewed presentation type or online flag')
        if record['url'] and not safe_url(record['url']):
            raise ValueError('Unsafe conference link')
        if reason:
            review.append({'id': work.get('id'), 'title': work.get('title'), 'reason': reason})
            continue
        if not record['conference_name']:
            review.append({'id': record['id'], 'title': record['title'], 'reason': 'event_metadata_incomplete', 'included': True})
        records.append(record)
    # Standalone organizer-verified presentations may have no DOI and no published paper.
    for entry in overrides:
        if entry.get('doi'):
            continue
        if entry.get('verified') is not True or not safe_url(entry.get('evidence_url')):
            raise ValueError('Standalone presentations need verified organizer evidence')
        if not entry.get('staff') or not set(entry['staff']).issubset({p['name'] for p in authors}):
            raise ValueError('Standalone presentation staff must match roster')
        record = dict(entry)
        for field in ['doi', 'conference_end', 'city', 'country', 'publication_kind', 'publication_date',
                      'presentation_type', 'online', 'url', 'collection']:
            record.setdefault(field, None)
        record.setdefault('staff_author_names', record['staff'])
        if not record.get('id') or not record.get('title') or not record.get('authors') or not record.get('conference_name'):
            raise ValueError('Incomplete standalone presentation')
        if record['publication_kind'] not in (None, 'Prosiding', 'Abstrak'):
            raise ValueError('Invalid publication kind')
        if record['presentation_type'] not in (None, 'Oral', 'Poster'):
            raise ValueError('Invalid presentation format')
        if record['url'] and not safe_url(record['url']):
            raise ValueError('Unsafe standalone presentation link')
        event_date, _ = publication_date({'publication_date': record.get('conference_start')})
        if event_date and date(today.year-4, 1, 1) <= event_date <= today:
            records.append(record)
    records = merge_contributions(records)
    return sorted(records, key=lambda item: (item.get('conference_start') or item.get('publication_date') or '', item['title']), reverse=True), review


def render(feed):
    records = feed['conferences']
    staff_options = ''.join(f'<option>{escape(p["name"])}</option>' for p in feed['authors'])
    year_options = ''.join(f'<option>{year}</option>' for year in range(int(feed['as_of'][:4]), feed['start_year']-1, -1))
    conference_options = ''.join(f'<option>{escape(name)}</option>' for name in sorted({r['conference_name'] for r in records if r['conference_name']}))
    rows = []
    for record in records:
        start, end = record.get('conference_start'), record.get('conference_end')
        event_date = date_range_label(start, end)
        meta = [value for value in [event_date, record.get('conference_name')] if value]
        missing_event = not event_date and not record.get('conference_name')
        location = ', '.join(v for v in [record.get('city'), record.get('country')] if v)
        if location:
            meta.append(location)
        pills = []
        for label in [record.get('publication_kind'), record.get('presentation_type'), 'Online' if record.get('online') is True else None]:
            if label:
                pills.append(f'<span class="gf-conf-pill gf-conf-{label.lower()}">{label}</span>')
        publication = ''
        if record.get('publication_kind') and record.get('publication_date'):
            label = 'Prosiding diterbitkan pada' if record['publication_kind'] == 'Prosiding' else 'Abstrak diterbitkan pada'
            publication = f'<p class="gf-conf-publication">{label} {date_label(record["publication_date"])}' + (' &#8226; ' + escape(record['collection']) if record.get('collection') else '') + (' ' + ' '.join(pills) if missing_event else '') + '</p>'
        meta_line = ''
        if not missing_event:
            meta_line = '<p class="gf-conf-meta">' + escape(' • '.join(meta)) + ' ' + ' '.join(pills) + '</p>'
        elif location or not publication:
            meta_line = '<p class="gf-conf-meta">' + escape(location) + (' ' + ' '.join(pills) if not publication else '') + '</p>'
        byline = ', '.join('<strong>' + escape(name) + '</strong>' if name in record['staff_author_names'] else escape(name) for name in record['authors'])
        link = ''
        if record.get('url'):
            label = 'DOI: ' + record['doi'].removeprefix('https://doi.org/') if record.get('doi') and record['url'] == record['doi'] else 'Lihat Kontribusi'
            link = f'<a class="gf-conf-access" href="{escape(record["url"], quote=True)}" target="_blank" rel="noopener noreferrer">{escape(label)} <span aria-hidden="true">&#8599;</span></a>'
        effective = record.get('conference_start') or record.get('publication_date') or ''
        rows.append(f'''<li class="gf-conf-item" data-year="{effective[:4]}" data-kind="{escape(record.get('publication_kind') or '')}" data-format="{record.get('presentation_type') or ''}" data-online="{str(record.get('online') is True).lower()}" data-staff="{escape('|'.join(record['staff']), quote=True)}" data-conference="{escape(record.get('conference_name') or '', quote=True)}"><article>
          {meta_line}
          {publication}<h2>{escape(record['title'])}</h2><p class="gf-conf-authors">{byline}</p>{link}
        </article></li>''')
    markup = f'''<section class="gf-conf-page" aria-label="Konferensi dan presentasi ilmiah">
      <div class="gf-conf-notice"><p>Kontribusi staf pendidik dan tenaga kependidikan Program Studi Geofisika pada konferensi terindeks dalam lima tahun terakhir ({feed['start_year']}-{feed['as_of'][:4]}).</p><p>Data dari OpenAlex, Crossref, dan sumber penyelenggara yang telah diverifikasi. Terakhir diperbarui {date_label(feed['as_of'])}. Tanggal konferensi dibedakan dari tanggal publikasi. Jenis presentasi dan pelaksanaan daring ditampilkan bila terkonfirmasi; peran sebagai penulis tidak selalu berarti sebagai penyaji.</p></div>
      <div class="gf-conf-controls" hidden><label>Publikasi<select data-conf-kind><option value="">Semua publikasi</option><option>Prosiding</option><option>Abstrak</option></select></label><label>Presentasi<select data-conf-format><option value="">Semua presentasi</option><option>Oral</option><option>Poster</option></select></label><label>Staf<select data-conf-staff><option value="">Semua staf</option>{staff_options}</select></label><label>Tahun<select data-conf-year><option value="">Semua tahun</option>{year_options}</select></label><label>Konferensi<select data-conf-event><option value="">Semua konferensi</option>{conference_options}</select></label><label>Pelaksanaan<select data-conf-online><option value="">Semua pelaksanaan</option><option value="true">Online</option></select></label><button type="button" data-conf-reset>Reset Filter</button></div>
      <p class="gf-conf-count" role="status" aria-live="polite">{len(records)} kontribusi</p><ul class="gf-conf-list">{''.join(rows)}</ul><p class="gf-conf-empty" role="status" {'hidden' if records else ''}>Belum ada kontribusi terverifikasi pada pilihan ini.</p>
    </section>'''
    markup = format_html(markup)
    js = (PAGE / 'conferences.js').read_text(encoding='utf-8')
    atomic_write(PAGE / '01-conferences-wordpress.html', markup + '\n<script>\n' + js + '\n</script>\n')
    atomic_write(PAGE / 'preview.html', '<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Konferensi dan Presentasi Ilmiah</title><link rel="stylesheet" href="konferensi.css"><style>body{margin:0;padding:24px;background:#f5f7f9}main{max-width:1140px;margin:auto}h1{font:700 30px/1.4 Arial;color:#073c64}</style></head><body><main><h1>Konferensi dan Presentasi Ilmiah</h1>' + markup + '</main><script>' + js + '</script></body></html>')
    public = BASE / 'public'
    public.mkdir(exist_ok=True)
    atomic_write(public / 'conferences-display.json', json.dumps({'schema_version': 1, 'as_of': feed['as_of'], 'page': markup}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--from-journal-snapshots', action='store_true')
    parser.add_argument('--as-of', type=date.fromisoformat)
    args = parser.parse_args()
    today = args.as_of or datetime.now(timezone(timedelta(hours=7))).date()
    authors = json.loads((ROOT / 'authors.json').read_text(encoding='utf-8')) + json.loads((ROOT / 'support-staff.json').read_text(encoding='utf-8'))
    snapshot = PAGE / 'conference-snapshot.json'
    if args.offline:
        saved = json.loads(snapshot.read_text(encoding='utf-8'))
        if saved['as_of'] != str(today):
            raise ValueError('Offline date must equal saved snapshot date')
        works, metadata = saved['works'], saved['crossref']
    else:
        unique = {}
        for person in authors:
            if not person.get('verified'):
                continue
            if args.from_journal_snapshots:
                saved = json.loads((ROOT / 'research' / (person['name'].replace(' ', '-') + '-works.json')).read_text(encoding='utf-8'))
                if saved['meta']['captured_as_of'] != str(today) or saved['meta'].get('start_year', 9999) > today.year-4:
                    raise ValueError('Journal snapshot does not cover the required date/window')
                records = saved['results']
            else:
                records = []
                for aid in author_ids(person):
                    records.extend(fetch_works(dict(person, openalex_id=aid), today))
            for work in records:
                if is_candidate(work):
                    unique[work['id']] = work
        works = list(unique.values())
        def fetch_metadata(doi):
            response = request('https://api.crossref.org/works/' + quote(doi.removeprefix('https://doi.org/'), safe='/'), allow_missing=True)
            return doi, (response or {}).get('message') or {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            metadata = dict(pool.map(fetch_metadata, sorted({doi_url(w.get('doi')) for w in works} - {None})))
    overrides = json.loads((PAGE / 'verified-contributions.json').read_text(encoding='utf-8'))
    records, review = select_conferences(works, authors, metadata, overrides, today)
    feed = {'schema_version': 1, 'as_of': str(today), 'start_year': today.year-4, 'authors': authors, 'conferences': records}
    render(feed)
    atomic_write(PAGE / 'conferences.json', json.dumps(feed, ensure_ascii=False, indent=2))
    atomic_write(PAGE / 'review.json', json.dumps(review, ensure_ascii=False, indent=2))
    if not args.offline:
        atomic_write(snapshot, json.dumps({'as_of': str(today), 'works': works, 'crossref': metadata}, ensure_ascii=False, indent=2))
    print(f'Conference archive: {len(records)} contributions; {len(review)} review notes.')


if __name__ == '__main__':
    main()
