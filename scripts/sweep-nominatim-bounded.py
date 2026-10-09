#!/usr/bin/env python3
"""One-time bounded OSM lookup of unresolved names; never called by the site.

Public Nominatim policy: one thread, <=1 request/second, identifying User-Agent,
and persistent local cache. Results are candidates only, not approved pins.
"""
import datetime as dt
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'imports/2026-10-09/nominatim-bounded.json'
OUT.parent.mkdir(parents=True, exist_ok=True)
stored = json.loads(OUT.read_text()) if OUT.exists() else {}
data = json.loads((ROOT/'data.json').read_text())
live = json.loads((ROOT/'live-data.json').read_text())
missing = [r for r in data['records'] if r['scope']=='hangzhou'
           and r['id'] not in live['records']]
agent = 'XiuyuanCampingGuide/1.0 (+https://xiuyuan-shi.github.io/xiuyuan-camping-guide/)'
for i, record in enumerate(missing, 1):
    rid = record['id']
    if rid in stored:
        continue
    params = {'q': record['name'], 'format': 'jsonv2', 'addressdetails': 1,
              'limit': 10, 'countrycodes': 'cn',
              'viewbox': '118.2,31.5,121.3,29.0', 'bounded': 1}
    url = 'https://nominatim.openstreetmap.org/search?' + urlencode(params)
    proc = subprocess.run(['curl','-fsSL','--max-time','25','-A',agent,
                           '-H','Accept: application/json',url],
                          capture_output=True,text=True)
    entry = {'name': record['name'],
             'queriedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
             'query': url, 'results': []}
    if proc.returncode == 0:
        try:
            entry['results'] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            entry['error'] = 'invalid JSON'
    else:
        entry['error'] = proc.stderr[-250:]
    stored[rid] = entry
    OUT.write_text(json.dumps(stored, ensure_ascii=False, indent=2)+'\n')
    print(f'{i}/{len(missing)} {rid} {record["name"]}: '
          f'{len(entry["results"])}', flush=True)
    time.sleep(1.2)
print('LOOKUPS',len(stored),'CANDIDATES',
      sum(bool(x['results']) for x in stored.values()), flush=True)
