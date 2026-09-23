#!/usr/bin/env python3
"""Check every approved photo URL used by the public site.

The workbook image-review file already records why other images were withheld;
this script checks transport availability, never changes place attribution.
"""
import collections
import concurrent.futures
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'data.json').read_text())
LIVE = json.loads((ROOT / 'live-data.json').read_text())
OUT = ROOT / 'imports/2026-09-23/photo-link-audit.json'
urls = set()
for source in DATA['sources'].values():
    for photo in source.get('imageReferences', []):
        if photo.get('review', {}).get('status') == 'keep':
            urls.add(photo['url'])
for record in DATA['records']:
    urls.update(p['url'] for p in record.get('reviewedPhotos', []))
    urls.update(p['url'] for p in record.get('publicPhotos', []))
for record in LIVE['records'].values():
    urls.update(p['url'] for p in record.get('images', []))
old = json.loads(OUT.read_text()) if OUT.exists() else {}

def check(url):
    if url.startswith('assets/photos/'):
        path = ROOT / url
        return url, {'displayUrl': url, 'status': 200 if path.is_file() else 404,
                     'mime': 'image/jpeg' if path.is_file() else None,
                     'bytes': path.stat().st_size if path.is_file() else None,
                     'error': None if path.is_file() else 'local asset missing'}
    display = url
    if 'img01.yzcdn.cn/' in url:
        display = url.split('?')[0] + '?imageView2/2/w/600/format/webp'
    proc = subprocess.run(
        ['curl', '-sSIL', '--max-time', '20', '-A', 'Mozilla/5.0',
         '-H', 'Accept: image/avif,image/webp,image/*', display],
        capture_output=True, text=True)
    responses = re.findall(r'^HTTP/\S+\s+(\d+)', proc.stdout, re.M)
    mime = re.findall(r'^content-type:\s*([^\r\n]+)', proc.stdout, re.I | re.M)
    length = re.findall(r'^content-length:\s*(\d+)', proc.stdout, re.I | re.M)
    return url, {'displayUrl': display, 'status': int(responses[-1]) if responses else None,
                 'mime': mime[-1].strip() if mime else None,
                 'bytes': int(length[-1]) if length else None,
                 'error': proc.stderr[-200:] if proc.returncode else None}

pending = sorted(url for url in urls if url not in old or old[url]['status'] != 200)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for i, (url, result) in enumerate(pool.map(check, pending), 1):
        old[url] = result
        if i % 10 == 0 or i == len(pending):
            OUT.write_text(json.dumps(old, ensure_ascii=False, indent=2) + '\n')
            print(f'{i}/{len(pending)} checked', flush=True)
print('URLS', len(old), 'HTTP', collections.Counter(v['status'] for v in old.values()),
      'MIME', collections.Counter(v['mime'] for v in old.values()), flush=True)
