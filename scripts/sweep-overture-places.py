#!/usr/bin/env python3
"""One-time, cached Overture Places candidate sweep for unresolved Hangzhou rows.

Candidates are never published automatically: a name match can be a park centre,
an unrelated homonym, or a closed business rather than a campsite entrance.
"""
import datetime as dt
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'imports/2026-10-09'
OUT.mkdir(parents=True, exist_ok=True)
CACHE = OUT / 'overture-hangzhou-places.json'
RELEASE = '2026-09-23.1'
SOURCE = (f's3://overturemaps-us-west-2/release/{RELEASE}/'
          'theme=places/type=place/*')


def normalize(value):
    value = unicodedata.normalize('NFKC', value or '').lower()
    return re.sub(r'[^\w\u4e00-\u9fff]', '', value)


def variants(record):
    names = [record['name'], *record.get('aliases', [])]
    out = set()
    for name in names:
        out.add(normalize(name))
        for part in re.split(r'[（(·及—－/]', name):
            if len(normalize(part)) >= 3:
                out.add(normalize(part))
        for prefix in ('杭州', '千岛湖', '富阳', '桐庐', '余杭',
                       '临安', '萧山', '建德', '淳安'):
            if name.startswith(prefix) and len(normalize(name[len(prefix):])) >= 3:
                out.add(normalize(name[len(prefix):]))
    return {x for x in out if len(x) >= 2}


def score(query, candidate):
    if query == candidate:
        return 1.0
    if len(query) >= 3 and (query in candidate or candidate in query):
        return min(len(query), len(candidate)) / max(len(query), len(candidate)) * .9
    return SequenceMatcher(None, query, candidate).ratio() * .78


if CACHE.exists():
    places = json.loads(CACHE.read_text())['places']
else:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2'")
    rows = con.execute(f"""
        SELECT id, names, bbox.xmin, bbox.ymin, addresses, websites,
               taxonomy.primary, operating_status, sources
        FROM read_parquet('{SOURCE}', filename=true, hive_partitioning=1)
        WHERE bbox.xmin BETWEEN 118.2 AND 121.3
          AND bbox.ymin BETWEEN 29.0 AND 31.5
    """).fetchall()
    places = []
    for row in rows:
        pid, names, lon, lat, addresses, websites, kind, status, sources = row
        places.append({'id': pid, 'name': names['primary'] if names else None,
                       'commonNames': names.get('common') if names else None,
                       'latitude': lat, 'longitude': lon, 'addresses': addresses,
                       'websites': websites, 'category': kind,
                       'operatingStatus': status,
                       'sources': [{'dataset': s.get('dataset'),
                                    'license': s.get('license'),
                                    'recordId': s.get('record_id')}
                                   for s in (sources or [])]})
    CACHE.write_text(json.dumps({'release': RELEASE,
                                 'downloadedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
                                 'source': SOURCE, 'places': places}, ensure_ascii=False) + '\n')

data = json.loads((ROOT / 'data.json').read_text())
live = json.loads((ROOT / 'live-data.json').read_text())
missing = [r for r in data['records'] if r['scope'] == 'hangzhou'
           and r['id'] not in live['records']]
matches = {}
for record in missing:
    options = variants(record)
    ranked = []
    for place in places:
        pname = normalize(place['name'])
        if not pname:
            continue
        pnames = [pname, *(normalize(n) for n in (place['commonNames'] or {}).values())]
        best = max((score(q, p) for q in options for p in pnames), default=0)
        if best >= .55:
            ranked.append((best, place))
    ranked.sort(key=lambda x: (-x[0], x[1]['name'] or ''))
    matches[record['id']] = {'name': record['name'], 'area': record.get('area', ''),
                             'aliases': record.get('aliases', []),
                             'candidates': [{'nameScore': round(s, 3), **p}
                                            for s, p in ranked[:8]]}

(OUT / 'overture-candidates.json').write_text(
    json.dumps({'release': RELEASE, 'checkedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
                'source': SOURCE, 'records': matches}, ensure_ascii=False, indent=2) + '\n')
print('PLACES', len(places), 'RECORDS', len(missing),
      'WITH_CANDIDATES', sum(bool(x['candidates']) for x in matches.values()))
for rid, result in matches.items():
    if result['candidates']:
        print(rid, result['name'], '=>',
              [(x['name'], x['nameScore'], x['category'])
               for x in result['candidates'][:3]])
