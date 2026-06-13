"""Final POI cleanup: apply all quality filters directly to pois.json.

Usage: python scripts/apply_quality_filter.py [--data-dir data]
"""
import argparse
import json
import os

# Import shared filter logic
import sys
sys.path.insert(0, os.path.dirname(__file__))
from poi_filters import filter_attractions, filter_restaurants, filter_hotels, filter_transit


def main():
    parser = argparse.ArgumentParser(description="Apply quality filters to all city POI files")
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "..", "data"),
                        help="Path to data directory (default: ../data relative to this script)")
    args = parser.parse_args()
    data_dir = os.path.abspath(args.data_dir)

    print('%-15s %5s %5s %5s %5s %5s %5s' % ('City','Before','Attr','Rest','Hotel','Transit','After'))
    print('-' * 60)
    total_before = total_after = 0

    for city_dir in sorted(os.listdir(data_dir)):
        poi_path = os.path.join(data_dir, city_dir, 'pois.json')
        if not os.path.isfile(poi_path):
            continue
        with open(poi_path, 'r', encoding='utf-8') as f:
            pois = json.load(f)
        before = len(pois)

        attrs = filter_attractions(pois)
        rests = filter_restaurants(pois)
        hotels = filter_hotels(pois)
        transits = filter_transit(pois)

        cleaned = attrs + rests + hotels + transits

        with open(poi_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)

        total_before += before
        total_after += len(cleaned)
        print('%-15s %5d %5d %5d %5d %5d %5d' % (city_dir, before, len(attrs), len(rests), len(hotels), len(transits), len(cleaned)))

    print('-' * 60)
    print('%-15s %5d %5s %5s %5s %5s %5d' % ('TOTAL', total_before, '', '', '', '', total_after))
    if total_before > 0:
        print('\nRemoved: %d POIs (%.0f%%)' % (total_before - total_after, (total_before - total_after) * 100 / total_before))


if __name__ == '__main__':
    main()
