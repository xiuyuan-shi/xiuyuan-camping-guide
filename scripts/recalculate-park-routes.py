#!/usr/bin/env python3
"""One-time, auditable route snapshots to exact-name OSM park areas.

These are park reference points, never asserted to be camping pitches or gates.
The local basemap is the coordinate source. OSRM is queried once per new point.
"""
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / 'data.json').read_text())
live_path = ROOT / 'live-data.json'
live = json.loads(live_path.read_text())
features = json.loads((ROOT / 'basemap.geojson').read_text())['features']
parks = {}
for feature in features:
    prop = feature['properties']
    if prop.get('kind') == 'park' and prop.get('name'):
        parks.setdefault(prop['name'], []).append(feature)

origin = live['origin']
results = []
for record in data['records']:
    if record['scope'] != 'hangzhou' or record['id'] in live['records']:
        continue
    matches = parks.get(record['name'], [])
    if len(matches) != 1:
        continue
    feature = matches[0]
    if feature['geometry']['type'] != 'Polygon':
        continue
    ring = feature['geometry']['coordinates'][0]
    lon = round((min(x[0] for x in ring) + max(x[0] for x in ring)) / 2, 7)
    lat = round((min(x[1] for x in ring) + max(x[1] for x in ring)) / 2, 7)
    source_url = 'https://www.openstreetmap.org/' + feature['properties']['osm']
    location = {'latitude': lat, 'longitude': lon, 'crs': 'WGS84',
                'precision': '同名公园范围参考点，非营位或入口',
                'source': 'OpenStreetMap local basemap', 'sourceUrl': source_url,
                'checkedAt': dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
                'osmName': feature['properties']['name']}
    url = f'https://router.project-osrm.org/route/v1/driving/{origin["longitude"]},{origin["latitude"]};{lon},{lat}?overview=full&geometries=geojson&steps=false'
    try:
        response = subprocess.run(['curl', '-fsSL', '--max-time', '25', url], capture_output=True, text=True, check=True)
        payload = json.loads(response.stdout)
        if payload.get('code') != 'Ok' or not payload.get('routes'):
            raise ValueError('OSRM returned no route')
        if any(w['distance'] > 500 for w in payload['waypoints']):
            raise ValueError('road snap exceeds 500m')
        route = payload['routes'][0]
        route_file = ROOT / 'routes' / f'{record["id"]}.json'
        route_file.write_text(json.dumps({'duration': route['duration'],
            'distance': route['distance'], 'geometry': route['geometry'],
            'originLocation': origin}, ensure_ascii=False, separators=(',', ':')) + '\n')
        snapshot = {'duration': route['duration'], 'distance': route['distance'],
                    'geometryUrl': f'routes/{record["id"]}.json?v=wulinmen-20260923',
                    'waypoints': payload['waypoints'],
                    'queriedAt': location['checkedAt'], 'sourceUrl': 'https://project-osrm.org/',
                    'requestUrl': url, 'origin': origin['name'], 'originLocation': origin,
                    'destinationLocation': location, 'isSnapshot': True}
        live['records'][record['id']] = {'name': record['name'], 'location': location,
                                       'images': [], 'routeSnapshot': snapshot}
        results.append((record['id'], record['name'], round(snapshot['duration'] / 60)))
        print('ROUTED', *results[-1], flush=True)
    except (subprocess.CalledProcessError, ValueError, KeyError, json.JSONDecodeError) as error:
        print('SKIP', record['id'], record['name'], str(error), flush=True)
    time.sleep(1)

live['updatedAt'] = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
live_path.write_text(json.dumps(live, ensure_ascii=False, indent=2) + '\n')
print('ADDED', len(results), 'TOTAL', len(live['records']), flush=True)
