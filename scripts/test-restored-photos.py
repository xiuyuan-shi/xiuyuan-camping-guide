"""The formerly visible photo set must not disappear again after an export."""
from pathlib import Path
import json,hashlib,importlib.util
ROOT=Path(__file__).resolve().parents[1]
load=lambda name:json.loads((ROOT/name).read_text())
index=load('data.json');fixture=load('tests/fixtures/photos-before-optimization.json');manifest=load('photo-restorations.json')
by_id={r['id']:r for r in index['records']};total=0
for expected in fixture['records']:
 photos=by_id[expected['id']]['displayPhotos'];actual={hashlib.sha256((p.get('originalUrl') or p['url']).encode()).hexdigest() for p in photos}
 assert actual>=set(expected['originalUrlHashes']),expected['id']+' lost previously displayed photos'
 assert len(photos)>=expected['count']
 total+=len(photos)
for record in index['records']:
 for photo in record['displayPhotos']:
  if photo.get('displayBasis')!='restored-previous':continue
  assert photo['kind']=='source' and photo['originalUrl'].startswith('https://') and photo['sourceUrl'].startswith('https://')
  body=(ROOT/photo['url']).read_bytes();assert body.startswith(b'\xff\xd8') and len(body)>512
  assert hashlib.sha256(body).hexdigest()==photo['sha256']
  assert photo['restoredFrom']==manifest['baselineCommit']
spec=importlib.util.spec_from_file_location('exporter',ROOT/'scripts/export-site.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
entry=next(p for rows in manifest['records'].values() for p in rows)
candidate={'url':entry['originalUrl'],'sourceUrl':entry['sourceUrl'],'status':'keep'}
record={'id':'fixture','name':'fixture','sourceIds':[]}
approved,held=exporter.photos(record,{'images':[candidate]}, {},load('policy.json'))
assert not approved,'new unknown photos must not inherit an old display decision'
approved,held=exporter.photos(record,{'images':[candidate]}, {},load('policy.json'),[entry])
assert len(approved)==1 and 'permission' not in approved[0] and 'associationConfirmed' not in approved[0]
bad={**entry,'sourceUrl':'https://example.org/wrong-source'}
try:exporter.photos(record,{'images':[candidate]}, {},load('policy.json'),[bad])
except ValueError:pass
else:raise AssertionError('restored photo must remain linked to its original source')
other=next(p for rows in manifest['records'].values() for p in rows if p['url']!=entry['url'])
bad={**entry,'url':other['url'],'sha256':other['sha256']}
try:exporter.photos(record,{'images':[candidate]}, {},load('policy.json'),[bad])
except ValueError:pass
else:raise AssertionError('another valid local image cannot replace the source photo')
approved,held=exporter.photos(record,{'images':[{**candidate,'status':'exclude'}]}, {},load('policy.json'),[entry])
assert not approved and held
print(f'PASS: all {fixture["total"]} prior photos across {fixture["places"]} places retained; local JPEG integrity and unchanged evidence facts')
