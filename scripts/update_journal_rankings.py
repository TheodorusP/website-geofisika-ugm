"""Conservative ranking refresh: official SCImago exports and explicit publisher notices.

No ranking inference from journal names, search snippets, or a current Sinta badge.
Source failures retain previous evidence; conflicts remain visible to the selector.
"""
import csv
import hashlib
from html.parser import HTMLParser
import io
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

AGENT = 'GeofisikaPublicationMonitor/1.0'
SCIMAGO = 'SCImago SJR best quartile'


def issn(value):
    value = re.sub(r'[-\s]', '', str(value)).upper()
    return value if re.fullmatch(r'\d{7}[\dX]', value) else None


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain(html):
    parser = Text()
    parser.feed(html)
    return ' '.join(' '.join(parser.parts).split())


def read_url(url, robots):
    """Respect robots rules and ordinary HTTP errors; never bypass challenges."""
    parsed = urlsplit(url)
    origin = parsed.scheme + '://' + parsed.netloc
    if parsed.scheme != 'https':
        raise ValueError('HTTPS evidence required')
    if origin not in robots:
        robot_url = origin + '/robots.txt'
        policy = RobotFileParser(robot_url)
        try:
            with urlopen(Request(robot_url, headers={'User-Agent': AGENT}), timeout=15) as response:
                policy.parse(response.read(200000).decode('utf-8', errors='replace').splitlines())
        except HTTPError as error:
            if error.code != 404:
                raise ValueError('robots.txt unavailable; source not requested') from None
            policy.parse([])
        robots[origin] = policy
    if not robots[origin].can_fetch(AGENT, url):
        raise ValueError('robots.txt disallows this request')
    with urlopen(Request(url, headers={'User-Agent': AGENT}), timeout=25) as response:
        final = urlsplit(response.url)
        if final.netloc != parsed.netloc:
            raise ValueError('Evidence redirected to another host')
        expected = parse_qs(parsed.query).get('year')
        if expected and parse_qs(final.query).get('year') != expected:
            raise ValueError('Evidence year changed during redirect')
        raw = response.read(25000001)
        if len(raw) > 25000000:
            raise ValueError('Evidence exceeds size limit')
        return raw


def parse_scimago(raw, year, url, today, candidates):
    """Use only the export's explicit best quartile and exact ISSN fields."""
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252')
    if '<html' in text[:3000].lower() or '<!doctype' in text[:3000].lower():
        raise ValueError('SCImago returned HTML instead of an export')
    rows = csv.DictReader(io.StringIO(text), delimiter=';')
    required = {'Title', 'Issn', 'SJR Best Quartile', 'Type'}
    if not required.issubset(rows.fieldnames or []):
        raise ValueError('Unrecognized SCImago export columns')
    groups = {}
    for row in rows:
        if row.get('Type', '').strip().lower() != 'journal':
            continue
        identifiers = {issn(v) for v in re.split(r'[,;]', row['Issn'])} - {None}
        matched = identifiers.intersection(candidates)
        if not matched:
            continue
        rank = row['SJR Best Quartile'].strip().upper()
        if rank not in ('Q1', 'Q2', 'Q3', 'Q4'):
            continue
        for identifier in matched:
            groups.setdefault(identifier, set()).add(rank)
    records = []
    for identifier, ranks in groups.items():
        if len(ranks) != 1:
            raise ValueError('Conflicting quartiles for the same ISSN')
        records.append({'journal': candidates[identifier], 'issns': [identifier],
                        'rank': next(iter(ranks)), 'system': SCIMAGO, 'years': [year],
                        'verified': True, 'checked_on': str(today), 'evidence_url': url,
                        'evidence_sha256': hashlib.sha256(raw).hexdigest(),
                        'automatic': True, 'note': 'Exact ISSN match in official annual best-quartile export.'})
    return records


