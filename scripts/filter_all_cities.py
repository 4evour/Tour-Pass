"""Filter POIs v4 - no popularity threshold.

Usage: python scripts/filter_all_cities.py [--data-dir data]
"""
import argparse
import json
import os

import sys
sys.path.insert(0, os.path.dirname(__file__))
from poi_filters import filter_attractions, filter_restaurants


def main():
    parser = argparse.ArgumentParser(description="Filter POIs for all cities")
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "..", "data"),
                        help="Path to data directory")
    args = parser.parse_args()
    data_dir = os.path.abspath(args.data_dir)

    results = {}
    for city_dir in sorted(os.listdir(data_dir)):
        poi_path = os.path.join(data_dir, city_dir, 'pois.json')
        if not os.path.isfile(poi_path):
            continue
        with open(poi_path, 'r', encoding='utf-8') as f:
            pois = json.load(f)
        attrs = filter_attractions(pois)
        rests = filter_restaurants(pois)
        results[city_dir] = {
            'total': len(pois),
            'attractions': len(attrs),
            'restaurants': len(rests),
            'attr_list': [p['name'] for p in attrs],
            'rest_list': [p['name'] for p in rests],
        }

    print('%-15s %5s %5s %5s %5s' % ('City', 'Total', 'Attr', 'Rest', 'Final'))
    print('-' * 45)
    ta = tr = 0
    for city, r in results.items():
        f = r['attractions'] + r['restaurants']
        ta += r['attractions']
        tr += r['restaurants']
        print('%-15s %5d %5d %5d %5d' % (city, r['total'], r['attractions'], r['restaurants'], f))
    print('-' * 45)
    print('%-15s %5s %5d %5d %5d' % ('TOTAL', '', ta, tr, ta + tr))

    output_dir = os.path.join(os.path.dirname(data_dir), 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'all_cities_filtered_v4.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print('\nSaved to ' + output_path)


if __name__ == '__main__':
    main()
