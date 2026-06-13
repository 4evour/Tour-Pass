"""Filter transit POIs v2 - only major hubs.

Usage: python scripts/filter_transit.py [--data-dir data]
"""
import argparse
import json
import os
import re

import sys
sys.path.insert(0, os.path.dirname(__file__))
from poi_filters import is_valid_transit, norm_station


def station_importance(name):
    """Higher = more important."""
    n = name
    if '机场' in n and '国际' in n: return 100
    if '机场' in n and '荷花' in n: return 100
    if '机场' in n: return 90
    if re.match(r'^.{2,4}(站)$', n): return 80
    if n.endswith('站'): return 50
    if '客运' in n or '汽车' in n: return 20
    return 10


def main():
    parser = argparse.ArgumentParser(description="Filter transit POIs")
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "..", "data"),
                        help="Path to data directory")
    args = parser.parse_args()
    data_dir = os.path.abspath(args.data_dir)

    results = {}
    for city_dir in sorted(os.listdir(data_dir)):
        poi_path = os.path.join(data_dir, city_dir, 'pois.json')
        if not os.path.isfile(poi_path): continue
        with open(poi_path, 'r', encoding='utf-8') as f:
            pois = json.load(f)
        transits = [p for p in pois if p.get('type') == 'transit']

        filtered = [p for p in transits if is_valid_transit(p['name'])]

        # Deduplicate
        groups = {}
        for p in filtered:
            base = norm_station(p['name'])
            groups.setdefault(base, []).append(p)
        deduped = []
        for base, group in groups.items():
            group.sort(key=lambda p: -p.get('popularity', 0))
            deduped.append(group[0])

        # Sort by importance then popularity
        deduped.sort(key=lambda p: (-station_importance(p['name']), -p.get('popularity', 0)))

        # Keep top N: 2 airports + 5 stations + 3 bus = 10 max
        airports = [p for p in deduped if '机场' in p['name']][:2]
        stations = [p for p in deduped if '站' in p['name'] and '机场' not in p['name'] and '客运' not in p['name'] and '汽车' not in p['name']][:5]
        bus = [p for p in deduped if '客运' in p['name'] or '汽车' in p['name']][:3]
        final = airports + stations + bus

        results[city_dir] = {
            'original': len(transits),
            'filtered': len(final),
            'list': [{'name': p['name'], 'pop': p.get('popularity',0), 'area': p.get('area','')} for p in final],
        }

    print('%-15s %5s %5s' % ('City', 'Orig', 'Final'))
    print('-' * 30)
    to = tf = 0
    for city, r in results.items():
        to += r['original']
        tf += r['filtered']
        print('%-15s %5d %5d' % (city, r['original'], r['filtered']))
    print('-' * 30)
    print('%-15s %5d %5d' % ('TOTAL', to, tf))

    print()
    for city, r in results.items():
        print('=== %s (%d) ===' % (city.upper(), r['filtered']))
        for item in r['list']:
            print('  %-40s %.1f  %s' % (item['name'][:40], item['pop'], item['area']))
        print()


if __name__ == '__main__':
    main()