def parse_notice(raw, source, today):
    text = plain(raw.decode('utf-8'))
    identifiers = {issn(v) for v in re.findall(r'\b\d{4}[- ]?\d{3}[\dXx]\b', text)} - {None}
    if not identifiers.intersection(issn(v) for v in source['issns']):
        raise ValueError('Publisher notice does not confirm journal ISSN')
    matches = list(re.finditer(source['pattern'], text, re.I))
    if len(matches) != 1:
        raise ValueError('Accreditation rank, decree or validity is ambiguous/missing')
    match = matches[0]
    rank, start, end = match['rank'], int(match['start']), int(match['end'])
    # Boundaries are issue-based. Only complete INTERIOR years are verified.
    years = [year for year in range(today.year - 2, today.year + 1) if start < year < end]
    if not years or end <= start:
        raise ValueError('No complete calendar year within explicit accreditation boundaries')
    return [{'journal': source['journal'], 'issns': source['issns'], 'rank': 'Sinta ' + rank,
             'system': 'Sinta accreditation', 'years': years, 'verified': True,
             'checked_on': str(today), 'evidence_url': source['url'],
             'evidence_sha256': hashlib.sha256(raw).hexdigest(), 'automatic': True,
             'note': 'Publisher accreditation notice; decree ' + match['decree'] +
                     '. Boundary years omitted because coverage is issue-based.'}]


def merge(existing, incoming):
    """Refresh matching automatic evidence, preserving manual evidence and conflicts."""
    result = list(existing)
    for record in incoming:
        result = [old for old in result if not (
            old.get('automatic') and old['system'] == record['system'] and
            old['evidence_url'] == record['evidence_url'] and
            old['years'] == record['years'] and
            set(map(issn, old['issns'])) == set(map(issn, record['issns'])))]
        result.append(record)
    return result


def refresh_rankings(root, works, existing, today, fetch=read_url):
    config = json.loads((root / 'ranking-sources.json').read_text(encoding='utf-8'))
    candidates = {}
    for work in works:
        source = (work.get('primary_location') or {}).get('source') or {}
        if source.get('type') != 'journal':
            continue
        for value in source.get('issn') or []:
            if issn(value):
                candidates[issn(value)] = source.get('display_name') or 'Unknown journal'
    report = {'checked_on': str(today), 'sources': [], 'review': []}
    incoming, robots = [], {}
    sources = []
    if config.get('scimago'):
        for year in range(today.year - 2, today.year):
            sources.append(('scimago', f'https://www.scimagojr.com/journalrank.php?year={year}&out=xls', year))
    sources.extend(('publisher', source['url'], source) for source in config.get('publisher_notices', []))
    for kind, url, argument in sources:
        try:
            raw = fetch(url, robots)
            records = (parse_scimago(raw, argument, url, today, candidates) if kind == 'scimago'
                       else parse_notice(raw, argument, today))
            incoming.extend(records)
            report['sources'].append({'url': url, 'status': 'verified', 'records': len(records)})
        except Exception as error:
            report['sources'].append({'url': url, 'status': 'unavailable_or_unverified',
                                      'reason': type(error).__name__ + ': ' + str(error)[:180]})
    result = merge(existing, incoming)
    for identifier, journal in sorted(candidates.items()):
        matches = [r for r in result if identifier in set(map(issn, r['issns'])) and r.get('verified')
                   and any(today.year - 2 <= year <= today.year for year in r['years'])]
        if not matches:
            report['review'].append({'journal': journal, 'issn': identifier, 'reason': 'No verified ranking in current window'})
        for system in {r['system'] for r in matches}:
            for year in range(today.year - 2, today.year + 1):
                ranks = {r['rank'] for r in matches if r['system'] == system and year in r['years']}
                if len(ranks) > 1:
                    report['review'].append({'journal': journal, 'issn': identifier, 'system': system,
                                             'year': year, 'reason': 'Conflicting ranks; selector excludes this evidence year'})
    return result, report
