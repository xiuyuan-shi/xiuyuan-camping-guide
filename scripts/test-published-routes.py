"""All references retain provenance; invalid historical routes stay held."""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/'library.json').read_text());live=json.loads((ROOT/'live-data.json').read_text());policy=json.loads((ROOT/'policy.json').read_text())
assert policy['roadSnapMaxMeters']==500
reviews=json.loads((ROOT/'route-reviews.json').read_text())
records={r['id']:r for r in data['records']};origin=live['origin'];eligible=0;held=[]
assert origin['name']=='杭州武林门地铁站'
for rid,item in live['records'].items():
 assert records[rid]['name']==item['name']
 location=item['location'];assert location['sourceUrl'].startswith('https://') and location['precision']
 assert -90<=location['latitude']<=90 and -180<=location['longitude']<=180
 route=item['routeSnapshot'];assert route['originLocation']==origin
 assert all(route['destinationLocation'][key]==location[key] for key in ['latitude','longitude'])
 assert route['duration']>0 and route['distance']>0 and len(route['waypoints'])==2
 if any(w['distance']>policy['roadSnapMaxMeters'] for w in route['waypoints']):
  assert reviews.get(rid,{}).get('status')=='held' and reviews[rid].get('reason'),rid+' has undeclared excessive road snap'
  assert max(w['distance'] for w in route['waypoints'])<=reviews[rid]['maximumRecordedSnapMeters'],rid+' exceeds historical held bounds'
  held.append(rid)
 else:eligible+=1
 if route.get('geometryUrl'):
  path=ROOT/route['geometryUrl'].split('?')[0];geometry=json.loads(path.read_text());assert geometry['duration']==route['duration'] and geometry['distance']==route['distance']
  assert geometry['originLocation']==origin and geometry['geometry']['type']=='LineString' and len(geometry['geometry']['coordinates'])>=2
  assert all(len(c)==2 and all(math.isfinite(x) for x in c) and -180<=c[0]<=180 and -90<=c[1]<=90 for c in geometry['geometry']['coordinates'])
print(f'PASS: {len(live["records"])} sourced references; {eligible} routes within 500m; historical held: {", ".join(held) or "none"}')
