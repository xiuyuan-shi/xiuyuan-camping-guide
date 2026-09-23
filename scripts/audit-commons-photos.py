#!/usr/bin/env python3
"""Look for reusable Commons photos for currently photo-less Hangzhou entries.

Search results are only leads. A human must confirm depicted place and license
before adding any image to the public gallery.
"""
import concurrent.futures
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT/'data.json').read_text())
LIVE = json.loads((ROOT/'live-data.json').read_text())
OUT = ROOT/'imports/2026-09-23/commons-photo-search.json'
stored = json.loads(OUT.read_text()) if OUT.exists() else {}
agent = 'XiuyuanCampingGuide/1.0 (+https://xiuyuan-shi.github.io/xiuyuan-camping-guide/)'

def has_photo(record):
    if record.get('reviewedPhotos') or record.get('publicPhotos'):
        return True
    if LIVE['records'].get(record['id'], {}).get('images'):
        return True
    for sid in record['sourceIds']:
        source = DATA['sources'].get(sid, {})
        rows = {n for e in record['evidence'] if e['sourceId'] == sid
                for n in e.get('excelRows', [])}
        if any(p.get('review', {}).get('status') == 'keep'
               and rows.intersection(p.get('excelRows', []))
               for p in source.get('imageReferences', [])):
            return True
    return False

records = [r for r in DATA['records'] if r['scope'] == 'hangzhou'
           and not has_photo(r) and r['id'] not in stored]

def search(record):
    url = 'https://commons.wikimedia.org/w/api.php?' + urlencode({
        'action': 'query', 'format': 'json', 'generator': 'search',
        'gsrsearch': record['name'], 'gsrnamespace': 6, 'gsrlimit': 5,
        'prop': 'imageinfo', 'iiprop': 'url|extmetadata'})
    proc = subprocess.run(['curl', '-fsSL', '--max-time', '20', '-A', agent, url],
                          capture_output=True, text=True)
    try:
        pages = json.loads(proc.stdout).get('query', {}).get('pages', {})
    except json.JSONDecodeError:
        pages = {}
    hits = []
    for page in pages.values():
        info = page.get('imageinfo', [{}])[0]
        meta = info.get('extmetadata', {})
        hits.append({'title': page['title'], 'url': info.get('url'),
                     'sourceUrl': info.get('descriptionurl'),
                     'license': meta.get('LicenseShortName', {}).get('value'),
                     'artist': meta.get('Artist', {}).get('value'),
                     'description': meta.get('ImageDescription', {}).get('value', '')[:500]})
    return record['id'], {'name': record['name'], 'hits': hits,
                          'error': proc.stderr[-200:] if proc.returncode else None}

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for i, (rid, result) in enumerate(pool.map(search, records), 1):
        stored[rid] = result
        if i % 10 == 0 or i == len(records):
            OUT.write_text(json.dumps(stored, ensure_ascii=False, indent=2) + '\n')
            print(f'{i}/{len(records)} searched', flush=True)
print('SEARCHED', len(records), 'CACHED', len(stored), flush=True)
