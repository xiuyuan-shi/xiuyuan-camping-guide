"""Regression checks for source association, cleaning, IDs, and reproducibility."""
import csv,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
d=read(ROOT/'data.json');folder=ROOT/'imports/2026-09-23';base=read(folder/'baseline.json');rows=read(folder/'source-rows.json');dec=read(folder/'decisions.json');review=read(folder/'image-review.json')['images'];held=read(folder/'held-places.json')
ids={r['id'] for r in d['records']};assert len(ids)==192 and not ids & set(held)
assert d['counts']['hangzhou']==171 and len([r for r in d['records'] if r.get('primaryData')])==89
assert len(dec)==195 and sum(x['status']=='merge' for x in dec)==111
assert len(d['verifiedRows'])==len(rows)==195
assert all(len(v['notes'])==3 and len({n['url'] for n in v['notes']})==3 for v in d['verifiedRows'])
assert sum(len(v['notes']) for v in d['verifiedRows'])==585
assert len({n['url'] for v in d['verifiedRows'] for n in v['notes']})==186
for original,v,decision in zip(rows,d['verifiedRows'],dec):
 assert v['rowNumber']==original['序号'] and v['name']==original['营地名称']
 assert v['area']==original['位置/地址'] and v['highlights']==original['特色亮点']
 assert v['rawDescription']==original['营地描述']
 assert v['interactions']=={key:original[key] for key in ['笔记1点赞','笔记1收藏','笔记1评论','总互动量']}
 assert [(p['slot'],p['url']) for p in v['imageCandidates']]==[(i,original[f'实拍图{i}']) for i in range(1,10) if original.get(f'实拍图{i}')]
 for key,column in {'fee':'免费/付费','overnight':'是否可过夜','stove':'是否可用卡式炉','toilet':'是否有厕所','parking':'是否可开车直达'}.items():assert v['facts'][key]==original[column]
 for i,n in enumerate(v['notes'],1):
  assert n['url']==original[f'笔记{i}链接'] and n['title']==(original[f'笔记{i}标题'] or '原表未提供标题')
  assert n['association']==('matched' if decision['status']=='merge' and decision['notes'][i-1]['status']=='keep' else 'unconfirmed')
 assert v['imageReview']['supplied']==v['imageReview']['approved']+v['imageReview']['existing']+v['imageReview']['withheld']
assert all(len(r['sourceIds'])==len(set(r['sourceIds'])) for r in d['records'])
assert sum(len(r.get('reviewedPhotos',[])) for r in d['records'])==14
for r in d['records']:
 assert all(s in d['sources'] for s in r['sourceIds'])
 assert all(e['sourceId'] in r['sourceIds'] for e in r['evidence'])
 assert r['overview']['paragraphs']
 if r.get('primaryData'):
  assert len(r['primaryFacts'])==5
  assert any(p['origin'].startswith('验证版') for p in r['overview']['paragraphs'])
  assert all(any(v['rowNumber']==n and v['recordId']==r['id'] for v in d['verifiedRows']) for n in r['primaryData']['rowNumbers'])
  for key,column in {'fee':'免费/付费','overnight':'是否可过夜','stove':'是否可用卡式炉','toilet':'是否有厕所','parking':'是否可开车直达'}.items():
   assert r['primaryFacts'][key]['entries']==[{'rowNumber':v['rowNumber'],'value':v['facts'][key]} for v in d['verifiedRows'] if v['recordId']==r['id']]
 for p in r.get('reviewedPhotos',[]):
  assert review[p['url']]['status']=='keep' and r['id'] in review[p['url']]['recordIds'] and p['sourceId'] in r['sourceIds']
 for s in r.get('primaryData',{}).get('sourceIds',[]):assert not re.search(r'成都|淄博|深圳|Yosemite|枣庄|日本|无锡',d['sources'][s]['title'])
 assert not r['fullVerified']
by_id={r['id']:r for r in d['records']}
assert by_id['C028']['primaryFacts']['fee']['status']=='conflict'
assert by_id['C010']['primaryFacts']['fee']['status']=='conflict'
assert by_id['C024']['primaryFacts']['fee']['status']=='free'
assert by_id['C143']['primaryFacts']['stove']['status']=='yes'  # another row says yes; BBQ-only row itself is not proof
assert sum(r['primaryFacts']['fee']['status']=='conflict' for r in d['records'] if r.get('primaryData'))>=5
assert sum(len(r.get('publicPhotos',[])) for r in d['records'])==3
julin=next(r for r in d['records'] if r['id']=='C035')
assert len(julin['reviewedPhotos'])==2
assert all(d['sources'][p['sourceId']]['url'].endswith('6938d309000000001d03ca54') for p in julin['reviewedPhotos'])
for rid in ['C039','C003']:
 photos=next(r for r in d['records'] if r['id']==rid)['publicPhotos']
 assert photos and all(p['status']=='keep' and p['sourceUrl'].startswith('https://') for p in photos)
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
assert len(list(csv.reader((ROOT/'验证版逐行核对.csv').open(encoding='utf-8-sig'))))==196
files=['data.json','杭州露营资料.csv','验证版逐行核对.csv','index.html','imports/2026-09-23/summary.json']
hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
for script in ['import-verified.py','import-camps.py']:
 subprocess.run([sys.executable,str(ROOT/'scripts'/script)],stdout=subprocess.DEVNULL,check=True)
 assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in hashes.items()),script
print('PASS: all 195 workbook rows, 585 links, five primary facts, description, photo review, CSV, and importer idempotence')
