"""Regression checks for source association, cleaning, IDs, and reproducibility."""
import csv,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
d=read(ROOT/'data.json');folder=ROOT/'imports/2026-09-23';base=read(folder/'baseline.json');dec=read(folder/'decisions.json');review=read(folder/'image-review.json')['images'];held=read(folder/'held-places.json')
ids={r['id'] for r in d['records']};assert len(ids)==192 and not ids & set(held)
assert d['counts']['hangzhou']==171 and len([r for r in d['records'] if r.get('primaryData')])==89
assert len(dec)==195 and sum(x['status']=='merge' for x in dec)==111
assert all(len(r['sourceIds'])==len(set(r['sourceIds'])) for r in d['records'])
assert sum(len(r.get('reviewedPhotos',[])) for r in d['records'])==12
for r in d['records']:
 assert all(s in d['sources'] for s in r['sourceIds'])
 assert all(e['sourceId'] in r['sourceIds'] for e in r['evidence'])
 assert r['overview']['paragraphs']
 for p in r.get('reviewedPhotos',[]):
  assert review[p['url']]['status']=='keep' and r['id'] in review[p['url']]['recordIds'] and p['sourceId'] in r['sourceIds']
 for s in r.get('primaryData',{}).get('sourceIds',[]):assert not re.search(r'成都|淄博|深圳|Yosemite|枣庄|日本|无锡',d['sources'][s]['title'])
 assert not r['fullVerified']
# Wrong notes in the new sheet must not newly attach to a place just to reach three.
original={r['id']:r for r in base['records']}
for row in dec:
 if row['status']!='merge':continue
 r=next(r for r in d['records'] if r['id']==row['recordId'])
 newurls={d['sources'][sid]['url'] for sid in r['sourceIds'] if sid not in original[r['id']]['sourceIds']}
 for note in row['notes']:
  if note['status']=='exclude':assert note['url'] not in newurls, (r['id'],note['url'])
assert not re.search(r'xsec_token|xsec_source|app_platform',json.dumps(d))
assert len(list(csv.reader((ROOT/'杭州露营资料.csv').open(encoding='utf-8-sig'))))==193
files=['data.json','杭州露营资料.csv','index.html','imports/2026-09-23/summary.json']
hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
for script in ['import-verified.py','import-camps.py']:
 subprocess.run([sys.executable,str(ROOT/'scripts'/script)],stdout=subprocess.DEVNULL,check=True)
 assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in hashes.items()),script
print('PASS: records, review gates, associations, photo binding, no token leakage, CSV, primary and legacy importer idempotence')
