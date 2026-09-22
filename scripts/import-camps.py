"""Reproducible, conservative import of the reviewed 2026-09-22 spreadsheet.

Uses sanitized source rows, never the sharing tokens in the original workbook.
Run from any directory with Python 3. Existing records and evidence are retained.
"""
import collections
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = '2026-09-22'
FOLDER = ROOT / 'imports' / BATCH

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

# Human-reviewed aliases. Geographic parent/child names are not auto-merged.
EXISTING = {
16:28,24:16,29:138,35:15,36:15,37:17,38:18,39:19,40:20,41:21,
42:22,43:23,44:24,45:25,46:26,47:27,48:29,49:30,50:31,51:32,
53:28,55:152,57:23,58:62,59:63,61:65,79:33,80:34,81:35,82:36,
83:37,84:38,85:39,92:4,93:10,94:11,95:12,96:13,97:14,
117:24,119:150,120:35,137:10,141:1,142:2,143:3,144:5,145:6,
146:7,147:8,148:9,159:57,160:58,161:59,162:60,172:104,
103:28,185:83,188:150,195:10,198:143,200:3,
}
# Missing identity, unresolved near-duplicates, or collection/route rather than a site.
HOLD = {
1:'缺少可定位名称',10:'缺少可定位名称',31:'整条大鱼线，不能作为独立营地',
32:'双溪与进贤村并列，具体营位不明',60:'湘湖渔村与已有停车场范围关系待核',
62:'青山村、艺术村与已有农庄停车点范围关系待核',63:'进贤村溪边与已有村域线索范围关系待核',64:'苕溪范围过大',
67:'古城桥古城坝与已有安禾村古城桥对应关系待核',76:'只定位到龙岗镇',
77:'只定位到千岛湖',87:'沿江路线，非独立营地',88:'缺少可定位名称',89:'缺少可定位名称',
90:'湘湖房车营地与沐心岛是否同一经营方待核',91:'风之谷与已有风之谷蓝色森林是否同一地点待核',98:'壶源溪范围过大',99:'户外组织，非地点',
100:'多地点合集，未提供地点名',102:'缺少可定位名称',104:'与已有有风营地名称相同但地址、价格不一致，待核身份',
107:'公园名称不明，不能合并到杭钢公园',109:'缺少可定位名称',112:'秘境宣传名，身份不明',
113:'多地点图片合集，未提供地点名',115:'缺少可定位名称',118:'雾凇谷与已有雾松谷是否同一地点待核',
131:'只定位到戴村',132:'沿江柳杉林与该笔记多个活动点的对应关系不明',135:'只定位到萧山',
139:'缺少可定位名称',140:'缺少经营主体名称',149:'松针描述可能并非营地专名',150:'名称乱码且位置不明',
152:'缺少可定位名称',154:'作者推荐名，非地点名',155:'缺少可定位名称',156:'缺少可定位名称',
158:'溪畔营地名称泛化，身份待核',165:'溪边营地名称泛化，身份待核',166:'采摘合集，地点不明',
167:'缺少可定位名称',169:'缺少可定位名称',170:'缺少可定位名称',171:'只定位到富阳',
173:'缺少可定位名称',174:'缺少可定位名称',175:'缺少可定位名称',177:'缺少可定位名称',
178:'缺少可定位名称',179:'名称乱码且位置不明',180:'缺少可定位名称',181:'缺少可定位名称',
182:'缺少经营主体名称',183:'太子尖高山营地与太子尖星空营地是否同一经营方待核',
184:'公园名称不明，保留同笔记补充信息',187:'缺少可定位名称',197:'具体地点仅在图片中，尚未核对',
199:'缺少经营主体名称',
}
# New locations with identifiable duplicate aliases, evaluated using address + name.
NEW_ALIASES = {164:6,74:8,176:23,101:56,138:105,196:105,110:185,
186:114,125:7,157:128,189:130,192:133,193:134,194:136}
# The old G09 source ties row 56 to a specific parking site only; do not infer it here.
# New geographic regions remain distinct from a specific campsite inside them.

