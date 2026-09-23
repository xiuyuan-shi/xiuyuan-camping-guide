"""Check every published route against its named map reference and geometry."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data = json.loads((root / 'data.json').read_text())
live = json.loads((root / 'live-data.json').read_text())
names = {r['id']: r['name'] for r in data['records']}
origin = live['origin']
assert origin['name'] == '杭州武林门地铁站'
for rid, item in live['records'].items():
    assert rid in names and item['name'] == names[rid]
    location = item['location']
    assert location['sourceUrl'].startswith('https://') and location['precision']
    assert -90 <= location['latitude'] <= 90 and -180 <= location['longitude'] <= 180
    route = item['routeSnapshot']
    assert route['origin'] == origin['name'] and route['originLocation'] == origin
    assert route['destinationLocation']['latitude'] == location['latitude']
    assert route['destinationLocation']['longitude'] == location['longitude']
    assert route['duration'] > 0 and route['distance'] > 0
    assert all(point['distance'] <= 1500 for point in route['waypoints'])
    if route.get('geometryUrl'):
        path = root / route['geometryUrl'].split('?')[0]
        assert path.is_file(), rid
        geometry = json.loads(path.read_text())
        assert geometry['duration'] == route['duration']
        assert geometry['distance'] == route['distance']
        assert geometry['geometry']['type'] == 'LineString'
        assert len(geometry['geometry']['coordinates']) >= 2
print(f'PASS: {len(live["records"])} sourced points and Wulinmen route snapshots')
