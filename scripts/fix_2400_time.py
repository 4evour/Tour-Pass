"""Find and fix '24:00' / '24:xx' time values in all city POI data."""
import json
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

def find_and_fix(dry_run=False):
    total_fixed = 0
    for city in sorted(os.listdir(DATA_DIR)):
        city_dir = os.path.join(DATA_DIR, city)
        if not os.path.isdir(city_dir):
            continue
        pois_path = os.path.join(city_dir, "pois.json")
        if not os.path.isfile(pois_path):
            continue

        with open(pois_path, "r", encoding="utf-8") as f:
            pois = json.load(f)

        changed = False
        for poi in pois:
            for field in ["open_time", "close_time"]:
                val = poi.get(field, "")
                if val and isinstance(val, str) and val.startswith("24:"):
                    # 24:00 → 23:59, 24:30 → 23:59, etc.
                    new_val = "23:59"
                    if not dry_run:
                        poi[field] = new_val
                    print(f"  {city}/{poi.get('id', '?')}: {field} '{val}' -> '{new_val}'  ({poi.get('name', '?')})")
                    changed = True
                    total_fixed += 1

        if changed and not dry_run:
            with open(pois_path, "w", encoding="utf-8") as f:
                json.dump(pois, f, ensure_ascii=False, indent=2)
            print(f"  Saved {pois_path}")

    print(f"\nTotal {'found' if dry_run else 'fixed'}: {total_fixed}")
    return total_fixed


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN (no changes) ===")
    else:
        print("=== Fixing 24:xx time values ===")
    find_and_fix(dry_run=dry_run)
