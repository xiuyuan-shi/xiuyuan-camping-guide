"""Publish the reviewed primary workbook; sanitized inputs and explicit decisions only."""
import collections,csv,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'imports/2026-09-23'
BATCH='2026-09-23'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def tidy(t):return re.sub(r'^表格摘录（未复核原文）：','',t or '').strip()
# Only these new narrative portions survived place-level and cross-note review.
DESCRIPTIONS={
7:'验证版将游览位置记为曲院风荷3号门，介绍以湖景和拍照为主。已有笔记提到西湖边露营体验，具体可搭帐区域与过夜安排需再确认。',
45:'位于临安青山湖。验证版以湖景、草坪和树林为主要特色，相关笔记分别介绍湖畔露营、花海和游览机位。景区游览范围不等同于太阳湾驿站的可搭帐区域。',
52:'位于临安大鱼线宣王桥附近，验证版将活动位置指向桥下溪边。相关笔记围绕露营、玩水与溯溪展开，选择营位时仍需确认实际入口和当日管理要求。',
75:'位于余杭良渚，相关介绍围绕康门水库的环湖游览与山野景观展开。具体露营落点尚未核清，环湖游览范围不等于可搭帐区域。',
78:'位于建德下涯之江村，验证版将山风农场与新安江沿线的乡村游览一并介绍。相关笔记包含晨雾、桨板和露营行程，沿江游览活动与农场服务项目需分别确认。',
109:'位于余杭小古城一带，新增依据为“春晓小古城苕溪营地正式开营”笔记。查看原文时请核对具体营地入口与可使用区域。',
131:'位于萧山北塘河一带，以河边草坪为主要环境。相关笔记介绍草坪露营和亲子骑行体验，具体活动区域与停车点请结合原文确认。',
155:'建德新安江沿线的驻车地点，相关笔记介绍白沙奇雾景观及晨雾、桨板、露营行程。晨雾与江景是相关游记的主要看点，驻车入口仍需核实。',
173:'位于建德之江村，资料以车中泊和新安江沿线休闲为主。验证版记载沿江道路较窄、沿途有停车点，并关联了自驾路线及建德露营体验笔记；具体驻车位置需以对应原文为准。',
185:'位于临安河桥古镇附近。验证版提供“河桥古镇停车场、过桥到水边”的到达线索，已有资料也指向古镇过桥后的溪滩。环境以溪水和石滩为主；溪滩游玩与可露营区域仍需结合现场管理区分。',
186:'位于建德市下涯镇之江村，验证版建议按“山风农场”查找地点。资料以草坪、乡村休闲和亲子活动为主，并提供山风农场及建德两日游笔记作为参考。',
}
# Detailed addresses were reviewed separately from the contaminated merged prose.
AREAS={7:'杭州西湖区曲院风荷3号门附近（验证版位置线索）',52:'杭州临安大鱼线宣王桥桥下溪边（入口待核）',186:'杭州市建德市下涯镇之江村，导航山风农场（入口待核）',185:'杭州临安河桥古镇停车场附近，过桥到水边（作者路线）'}
SAFE_RULE_ROWS={7,45,173}