def text(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()

def note_id(url):
    m = re.search(r'/(?:explore|item)/([a-f0-9]{24})', url)
    if not m:
        raise ValueError('Invalid note URL')
    return m.group(1)

def known(value):
    return bool(value and value != '未知')

def urls(row):
    return list(dict.fromkeys(u for i in range(1,10)
        for u in re.findall(r'https?://[^\s]+', row.get(f'实拍图{i}') or '')))

def polarity(value):
    if value.startswith('否'): return 'no'
    if value.startswith('是'): return 'yes'
    return None

def run():
    data = json.loads((ROOT/'data.json').read_text())
    rows = json.loads((FOLDER/'source-rows.json').read_text())
    assert len(rows) == 200 and {r['序号'] for r in rows} == set(range(1,201))
    records = {r['id']:r for r in data['records']}
    # Persist decisions for audit and idempotence, keeping published IDs stable.
    decision_path = FOLDER/'decisions.json'
    previous = json.loads(decision_path.read_text()) if decision_path.exists() else []
    prior_ids = {d['rowNumber']:d['recordId'] for d in previous if d['recordId']}
    mapping = {n:f'C{i:03}' for n,i in EXISTING.items()}
    mapping[110] = 'C083'
    next_id = max(int(k[1:]) for k in records)+1
    new_ids = set(d['recordId'] for d in previous if d.get('newRecord'))
    row_by_num = {r['序号']:r for r in rows}
    for row in rows:
        n = row['序号']
        if n in HOLD or n in mapping or n in NEW_ALIASES: continue
        rid = prior_ids.get(n)
        if not rid:
            rid = f'C{next_id:03}'; next_id += 1
        mapping[n] = rid
        new_ids.add(rid)
        if rid in records: continue
        name, area = text(row['营地名称']), text(row['位置/地址'])
        scope = 'nearby' if any(x in area for x in ['安吉','海宁','杭州周边']) else 'hangzhou'
        city = '湖州' if '安吉' in area else '嘉兴' if '海宁' in area else '待核实' if scope=='nearby' else '杭州'
        kind = '公园与绿地' if '公园' in name else '待分类'
        records[rid] = dict(id=rid,name=name,aliases=[],city=city,area=area,scope=scope,type=kind,
            sourceIds=[],evidence=[],tags=[],lastCollected=BATCH,conflict=False,note='',fullVerified=False,
            hasDetails=False,mentionAuthors=0,summary='表格提供的地点线索，具体营位及现行规则待核实。',detailCount=0)
        data['records'].append(records[rid])
    for n,parent in NEW_ALIASES.items():
        if n not in mapping: mapping[n] = mapping[parent]
    assert set(mapping) | set(HOLD) == set(range(1,201))
    assert not (set(mapping) & set(HOLD))

    groups = collections.defaultdict(list)
    for row in rows: groups[note_id(row['笔记链接'])].append(row)
    image_notes = collections.defaultdict(set)
    for nid, rs in groups.items():
        for row in rs:
            for url in urls(row): image_notes[url].add(nid)
    by_note = {note_id(s['url']):sid for sid,s in data['sources'].items() if 'xiaohongshu.com/' in s['url']}
    source_ids = {}
    audits = []
    for nid,rs in groups.items():
        sid = by_note.get(nid, 'X'+nid)
        source_ids[nid] = sid
        first = rs[0]
        snap = dict(batch=BATCH,importedAt=BATCH,originalCaptureDate=None,
            rowNumbers=[r['序号'] for r in rs],excelRows=[r['excelRow'] for r in rs],
            title=text(first['来源笔记标题']),author=text(first['笔记作者']),
            extractionNote='由用户表格导入，未复核原文；导入日不是原文发布日或互动采样日。')
        metrics = []
        for row in rs:
            likes,saves,comments,total = [int(row[k]) for k in ['点赞数','收藏数','评论数','总互动量']]
            metrics.append(dict(rowNumber=row['序号'],likes=likes,saves=saves,comments=comments,
                reportedTotal=total,calculatedTotal=likes+saves+comments,
                totalMismatch=total != likes+saves+comments))
        snap['interactionRows'] = metrics
        if sid not in data['sources']:
            data['sources'][sid] = dict(id=sid,title=snap['title'],author=snap['author'],date='原表未提供',
                url=first['笔记链接'],importedAt=BATCH)
        src = data['sources'][sid]
        src['spreadsheetImports'] = [s for s in src.get('spreadsheetImports',[]) if s['batch']!=BATCH] + [snap]
        src['imageReferences'] = [dict(url=u,status='unverified',
            referencedByNotes=len(image_notes[u]),
            excelRows=[row['excelRow'] for row in rs if u in urls(row)])
            for u in dict.fromkeys(u for row in rs for u in urls(row))]
        audits.append(dict(sourceId=sid,url=first['笔记链接'],rowNumbers=snap['rowNumbers'],
            images=list(dict.fromkeys(u for row in rs for u in urls(row))),
            imageStatus='仅保留来源线索；地点归属、拍摄日期及转载许可未核实，不进入实景相册',
            interactionRows=metrics))

    per_record_source = collections.defaultdict(list)
    decisions = []
    for row in rows:
        n = row['序号']; rid = mapping.get(n); sid = source_ids[note_id(row['笔记链接'])]
        decisions.append(dict(rowNumber=n,excelRow=row['excelRow'],name=row['营地名称'],
            recordId=rid,sourceId=sid,newRecord=rid in new_ids if rid else False,
            status='待核实' if not rid else '新增地点' if rid in new_ids else '合并已有地点',
            reason=HOLD.get(n,'名称及地址人工比对；保留原始表格行号，不据同名自动合并')))
        if not rid: continue
        rec = records[rid]
        name = text(row['营地名称'])
        if name != rec['name'] and '\ufffd' not in name and name not in rec['aliases']:
            rec['aliases'].append(name)
        if sid not in rec['sourceIds']: rec['sourceIds'].append(sid)
        per_record_source[(rid,sid)].append(row)

    conflict_count = 0
    withheld_count = 0
    field_map = [('位置/地址','location','位置线索'),('免费/付费','fee','费用线索'),
        ('是否可过夜','overnight','过夜线索'),('是否可用卡式炉','stove','用火线索'),
        ('是否有厕所','toilet','厕所线索'),('是否可开车直达','parking','交通线索'),
        ('特色亮点','environment','环境与活动摘录')]
    for (rid,sid),rs in per_record_source.items():
        rec = records[rid]
        nid = note_id(rs[0]['笔记链接'])
        targets = {mapping.get(row['序号'], 'hold:'+str(row['序号'])) for row in groups[nid]}
        # Repeated extraction of the same place is not a multi-place compilation.
        compilation = len(targets)>1
        fields = []
        issues = []
        for column,key,label in field_map:
            vals = list(dict.fromkeys(text(row[column]) for row in rs if known(text(row[column]))))
            if not vals: continue
            if compilation and key!='location':
                withheld_count += 1
                continue
            if any('\ufffd' in v for v in vals):
                issues.append(f'{label}含乱码，未写入可筛选字段')
                vals = [v for v in vals if '\ufffd' not in v]
                if not vals: continue
            signs = {polarity(v) for v in vals} - {None}
            if len(signs)>1:
                issues.append(f'{label}在同一来源的表格行中冲突：'+ '；'.join(vals))
                continue
            if key=='stove':
                val = '表格摘录（未复核原文）：'+ '；'.join(vals) + '。烧烤或其他炉具的描述不等于卡式炉许可。'
            elif key=='toilet':
                val = '表格摘录（未复核原文）：'+ '；'.join('有厕所'+v[1:] if v.startswith('是') else '无厕所'+v[1:] if v.startswith('否') else v for v in vals)
            else:
                val = '表格摘录（未复核原文）：'+ '；'.join(vals)
            fields.append(dict(key=key,label=label,value=val))
        if compilation:
            fields.append(dict(key='experience',label='表格提取范围待核',value='同一笔记对应多个地点；费用、设施和活动可能是合集通用描述，本次仅收录地点与位置线索。'))
        if issues:
            conflict_count += 1
            rec['conflict'] = True
            fields.append(dict(key='conflict',label='表格信息待核',value='；'.join(issues)))
        rec['evidence'] = [e for e in rec['evidence'] if not (e.get('importBatch')==BATCH and e['sourceId']==sid)]
        rec['evidence'].append(dict(sourceId=sid,importBatch=BATCH,excelRows=[r['excelRow'] for r in rs],
            caveat='用户表格摘录，尚未复核原文及当前管理规则。',fields=fields,
            withheldCompilationClaims=compilation))
        rec['lastCollected'] = BATCH
        rec['hasDetails'] = rec['hasDetails'] or any(f['key'] not in ['location','conflict','experience'] for f in fields)
        rec['detailCount'] = len(rec['evidence'])
        rec['mentionAuthors'] = len({data['sources'][s]['author'] for s in rec['sourceIds'] if data['sources'][s]['author']})

    data['updatedAt'] = BATCH
    data['counts'] = dict(total=len(data['records']),**{s:sum(r['scope']==s for r in data['records']) for s in ['hangzhou','nearby','outside']},withDetails=sum(r['hasDetails'] for r in data['records']))
    summary = dict(inputRows=len(rows),uniqueNotes=len(groups),mergedRows=len(mapping),
        heldRows=len(HOLD),addedRecords=len(new_ids),updatedExistingRecords=len(set(mapping.values())-new_ids),
        distinctImportedRecords=len(set(mapping.values())),collapsedRows=len(mapping)-len(set(mapping.values())),
        conflictingRecordSources=conflict_count,withheldCompilationFields=withheld_count,
        interactionTotalMismatchRows=sum(m['totalMismatch'] for a in audits for m in a['interactionRows']),
        uniqueImageUrls=len({u for a in audits for u in a['images']}),counts=data['counts'])
    save(ROOT/'data.json',data)
    save(decision_path,decisions)
    save(FOLDER/'source-audit.json',audits)
    save(FOLDER/'summary.json',summary)
    with (ROOT/'杭州露营资料.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(['编号','名称','归属线索','类别线索','采集时间','有详情','核验状态','原文来源'])
        for r in data['records']:
            writer.writerow([r['id'],r['name'],r['city'],r['type'],r['lastCollected'],'是' if r['hasDetails'] else '否',
                '已核实' if r['fullVerified'] else '信息待核实',';'.join(data['sources'][s]['url'] for s in r['sourceIds'])])
    with (FOLDER/'row-review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.writer(f, lineterminator="\n"); writer.writerow(['原表行号','序号','原名称','处理结果','地点ID','合并名称','说明'])
        for d in decisions:
            writer.writerow([d['excelRow'],d['rowNumber'],d['name'],d['status'],d['recordId'],records[d['recordId']]['name'] if d['recordId'] else '',d['reason']])
    html = (ROOT/'index.html').read_text()
    version = hashlib.sha256((ROOT/'data.json').read_bytes()).hexdigest()[:12]
    html = re.sub(r'(name="camp-data-version" content=")[^"]+',lambda m:m[1]+version,html)
    html = re.sub(r'data.json\?v=[a-f0-9]+', 'data.json?v='+version, html)
    (ROOT/'index.html').write_text(html)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__ == '__main__': run()
