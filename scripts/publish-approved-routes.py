#!/usr/bin/env python3
"""Publish only reviewed public map points and cached Wulinmen driving routes.

Each point is a named place reference unless its source proves an actual camp
entrance. A place name alone never establishes permission to camp there.
"""
import datetime as dt
import json
import math
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
approvals = json.loads((ROOT/'imports/2026-09-23/place-approvals.json').read_text())
osm = {(e['type'], e['id']): e for e in
       json.loads((ROOT/'imports/2026-09-23/osm-exact-search.json').read_text())['elements']}
geocoded = json.loads((ROOT/'imports/2026-09-23/public-place-search.json').read_text())
data = json.loads((ROOT/'data.json').read_text())
records = {r['id']: r for r in data['records']}
live_path = ROOT/'live-data.json'
live = json.loads(live_path.read_text())
origin = live['origin']
now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
report = []

def gcj_to_wgs(lat, lon):
    """Iteratively invert the GCJ-02 offset for an AMap-provided point."""
    def wgs_to_gcj(y, x):
        a, ee = 6378245.0, 0.00669342162296594323
        dx, dy = x-105.0, y-35.0
        dlat = (-100.0+2.0*dx+3.0*dy+0.2*dy*dy+0.1*dx*dy
                +0.2*math.sqrt(abs(dx)))
        dlat += ((20.0*math.sin(6.0*dx*math.pi)
                  +20.0*math.sin(2.0*dx*math.pi))*2.0/3.0)
        dlat += ((20.0*math.sin(dy*math.pi)
                  +40.0*math.sin(dy/3.0*math.pi))*2.0/3.0)
        dlat += ((160.0*math.sin(dy/12.0*math.pi)
                  +320*math.sin(dy*math.pi/30.0))*2.0/3.0)
        dlon = (300.0+dx+2.0*dy+0.1*dx*dx+0.1*dx*dy
                +0.1*math.sqrt(abs(dx)))
        dlon += ((20.0*math.sin(6.0*dx*math.pi)
                  +20.0*math.sin(2.0*dx*math.pi))*2.0/3.0)
        dlon += ((20.0*math.sin(dx*math.pi)
                  +40.0*math.sin(dx/3.0*math.pi))*2.0/3.0)
        dlon += ((150.0*math.sin(dx/12.0*math.pi)
                  +300.0*math.sin(dx/30.0*math.pi))*2.0/3.0)
        rad = y/180.0*math.pi
        magic = 1-ee*math.sin(rad)**2
        root = math.sqrt(magic)
        return (y+(dlat*180.0)/((a*(1-ee))/(magic*root)*math.pi),
                x+(dlon*180.0)/(a/root*math.cos(rad)*math.pi))
    y, x = lat, lon
    for _ in range(8):
        gy, gx = wgs_to_gcj(y, x)
        y += lat-gy
        x += lon-gx
    return round(y, 7), round(x, 7)

for rid, decision in approvals.items():
    if rid in live['records']:
        report.append({'id': rid, 'status': 'already-published'})
        continue
    record = records[rid]
    if decision['source'] == 'OpenStreetMap':
        element = osm[(decision['type'], decision['osmId'])]
        if element['tags'].get('name') != decision['matchedName']:
            raise ValueError(f'{rid} OSM name mismatch')
        point = element.get('center', element)
        lat, lon = point['lat'], point['lon']
        source_url = f'https://www.openstreetmap.org/{decision["type"]}/{decision["osmId"]}'
    elif decision['source'] == 'OpenStreetMap Nominatim':
        result = geocoded[rid]['results'][decision['resultIndex']]
        if result.get('name') != decision['matchedName'] or '杭州市' not in result['display_name']:
            raise ValueError(f'{rid} geocoding name or city mismatch')
        lat, lon = float(result['lat']), float(result['lon'])
        source_url = f'https://www.openstreetmap.org/{result["osm_type"]}/{result["osm_id"]}'
    elif decision['source'] == 'Amap':
        lat, lon = gcj_to_wgs(decision['latitude'], decision['longitude'])
        source_url = decision['sourceUrl']
    else:
        raise ValueError(f'{rid}: unsupported source')
    location = {'latitude': lat, 'longitude': lon, 'crs': 'WGS84',
                'precision': decision['precision'], 'travelLabel': decision['travelLabel'],
                'pointKind': decision['pointKind'],
                'source': decision['source'], 'sourceUrl': source_url,
                'checkedAt': now, 'matchedName': decision['matchedName']}
    route_url = (f'https://router.project-osrm.org/route/v1/driving/'
                 f'{origin["longitude"]},{origin["latitude"]};{lon},{lat}'
                 '?overview=full&geometries=geojson&steps=false')
    proc = subprocess.run(['curl', '-fsSL', '--max-time', '30', route_url],
                          capture_output=True, text=True)
    try:
        if proc.returncode:
            raise ValueError(proc.stderr[-150:])
        payload = json.loads(proc.stdout)
        if payload.get('code') != 'Ok' or not payload.get('routes'):
            raise ValueError('OSRM did not find a route')
        if any(w['distance'] > 500 for w in payload['waypoints']):
            raise ValueError('road snap exceeds 500m')
        route = payload['routes'][0]
        route_file = ROOT/'routes'/f'{rid}.json'
        route_file.write_text(json.dumps({
            'duration': route['duration'], 'distance': route['distance'],
            'geometry': route['geometry'], 'originLocation': origin
        }, ensure_ascii=False, separators=(',', ':')) + '\n')
        snapshot = {'duration': route['duration'], 'distance': route['distance'],
                    'geometryUrl': f'routes/{rid}.json?v=wulinmen-20260923b',
                    'waypoints': payload['waypoints'], 'queriedAt': now,
                    'sourceUrl': 'https://project-osrm.org/', 'requestUrl': route_url,
                    'origin': origin['name'], 'originLocation': origin,
                    'destinationLocation': location, 'isSnapshot': True}
        live['records'][rid] = {'name': record['name'], 'location': location,
                                'images': [], 'routeSnapshot': snapshot}
        report.append({'id': rid, 'name': record['name'], 'status': 'published',
                       'minutes': round(route['duration']/60),
                       'roadSnapMeters': round(payload['waypoints'][-1]['distance'])})
        print('ROUTED', rid, record['name'],
              round(route['duration']/60), 'min', flush=True)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        report.append({'id': rid, 'name': record['name'],
                       'status': 'not-routed', 'reason': str(exc)})
        print('SKIP', rid, record['name'], str(exc), flush=True)
    time.sleep(0.5)
live['updatedAt'] = now
live_path.write_text(json.dumps(live, ensure_ascii=False, indent=2) + '\n')
(ROOT/'imports/2026-09-23/route-publication-report.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print('ADDED', sum(x['status']=='published' for x in report),
      'TOTAL', len(live['records']), flush=True)
