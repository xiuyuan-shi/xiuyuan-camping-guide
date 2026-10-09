#!/usr/bin/env python3
"""Summarize the 123-place location review without promoting search hits to facts."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'imports/2026-10-09'
original = json.loads((WORK / 'unresolved-123.json').read_text())
reports = {r['id']: r for r in json.loads((WORK / 'route-publication-report.json').read_text())}
approvals = json.loads((WORK / 'place-approvals.json').read_text())
nominatim = json.loads((WORK / 'nominatim-bounded.json').read_text())
overture = json.loads((WORK / 'overture-candidates.json').read_text())['records']
live = json.loads((ROOT / 'live-data.json').read_text())

specific_notes = {
    'C038': '杨家村存在多个同名地点，尚不能确定原文所指河岸或营位。',
    'C125': '可找到沧州村，但原文指沧州书苑附近河滩；村庄中心不能替代入口。',
    'C126': '仰天坪有多个同名山地地点，尚不能确定原文所指位置。',
    'C132': '可找到蝴蝶谷相关站点，但站点不等于营位或车辆入口。',
}
rows = []
for item in original['records']:
    rid = item['id']
    result = reports.get(rid)
    if result and result['status'] == 'published':
        status = 'published-reference'
        reason = approvals[rid]['precision']
    elif result and result['status'] == 'not-routed':
        status = 'matched-no-safe-road'
        reason = '同名地点已找到，但路网匹配距离超过 500 米，未发布车程。'
    else:
        status = 'unresolved'
        reason = specific_notes.get(rid, '公开检索尚未确认与原线索一致的营位或唯一车辆入口。')
    n = nominatim.get(rid, {})
    o = overture.get(rid, {})
    rows.append({
        'id': rid, 'name': item['name'], 'areaClue': item.get('area', ''),
        'status': status, 'reason': reason,
        'nominatimCandidateCount': len(n.get('results', [])),
        'overtureCandidateCount': len(o.get('candidates', [])),
        'publishedMapSource': approvals.get(rid, {}).get('sourceUrl'),
        'wulinmenDrivingMinutes': result.get('minutes') if status == 'published-reference' else None,
    })

counts = dict(Counter(row['status'] for row in rows))
assert len(rows) == 123 and len({r['id'] for r in rows}) == 123
assert counts == {'published-reference': 11, 'matched-no-safe-road': 1, 'unresolved': 111}
assert len(live['records']) == 59
output = {
    'reviewDate': '2026-10-10',
    'scope': '此前 123 处无可靠地图位置的杭州露营线索',
    'origin': original['origin'],
    'counts': counts,
    'method': '公开地图/景点页人工同名核对；Overture Places 及 OSM Nominatim 只作候选；已确认参考点使用 OSRM 预计算驾车路线。',
    'limits': '公布的是景点、公园、营地范围或停车场等参考点，并非全部为营位或入口；OSRM 车程不含实时路况；地点名称不证明允许露营。',
    'records': rows,
}
(WORK / 'location-review.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')

lines = [
    '# 杭州 123 处未定位线索核查（2026-10-10）', '',
    '本轮新增 **11 处有来源的地点参考点和预计算驾车路线**，公开页累计 59 处有路线。另 1 处找到同名地点，但距离可匹配道路超过 500 米，未发布车程；其余 111 处尚未得到足以确认唯一营位或车辆入口的坐标。', '',
    '路线统一从杭州武林门地铁站附近可通行道路出发，由 OSRM 计算，不含实时路况。地图参考点不等于营位或入口，也不证明该处允许搭帐篷、用火或过夜。', '',
    '| 地点 | 到参考点车程 | 地图来源 | 点位性质 |', '| --- | ---: | --- | --- |',
]
for row in rows:
    if row['status'] != 'published-reference':
        continue
    point = approvals[row['id']]
    lines.append(f'| {row["name"]} | 约 {row["wulinmenDrivingMinutes"]} 分钟 | [{point["source"]}]({point["sourceUrl"]}) | {point["pointKind"]} |')
lines.extend([
    '', '未发布的 112 处逐条状态见 [location-review.json](location-review.json)。搜索结果和模糊名称仅作为候选，未据此生成坐标或车程。', '',
    '公开候选源：[Overture Places](https://docs.overturemaps.org/guides/places/)、[OpenStreetMap Nominatim](https://nominatim.org/)。高德 Web 服务的 POI/路径规划接口需要 API Key；本轮没有密钥，使用可公开访问的地图地点页核对少数点位。', '',
])
(WORK / 'LOCATION_AUDIT.md').write_text('\n'.join(lines))
print(counts)
