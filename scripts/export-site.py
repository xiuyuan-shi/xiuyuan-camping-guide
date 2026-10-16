#!/usr/bin/env python3
"""Generate public views from library.json, without changing the authoritative library."""
import argparse,csv,hashlib,io,json,re,os,tempfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

ROOT=Path(__file__).resolve().parents[1]

def load(name):return json.loads((ROOT/name).read_text())
def dump(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n'
def digest(value):return hashlib.sha256(value.encode()).hexdigest()[:12]
def https(value):
    try:p=urlsplit(value or '');return p.scheme=='https' and bool(p.hostname) and not p.username and not p.password
    except ValueError:return False

def validate(data):
    records=data.get('records');sources=data.get('sources')
    if not isinstance(records,list) or not records or not isinstance(sources,dict):raise ValueError('资料库结构不完整')
    ids=[r['id'] for r in records]
    if len(ids)!=len(set(ids)) or not all(re.fullmatch(r'C\d+',x) for x in ids):raise ValueError('地点ID无效或重复')
    for r in records:
        for field in ['tags','aliases','sourceIds']:
            if not isinstance(r.get(field),list) or not all(isinstance(v,str) for v in r[field]):raise ValueError('地点'+field+'必须是字符串数组：'+str(r.get('id')))
        if not isinstance(r.get('evidence'),list):raise ValueError('地点证据必须是数组')
        if not isinstance(r.get('name'),str) or not isinstance(r.get('area',''),str) or not isinstance(r.get('type',''),str):raise ValueError('地点文本字段无效')
        if r.get('scope') not in ['hangzhou','nearby','outside'] or not r.get('name'):raise ValueError('地点范围或名称无效')
        if len(r.get('sourceIds',[]))!=len(set(r.get('sourceIds',[]))):raise ValueError('来源ID重复：'+r['id'])
        if any(x not in sources for x in r.get('sourceIds',[])):raise ValueError('地点引用不存在的来源：'+r['id'])
        if any(e.get('sourceId') not in r.get('sourceIds',[]) for e in r.get('evidence',[])):raise ValueError('证据来源未关联地点：'+r['id'])
        for fact in r.get('primaryFacts',{}).values():
            if fact.get('status') not in ['yes','no','free','paid','unknown','conflict']:raise ValueError('无效字段状态')
    for s in sources.values():
        if not https(s.get('url')):raise ValueError('来源链接不是HTTPS')
    if re.search(r'xsec_token|xsec_source|app_platform|/Users/|"(?:Cookie|Authorization)"\s*:',dump(data),re.I):raise ValueError('公开资料含非公开认证或本机信息')
    for row in data.get('verifiedRows',[]):
        if row.get('recordId') and row['recordId'] not in ids:raise ValueError('核对行指向不存在的地点')
        if len(row.get('notes',[]))!=3:raise ValueError('原始三条笔记链接缺失')

def claimed(r):
    keys={f['key'] for e in r.get('evidence',[]) for f in e.get('fields',[])}|set(r.get('primaryFacts',{}));out={}
    for k in sorted(keys):
        values=[f['value'] for e in r.get('evidence',[]) if e.get('priority')=='primary' for f in e.get('fields',[]) if f['key']==k]
        if not values:values=[f['value'] for e in r.get('evidence',[]) for f in e.get('fields',[]) if f['key']==k]
        out[k]=list(dict.fromkeys(str(v) for v in values if v))
    return out

def photos(r,live,sources,policy,restored=None):
    candidates=[]
    for p in live.get('images',[]):candidates.append(dict(p))
    for p in r.get('reviewedPhotos',[]):
        s=sources.get(p.get('sourceId'),{});candidates.append({**p,'sourceUrl':s.get('url'),'author':s.get('author'),'sourceTitle':s.get('title'),'associationConfirmed':p.get('associationConfirmed',False)})
    for p in r.get('publicPhotos',[]):candidates.append(dict(p))
    for sid in r.get('sourceIds',[]):
        s=sources[sid];rows={n for e in r.get('evidence',[]) if e['sourceId']==sid for n in e.get('excelRows',[])}
        for p in s.get('imageReferences',[]):
            if p.get('review',{}).get('status')=='keep' and rows.intersection(p.get('excelRows',[])):
                candidates.append({**p,'sourceUrl':s.get('url'),'author':s.get('author'),'sourceTitle':s.get('title'),'associationConfirmed':p.get('associationConfirmed',False)})
    unique={p['url']:p for p in candidates if p.get('url')};approved=[];held=[]
    identity=lambda p:re.sub(r'^http://','https://',p.get('originalUrl') or p.get('url',''))
    restore_by_url={identity(p):p for p in restored or []};seen=set()
    if len(restore_by_url)!=len(restored or []):raise ValueError('恢复图片清单重复：'+r.get('id',''))
    for p in unique.values():
        restoration=restore_by_url.get(identity(p))
        if restoration:seen.add(identity(p))
        local=p['url'].startswith('assets/photos/')
        signed=any(k.lower() in ['sign','expires','x-expires','xsec_token'] for k in parse_qs(urlsplit(p['url']).query))
        reason=None
        if p.get('status') in ['exclude','withheld','unavailable'] or p.get('review',{}).get('status')=='exclude':reason='内容审核未采用'
        elif p.get('permission')=='denied':reason='图片已有明确拒绝状态'
        elif restoration:
            if p.get('status')!='keep' and p.get('review',{}).get('status')!='keep':raise ValueError('恢复清单包含未通过旧内容筛选的图片')
            if restoration.get('sourceUrl')!=p.get('sourceUrl') or not https(p.get('sourceUrl')):raise ValueError('恢复图片来源与原记录不一致')
            filename=restoration.get('url','');path=ROOT/filename
            expected='assets/photos/restored-'+hashlib.sha256(identity(p).encode()).hexdigest()[:20]+'.jpg'
            if filename!=expected:raise ValueError('恢复图片资源与原图地址不匹配')
            if not re.fullmatch(r'assets/photos/restored-[a-f0-9]{20}\.jpg',filename) or not path.is_file():raise ValueError('恢复图片的本地资源不存在')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=restoration.get('sha256'):raise ValueError('恢复图片资源校验不一致')
            display={**p,**restoration,'displayBasis':'restored-previous'}
            # Displaying a prior source photo does not change permission/location facts.
            for key in ['permission','license','licenseUrl','associationConfirmed','associationEvidence']:
                if key in p:display[key]=p[key]
                else:display.pop(key,None)
            approved.append(display)
            continue
        elif p.get('permission')!='allowed':reason='未通过独立授权审核'
        elif p.get('associationConfirmed') is not True or not isinstance(p.get('associationEvidence'),dict) or p['associationEvidence'].get('sourceUrl')!=p.get('sourceUrl') or not p['associationEvidence'].get('scope'):reason='拍摄地点尚未确认'
        elif p.get('license') not in policy['photoLicenses'] or not https(p.get('licenseUrl')):reason='缺少可回查的使用许可'
        elif not https(p.get('sourceUrl')) or not p.get('author'):reason='来源或署名不完整'
        elif signed:reason='临时签名地址不用于正式展示'
        elif not local and not https(p['url']):reason='图片地址无效'
        elif local:
            path=ROOT/p['url']
            if not re.fullmatch(r'assets/photos/[a-z0-9-]+\.jpg',p['url']) or not path.is_file():reason='本地图片不存在'
            elif not p.get('sha256') or hashlib.sha256(path.read_bytes()).hexdigest()!=p['sha256']:reason='本地图片校验不一致'
        if reason:held.append({'sourceUrl':p.get('sourceUrl'),'reason':reason});continue
        approved.append({**p,'label':p.get('label') or r['name']+'区域实景'})
    if set(restore_by_url)-seen:raise ValueError('恢复清单图片已不在原始资料中：'+r.get('id',''))
    return approved[:9],held

def generate():
    data=load('library.json');live=load('live-data.json');policy=load('policy.json');meta=load('site-meta.json');validate(data)
    ids={r['id'] for r in data['records']}
    if set(live['records'])-ids:raise ValueError('扩展数据包含资料库中不存在的地点')
    restoration=load('photo-restorations.json') if (ROOT/'photo-restorations.json').exists() else {'records':{}}
    if restoration['records'] and (restoration.get('schemaVersion')!=1 or not re.fullmatch(r'[a-f0-9]{40}',restoration.get('baselineCommit','')) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',restoration.get('restoredAt',''))):raise ValueError('图片恢复清单的依据或日期无效')
    if set(restoration['records'])-ids:raise ValueError('恢复清单指向不存在的地点')
    for entries in restoration['records'].values():
        for entry in entries:
            if entry.get('displayBasis')!='restored-previous' or entry.get('restoredAt')!=restoration['restoredAt'] or not https(entry.get('originalUrl')):raise ValueError('图片恢复记录无效')
            entry['restoredFrom']=restoration['baselineCommit']
    counts={'total':len(ids),**{s:sum(r['scope']==s for r in data['records']) for s in ['hangzhou','nearby','outside']},'withDetails':sum(bool(r.get('hasDetails')) for r in data['records'])}
    source_index={sid:{k:s[k] for k in ['id','title','author','date','url'] if k in s} for sid,s in data['sources'].items()}
    files={};records=[];visible_photos=0;held_photos=0
    for original in data['records']:
        r=dict(original);r['claimedValues']=claimed(r);p,held=photos(r,live['records'].get(r['id'],{}),data['sources'],policy,restoration['records'].get(r['id'],[]))
        r['referenceEvidence']={}
        for dimension,keys in {'scenery':['environment'],'activities':['hiking','stove','experience'],'facilities':['toilet','parking'],'audience':['audience']}.items():
            evidence=[(e,f) for e in r.get('evidence',[]) if not e.get('withheldCompilationClaims') and re.fullmatch(r'\d{4}-\d{2}-\d{2}',data['sources'][e['sourceId']].get('date','')) for f in e.get('fields',[]) if f['key'] in keys]
            if evidence:r['referenceEvidence'][dimension]={'items':[{'key':f['key'],'value':f['value'],'label':f.get('label',''),'sourceId':e['sourceId']} for e,f in evidence]}
        r['displayPhotos']=p;r['photoReview']={'displayable':len(p),'withheld':len(held),'reasons':list(dict.fromkeys(h['reason'] for h in held))};visible_photos+=len(p);held_photos+=len(held)
        detail={'schemaVersion':2,'record':r,'sources':{sid:data['sources'][sid] for sid in r['sourceIds']},'verifiedRows':[v for v in data.get('verifiedRows',[]) if v.get('recordId')==r['id']]}
        body=dump(detail);filename='details/'+r['id']+'.json';files[filename]=body
        item={k:r[k] for k in ['id','name','aliases','city','area','scope','type','tags','lastCollected','conflict','hasDetails','sourceIds','primaryData','recommendationAudit'] if k in r}
        item['primaryFacts']={k:{'status':v['status'],'value':v.get('value','')} for k,v in r.get('primaryFacts',{}).items()}
        item['referenceEvidence']=r['referenceEvidence'];item['claimedValues']=r['claimedValues'];item['displayPhotos']=p;item['photoReview']=r['photoReview'];item['detailUrl']=filename+'?v='+digest(body)
        item['searchText']=' '.join(dict.fromkeys([r['name'],r.get('type',''),r.get('area',''),*r.get('tags',[]),*r.get('aliases',[]),*(x for vals in r['claimedValues'].values() for x in vals),*(p['text'] for p in r.get('overview',{}).get('paragraphs',[]))])).lower()
        records.append(item)
    index={'schemaVersion':2,'title':data['title'],'updatedAt':data['updatedAt'],'counts':counts,'records':records,'sources':source_index,'excludedPlaces':data.get('excludedPlaces',[]),'maintenance':meta['maintenance'],'policy':policy}
    files['workbook.json']=dump({'schemaVersion':2,'verifiedRows':data.get('verifiedRows',[])})
    index['workbookUrl']='workbook.json?v='+digest(files['workbook.json']);index['basemapUrl']='basemap.geojson?v='+hashlib.sha256((ROOT/'basemap.geojson').read_bytes()).hexdigest()[:12];files['data.json']=dump(index)
    output=io.StringIO(newline='');writer=csv.writer(output,lineterminator='\n');writer.writerow(['编号','名称','位置','主数据','营地介绍','笔记1','笔记2','笔记3'])
    def safe(v):
        text=str(v or '')
        return "'"+text if text and text[0] in '=+-@' else text
    for r in data['records']:
        row=next((v for v in data.get('verifiedRows',[]) if v.get('recordId')==r['id']),None);links=[n['url'] for n in row['notes']] if row else [data['sources'][sid]['url'] for sid in r['sourceIds'][:3]]
        writer.writerow(map(safe,[r['id'],r['name'],r.get('area',''),'主清单优先' if r.get('primaryData') else '已有资料','\n'.join(p['text'] for p in r.get('overview',{}).get('paragraphs',[])),*(links+['']*(3-len(links)))]))
    files['杭州露营资料.csv']='\ufeff'+output.getvalue()
    html=(ROOT/'index.html').read_text()
    for kind,filename in [('data','data.json'),('live','live-data.json')]:
        body=files.get(filename) or (ROOT/filename).read_text();version=digest(body)
        html=re.sub(r'(name="camp-'+kind+r'-version" content=")[^"]+',lambda m:m[1]+version,html)
        html=re.sub(r'(?<![\w-])'+re.escape(filename)+r'\?v=[^"\s]+',filename+'?v='+version,html)
    for filename in ['domain.js','services.js','store.js','router.js','offline-map.js','ratings.js','live.js','app.js','style.css']:
        if (ROOT/filename).exists():html=re.sub(re.escape(filename)+r'(?:\?v=[^"\s]+)?(?=")',filename+'?v='+digest((ROOT/filename).read_text()),html)
    files['index.html']=html
    files['build-manifest.json']=dump({'schemaVersion':1,'counts':counts,'displayPhotos':visible_photos,'withheldPhotoCandidates':held_photos,'assets':{f:hashlib.sha256(b.encode()).hexdigest() for f,b in files.items()}})
    return files

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args();files=generate()
    # A stale index is never accepted as the authority. Compare IDs to guard loss during normal export.
    old=load('data.json') if (ROOT/'data.json').exists() else {};missing={r['id'] for r in old.get('records',[])}-{r['id'] for r in load('library.json')['records']}
    if missing:raise ValueError('常规导出将删除地点，先明确归档决定：'+','.join(sorted(missing)))
    stale=[name for name,body in files.items() if not (ROOT/name).exists() or (ROOT/name).read_text()!=body]
    if args.check:
        if stale:raise SystemExit('导出不一致：'+', '.join(stale[:8]))
        print('PASS: canonical library and all generated public views match');return
    for name,body in files.items():
        path=ROOT/name;path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.read_text()==body:continue
        handle,temporary=tempfile.mkstemp(prefix='.export-',dir=path.parent)
        try:
            with os.fdopen(handle,'w',encoding='utf-8',newline='') as f:f.write(body)
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
    print('EXPORTED',len(files),'files;',len(load('library.json')['records']),'records retained')

if __name__=='__main__':main()
