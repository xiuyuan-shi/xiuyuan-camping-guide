"""Exercise retention, source association and isolated importer/exporter boundaries."""
import hashlib,json,subprocess,sys,tempfile,shutil,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import importlib.util
spec=importlib.util.spec_from_file_location('exporter',ROOT/'scripts/export-site.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
def read(path):return json.loads(path.read_text())
def run(script,root):return subprocess.run([sys.executable,str(root/'scripts'/script)],capture_output=True,text=True)
data=read(ROOT/'library.json');index=read(ROOT/'data.json');rows=read(ROOT/'workbook.json')['verifiedRows'];snapshot=read(ROOT/'tests/fixtures/retained-bf5f4af.json')
ids={r['id'] for r in data['records']};assert len(ids)==len(data['records'])
assert ids >= set(snapshot['recordIds']) and data['sources'].keys() >= set(snapshot['sourceIds'])
assert {r['rowNumber'] for r in rows} >= set(snapshot['rowNumbers']) and rows==data['verifiedRows']
assert {r['id'] for r in index['records']}==ids
assert index['counts']['total']==len(ids)
assert (ROOT/'data.json').stat().st_size < (ROOT/'library.json').stat().st_size/2
for r in data['records']:
 assert set(r['sourceIds'])<=data['sources'].keys()
 assert all(e['sourceId'] in r['sourceIds'] for e in r['evidence'])
 item=next(v for v in index['records'] if v['id']==r['id']);filename=item['detailUrl'].split('?')[0];detail=read(ROOT/filename)
 assert detail['record']['id']==r['id'] and detail['record']['evidence']==r['evidence']
 assert all(detail['sources'][sid]==data['sources'][sid] for sid in r['sourceIds'])
 assert item['detailUrl'].split('=')[-1]==hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()[:12]
 for p in item['displayPhotos']:
  if p.get('displayBasis')=='restored-previous':
   assert p['kind']=='source' and p['restoredFrom'] and p['restoredAt'] and p.get('permission')!='denied'
  else:assert p['permission']=='allowed' and p['associationConfirmed'] and p['license'] and p['licenseUrl']
 for p in item['displayPhotos']:
  if p['url'].startswith('assets/'):assert hashlib.sha256((ROOT/p['url']).read_bytes()).hexdigest()==p['sha256']
for row in rows:
 assert len(row['notes'])==3 and len({n['url'] for n in row['notes']})==3
 assert all(re.fullmatch(r'https://www\.xiaohongshu\.com/explore/[a-f0-9]{24}',n['url']) for n in row['notes'])
 assert not row['recordId'] or row['recordId'] in ids

# Explicit negative states must never be replaced by a historical keep/allowed flag.
photo=next(p for r in index['records'] for p in r['displayPhotos'] if p.get('permission')=='allowed' and p.get('displayBasis')!='restored-previous')
for change in [{'associationConfirmed':False},{'permission':'denied'},{'permission':'unknown'},{'status':'exclude'}]:
 candidate={**photo,**change};approved,held=exporter.photos({'name':'fixture','sourceIds':[]},{'images':[candidate]}, {},read(ROOT/'policy.json'))
 assert not approved and held
bad=read(ROOT/'library.json');bad['records'][0]['tags']='invalid'
try:exporter.validate(bad)
except ValueError:pass
else:raise AssertionError('invalid tags must be rejected before any export')
with tempfile.TemporaryDirectory(prefix='camp-data-regression-') as directory:
 copy=Path(directory)/'site';shutil.copytree(ROOT,copy,ignore=shutil.ignore_patterns('.git','__pycache__','overture-hangzhou-places.json'))
 canonical=(copy/'library.json').read_bytes();artifacts={p.relative_to(copy).as_posix():p.read_bytes() for p in [copy/'data.json',copy/'index.html',copy/'杭州露营资料.csv',copy/'workbook.json']}
 for script in ['export-site.py','import-verified.py','import-camps.py']:
  proc=run(script,copy);assert proc.returncode==0,proc.stderr
  assert (copy/'library.json').read_bytes()==canonical
  assert all((copy/f).read_bytes()==body for f,body in artifacts.items()),script
 amended=read(copy/'library.json');r=amended['records'][0];amended['sources']['fixture-preserved']={'id':'fixture-preserved','title':'isolated fixture','url':'https://example.org/fixture','author':'fixture','date':'2026-10-14'};r['sourceIds'].append('fixture-preserved');r['evidence'].append({'sourceId':'fixture-preserved','fields':[{'key':'experience','value':'isolated fixture','label':'fixture'}]})
 (copy/'library.json').write_text(json.dumps(amended,ensure_ascii=False));proc=run('import-verified.py',copy);assert proc.returncode==0,proc.stderr
 retained=read(copy/'library.json');assert 'fixture-preserved' in retained['sources'] and any(e['sourceId']=='fixture-preserved' for e in retained['records'][0]['evidence'])
 amended['records'].append({'id':'C990','name':'isolated fixture','scope':'hangzhou','type':'待分类','city':'杭州','area':'fixture','tags':[],'aliases':[],'sourceIds':['fixture-preserved'],'evidence':[],'lastCollected':'2026-10-14','conflict':False,'hasDetails':False})
 (copy/'library.json').write_text(json.dumps(amended,ensure_ascii=False));proc=run('export-site.py',copy);assert proc.returncode==0,proc.stderr
 assert len(read(copy/'data.json')['records'])==len(index['records'])+1
 live=read(copy/'live-data.json');original_live=(copy/'live-data.json').read_bytes();live['records']['C014']['routeSnapshot']['waypoints'][-1]['distance']=1000;(copy/'live-data.json').write_text(json.dumps(live));failed_route=run('test-published-routes.py',copy);assert failed_route.returncode!=0,'new excessive snap must fail rather than silently become historical held';(copy/'live-data.json').write_bytes(original_live)
 malformed=read(copy/'library.json');malformed['records'][-1]['tags']='invalid';before_invalid=(copy/'data.json').read_bytes();(copy/'library.json').write_text(json.dumps(malformed,ensure_ascii=False));proc=run('export-site.py',copy);assert proc.returncode!=0 and (copy/'data.json').read_bytes()==before_invalid
 (copy/'library.json').write_text(json.dumps(amended,ensure_ascii=False))
 before=(copy/'data.json').read_bytes();amended['records']=[r for r in amended['records'] if r['id']!='C990'];(copy/'library.json').write_text(json.dumps(amended,ensure_ascii=False));proc=run('export-site.py',copy);assert proc.returncode!=0
 assert (copy/'data.json').read_bytes()==before
print('PASS: retained IDs/rows/sources, lazy details, sourced photo assets, idempotence, new evidence preserved, valid expansion, destructive removal blocked')