def run():
 data=read(FOLDER/'baseline.json');rows=read(FOLDER/'source-rows.json');decisions=read(FOLDER/'decisions.json');held=read(FOLDER/'held-places.json');images=read(FOLDER/'image-review.json')['images']
 records={r['id']:r for r in data['records']};by_url={s['url'].split('?')[0].replace('/discovery/item/','/explore/'):sid for sid,s in data['sources'].items()}
 groups=collections.defaultdict(list)
 for row,d in zip(rows,decisions):
  if d['status']=='merge':groups[d['recordId']].append((row,d))
 audit=[]
 for rid,items in groups.items():
  r=records[rid];primary_ids=[];primary_paragraphs=[];primary_fields=[]
  for row,d in items:
   n=row['序号'];accepted=[]
   for note in d['notes']:
    if note['status']!='keep':continue
    i=note['slot'];url=note['url'];sid=by_url.get(url,'V'+url.rsplit('/',1)[-1]);by_url[url]=sid
    if sid not in data['sources']:
     data['sources'][sid]=dict(id=sid,title=row[f'笔记{i}标题'],author=row[f'笔记{i}作者'] or '作者未提供',date='原表未提供',url=url)
    s=data['sources'][sid];s['primaryWorkbook']=True
    if sid not in primary_ids:primary_ids.append(sid)
    accepted.append(sid)
   field_audit={'rowNumber':n,'recordId':rid,'adopted':['地点名称关联'],'withheld':[]}
   name=row['营地名称']
   if '\ufffd' not in name and name!=r['name'] and name not in r['aliases']:r['aliases'].append(name)
   if n in AREAS:r['area']=AREAS[n];field_audit['adopted'].append('独立复查的位置片段')
   if n in DESCRIPTIONS:
    primary_paragraphs.append({'text':DESCRIPTIONS[n],'sourceIds':accepted,'origin':'验证版清洗介绍','rowNumber':n});field_audit['adopted'].append('清洗后的介绍片段')
   else:field_audit['withheld'].append('原描述存在混合笔记聚合或缺乏独立归属，不整段覆盖')
   if n in SAFE_RULE_ROWS and accepted:
    fields=[]
    for col,key,label in [('免费/付费','fee','费用'),('是否可过夜','overnight','过夜'),('是否有厕所','toilet','卫生间'),('是否可开车直达','parking','车辆到达')]:
     value=row[col]
     if not value or value=='未知':continue
     value=('有厕所'+value[1:] if value.startswith('是') else value) if key=='toilet' else value
     fields.append({'key':key,'label':label,'value':'验证版记录：'+value})
    if fields:primary_fields.append({'sourceId':accepted[0],'sourceIds':accepted,'importBatch':BATCH,'priority':'primary','excelRows':[row['excelRow']],'caveat':'验证版整理的来源主张；未向营地方确认现行规则。','fields':fields})
    field_audit['adopted'].append('有同地点笔记支持的费用、过夜、厕所与交通主张')
   else:field_audit['withheld'].append('混合笔记汇总的费用与设施布尔值，不覆盖旧证据')
   audit.append(field_audit)
  anchors={'C157':['山风农场'],'C024':['河桥'],'C028':['宣王桥','大鱼线'],'C016':['青山湖'],'C172':['曲院风荷','西湖边'],'C216':['建德'],'C155':['杭钢'],'C213':['北塘河'],'C152':['康门'],'C060':['小古城'],'C186':['湘湖'],'C196':['白沙奇雾'],'C179':['东纪坞']}.get(rid,[r['name']])
  r['sourceIds']=list(dict.fromkeys(primary_ids+r['sourceIds']))
  r['sourceIds'].sort(key=lambda sid: -sum(term in data['sources'][sid]['title'] for term in anchors))
  r['evidence']=primary_fields+r['evidence']
  r['primaryData']={'name':'杭州热门露营地清单（验证版）','importedAt':BATCH,'rowNumbers':[row['序号'] for row,d in items],'sourceIds':primary_ids,'status':'reviewed-extract','note':'验证版优先，地点、描述和笔记逐项清洗；现行规则仍需确认。'}
  r['lastCollected']=BATCH
  # Source photos have their own approval and record binding; never inherit all 9 images from a note.
  r['reviewedPhotos']=[]
  for u,img in images.items():
   if img['status']!='keep' or rid not in img.get('recordIds',[]):continue
   related=[(row,d) for row,d in items if row['序号'] in img['rows']]
   if not related:continue
   matches=[(row,d,note) for row,d in related for note in d['notes'] if note['slot']==img.get('sourceSlot',1) and note['status']=='keep' and (not img.get('sourceRowNumber') or row['序号']==img['sourceRowNumber'])]
   if not matches:continue
   row,d,note=matches[0]
   sid=by_url[note['url']]
   r['reviewedPhotos'].append({'url':u,'sourceId':sid,'status':'keep','kind':'source','reviewedAt':BATCH,'label':r['name']+' · 来源景观配图','coverPriority':img.get('coverPriority',10),'description':'验证版提供并经内容筛选；区域景观不等于已确认营位。'})
  r['reviewedPhotos'].sort(key=lambda p:p.get('coverPriority',10))
  r['overview']={'paragraphs':primary_paragraphs[-1:]}
 supplements=read(ROOT/'photo-supplements.json')['records'] if (ROOT/'photo-supplements.json').exists() else {}
 for rid,photos in supplements.items():
  if rid in records and rid not in held:
   records[rid]['publicPhotos']=[p for p in photos if p['status']=='keep' and p['url'].startswith('https://') and p['sourceUrl'].startswith('https://')]
 # Structured descriptions expose existing evidence even when new text was rejected.
 for r in data['records']:
  if r['id'] in held:continue
  paragraphs=r.setdefault('overview',{'paragraphs':[]})['paragraphs']
  if not paragraphs:
   loc=next((tidy(f['value']) for e in r['evidence'] for f in e['fields'] if f['key']=='location' and '待核实' not in f['value']),r['area'])
   paragraphs.append({'text':r['name']+'。位置线索：'+loc.rstrip('。')+'。','sourceIds':r['sourceIds'][:1],'origin':'已有来源整理'})
  features=[];source_ids=[]
  for e in r['evidence']:
   if e.get('withheldCompilationClaims'):continue
   for f in e['fields']:
    if f['key'] in ['environment','audience','hiking','season','experience'] and len(f['value'])>2:
     v=tidy(f['value'])
     if v not in features:features.append(v);source_ids.append(e['sourceId'])
  if features:paragraphs.append({'text':'来源介绍：'+'；'.join(features[:4])[:900].rstrip('；。')+'。','sourceIds':list(dict.fromkeys(source_ids)),'origin':'来源摘要'})
  r['overview']['practical']=[{'key':key,'label':label,'values':list(dict.fromkeys(tidy(f['value']) for e in r['evidence'] for f in e['fields'] if f['key']==key))[:2]} for key,label in [('fee','费用参考'),('toilet','卫生间'),('overnight','过夜安排'),('parking','车辆与停车')]]
  env='；'.join(f['value'] for e in r['evidence'] for f in e['fields'] if f['key']=='environment')
  r['tags']=list(dict.fromkeys(r['tags']+[tag for tag in ['湖景','溪水','草坪','森林','竹林','日落','日出','水杉','河滩'] if tag in env]))
  r['detailCount']=len(r['evidence']);r['hasDetails']=r['hasDetails'] or bool(features or r.get('primaryData',{}).get('sourceIds'))
  r['mentionAuthors']=len({data['sources'][s]['author'] for s in r['sourceIds']})
 data['excludedPlaces']=[{'id':rid,'name':records[rid]['name'] if rid in records else next(p['name'] for p in data['excludedPlaces'] if p['id']==rid),'reason':reason} for rid,reason in held.items()]
 data['records']=[r for r in data['records'] if r['id'] not in held]
 data['updatedAt']=BATCH;data['nextUpdate']='2026-09-24'
 data['counts']=dict(total=len(data['records']),**{s:sum(r['scope']==s for r in data['records']) for s in ['hangzhou','nearby','outside']},withDetails=sum(r['hasDetails'] for r in data['records']))
 data['primarySource']={'name':'杭州热门露营地清单（验证版）','importedAt':BATCH,'reviewedRecords':len(groups),'policy':'通过检查的字段优先采用，旧资料补充；无关笔记、错配介绍和图片不入展示。'}
 save(ROOT/'data.json',data);save(FOLDER/'field-review.json',audit)
 summary={'inputRows':len(rows),'mergedRows':sum(d['status']=='merge' for d in decisions),'primaryRecords':len(groups),'duplicateRowsMerged':sum(d['status']=='merge' for d in decisions)-len(groups),'heldInputRows':sum(d['status']=='hold' for d in decisions),'newlyHeldExistingPlaces':len(data['excludedPlaces'])-len(read(FOLDER/'baseline.json')['excludedPlaces']),'acceptedNoteAssociations':sum(n['status']=='keep' for d in decisions for n in d['notes']),'rejectedNoteAssociations':sum(n['status']!='keep' for d in decisions for n in d['notes']),'newApprovedPhotos':sum(len(r.get('reviewedPhotos',[])) for r in data['records']),'publicSupplementPhotos':sum(len(r.get('publicPhotos',[])) for r in data['records']),'recordsWithThreeNotes':sum(len(r['sourceIds'])>=3 for r in data['records']),'counts':data['counts']}
 save(FOLDER/'summary.json',summary)
 with (ROOT/'杭州露营资料.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f,lineterminator='\n');w.writerow(['编号','名称','位置','主数据','营地介绍','笔记1','笔记2','笔记3'])
  for r in data['records']:
   links=[data['sources'][sid]['url'] for sid in r['sourceIds'][:3]]
   w.writerow([r['id'],r['name'],r['area'],'验证版优先' if r.get('primaryData') else '已有资料','\n'.join(p['text'] for p in r['overview']['paragraphs']),*(links+['']*(3-len(links)))])
 version=hashlib.sha256((ROOT/'data.json').read_bytes()).hexdigest()[:12];p=ROOT/'index.html';html=p.read_text();html=re.sub(r'(name="camp-data-version" content=")[^"]+',lambda m:m[1]+version,html);html=re.sub(r'(?<!-)data.json\?v=[a-f0-9]+','data.json?v='+version,html);html=re.sub(r'live-data.json\?v=[a-f0-9]+', 'live-data.json?v='+re.search(r'name="camp-live-version" content="([^"]+)', html)[1],html);p.write_text(html)
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
