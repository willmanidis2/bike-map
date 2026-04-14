#!/usr/bin/env python3
"""
Merge email polyline data with Citibike API ride list.
For rides without polylines, use OSRM cycling router to generate routes.
"""

import json
import time
import requests
from datetime import datetime

# Load existing GeoJSON (email-extracted polylines)
with open('/Users/will/citibike/citibike_routes.geojson') as f:
    existing = json.load(f)

# Load all rides from Citibike API
with open('/Users/will/citibike/citibike_all_rides.json') as f:
    all_rides = json.load(f)

# Load Citibike station info for coordinate lookup
print("Fetching station coordinates...")
station_resp = requests.get('https://gbfs.citibikenyc.com/gbfs/en/station_information.json')
stations = station_resp.json()['data']['stations']

# Build station name -> coords lookup (fuzzy matching by name)
station_coords = {}
for s in stations:
    station_coords[s['name']] = (s['lat'], s['lon'])

# Also build normalized lookup (lowercase, stripped)
station_coords_normalized = {}
for name, coords in station_coords.items():
    station_coords_normalized[name.lower().strip()] = coords

def find_station_coords(name):
    if not name:
        return None
    # Direct match
    if name in station_coords:
        return station_coords[name]
    # Normalized
    norm = name.lower().strip()
    if norm in station_coords_normalized:
        return station_coords_normalized[norm]
    # Fuzzy: try removing extra spaces, ampersand variants
    for sname, coords in station_coords.items():
        if sname.lower().replace('&', 'and').replace('  ', ' ').strip() == norm.replace('&', 'and').replace('  ', ' '):
            return coords
    # Partial match
    for sname, coords in station_coords.items():
        if norm in sname.lower() or sname.lower() in norm:
            return coords
    return None

def osrm_route(start_lat, start_lng, end_lat, end_lng):
    """Get cycling route from OSRM."""
    url = f"http://router.project-osrm.org/route/v1/cycling/{start_lng},{start_lat};{end_lng},{end_lat}?geometries=geojson&overview=full"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('code') == 'Ok' and data.get('routes'):
            return data['routes'][0]['geometry']['coordinates']
    except Exception as e:
        print(f"  OSRM error: {e}")
    return None

# Index existing email rides by startTimeMs for matching
existing_by_time = {}
for feat in existing['features']:
    email_date = feat['properties'].get('email_date')
    if email_date:
        # Convert to ms timestamp for matching
        dt = datetime.fromisoformat(email_date.replace('Z', '+00:00'))
        # Use a ±2 hour window since email_date != exact ride time
        existing_by_time[email_date] = feat

# Match rides: for each API ride, find matching email polyline or generate OSRM route
merged_features = []
osrm_count = 0
email_count = 0
skipped = 0

for ride in all_rides:
    start_ms = int(ride['startTimeMs'])
    end_ms = int(ride['endTimeMs'])
    ride_date = datetime.utcfromtimestamp(start_ms / 1000)
    duration_sec = (end_ms - start_ms) / 1000

    start_station = ride.get('startStation', '')
    end_station = ride.get('endStation', '')

    # Try to find matching email polyline by matching station names + close time
    matched_feat = None
    for feat in existing['features']:
        fp = feat['properties']
        # Match by station names (both directions match)
        if fp.get('start_station') == start_station and fp.get('end_station') == end_station:
            # Check time proximity (within 2 days - email dates may not match exactly)
            email_dt = fp.get('email_date', '')
            if email_dt:
                email_ts = datetime.fromisoformat(email_dt.replace('Z', '+00:00')).timestamp() * 1000
                if abs(email_ts - start_ms) < 48 * 3600 * 1000:  # within 2 days
                    matched_feat = feat
                    break

    if matched_feat:
        # Use the email polyline coordinates
        coords = matched_feat['geometry']['coordinates']
        source = 'email_polyline'
        email_count += 1
    else:
        # Generate route via OSRM
        start_coords = find_station_coords(start_station)
        end_coords = find_station_coords(end_station)

        if start_coords and end_coords:
            coords = osrm_route(start_coords[0], start_coords[1], end_coords[0], end_coords[1])
            if coords:
                source = 'osrm'
                osrm_count += 1
            else:
                # Fallback: straight line
                coords = [[start_coords[1], start_coords[0]], [end_coords[1], end_coords[0]]]
                source = 'straight_line'
                osrm_count += 1
        else:
            print(f"  Skipping ride {ride_date.strftime('%Y-%m-%d %H:%M')} - can't find stations: {start_station} -> {end_station}")
            skipped += 1
            continue

    # Build feature
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coords
        },
        "properties": {
            "date": ride_date.strftime('%B %d, %Y at %I:%M %p').upper(),
            "email_date": ride_date.isoformat() + 'Z',
            "start_station": start_station,
            "end_station": end_station,
            "start_time": ride_date.strftime('%-I:%M %p').lower(),
            "end_time": datetime.utcfromtimestamp(end_ms / 1000).strftime('%-I:%M %p').lower(),
            "duration_min": round(duration_sec / 60, 1),
            "price": ride.get('price', ''),
            "bike": ride.get('bikeName', ''),
            "point_count": len(coords),
            "source": source
        }
    }
    merged_features.append(feature)

    # Rate limit OSRM calls
    if source == 'osrm':
        time.sleep(0.5)

    if len(merged_features) % 50 == 0:
        print(f"  Processed {len(merged_features)} rides...")

# Sort by date
merged_features.sort(key=lambda f: f['properties']['email_date'])

# Assign ride numbers
for i, f in enumerate(merged_features):
    f['properties']['ride_number'] = i + 1

# Build final GeoJSON
final = {
    "type": "FeatureCollection",
    "features": merged_features
}

# Save
output_path = '/Users/will/citibike/citibike_routes.geojson'
with open(output_path, 'w') as f:
    json.dump(final, f)

print(f"\nDone!")
print(f"  Total rides: {len(merged_features)}")
print(f"  From email polylines: {email_count}")
print(f"  From OSRM routing: {osrm_count}")
print(f"  Skipped (no station match): {skipped}")
print(f"  Saved to {output_path}")
