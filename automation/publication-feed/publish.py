"""Build the public display payload after successful collection."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
feed = json.loads((root / 'widgets/publication-feed/publications.json').read_text(encoding='utf-8'))
home = (root / 'widgets/publication-feed/publication-feed-wordpress.html').read_text(encoding='utf-8')
page = (root / 'pages-v2/publikasi-jurnal/01-publications-wordpress.html').read_text(encoding='utf-8').split('<script>')[0].strip()
payload = {'schema_version': 1, 'as_of': feed['as_of'], 'home': home, 'page': page}
destination = root / 'public/publications-display.json'
destination.parent.mkdir(exist_ok=True)
temporary = destination.with_suffix('.tmp')
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
temporary.replace(destination)
print(f"Published display payload dated {feed['as_of']}")
