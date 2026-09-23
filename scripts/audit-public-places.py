#!/usr/bin/env python3
"""One-time cached public-place lookup. Results are candidates, not camp coordinates.

Nominatim's public-service policy allows small one-time bulk lookups only from a
single thread, below one request per second, with a distinct User-Agent and a
local cache. Never run this script as a scheduled job or from the website.
"""
import datetime as dt
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode, quote

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'imports/2026-09-23/public-place-search.json'
DATA = json.loads((ROOT / 'data.json').read_text())
LIVE = json.loads((ROOT / 'live-data.json').read_text())
OSM = json.loads((ROOT/'imports/2026-09-23/osm-exact-search.json').read_text())
EXACT = {e.get('tags', {}).get('name') for e in OSM['elements']}
AGENT = 'XiuyuanCampingGuide/1.0 (+https://xiuyuan-shi.github.io/xiuyuan-camping-guide/)'
stored = json.loads(OUT.read_text()) if OUT.exists() else {}
names = [(r['id'], r['name']) for r in DATA['records']
         if r['scope'] == 'hangzhou' and r['id'] not in LIVE['records']
         and r['name'] not in EXACT]
for i, (rid, name) in enumerate(names, 1):
    if rid in stored:
        continue
    params = {'q': name, 'format': 'jsonv2', 'addressdetails': 1,
              'limit': 5, 'countrycodes': 'cn',
              'viewbox': '118.2,31.5,121.3,29.0'}
    url = 'https://nominatim.openstreetmap.org/search?' + urlencode(
        params, quote_via=quote)
    proc = subprocess.run(
        ['curl', '-fsSL', '--max-time', '25', '-A', AGENT,
         '-H', 'Accept: application/json', url],
        capture_output=True, text=True)
    entry = {'name': name, 'queriedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
             'query': url, 'results': []}
    if proc.returncode == 0:
        try:
            entry['results'] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            entry['error'] = 'invalid JSON'
    else:
        entry['error'] = proc.stderr[-300:]
    stored[rid] = entry
    OUT.write_text(json.dumps(stored, ensure_ascii=False, indent=2) + '\n')
    print(f'{i}/{len(names)} {rid} {name}: {len(entry["results"])}', flush=True)
    time.sleep(1.2)
print('LOOKUPS', len(names), 'CACHED', len(stored), flush=True)
