"""Restore Changsha POI data from output/ and fix all cities' dangling edge references.

Two fixes:
1. Copy output/amap-changsha/{pois,edges}.json → data/changsha/
   (Changsha was the original city but pois.json was never committed to git)
2. For ALL cities: remove edges that reference POI IDs no longer in pois.json
   (caused by POI quality filter removing 33% of POIs without updating edges)
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")


def restore_changsha():
    """Copy raw Changsha data from output/ to data/ and apply quality filter.
    
    Only restores if pois.json doesn't exist or has no recommendations
    (to avoid overwriting enriched data).
    """
    src_pois = os.path.join(OUTPUT_DIR, "amap-changsha", "pois.json")
    src_edges = os.path.join(OUTPUT_DIR, "amap-changsha", "edges.json")
    dst_dir = os.path.join(DATA_DIR, "changsha")
    dst_pois = os.path.join(dst_dir, "pois.json")
    dst_edges = os.path.join(dst_dir, "edges.json")

    if not os.path.exists(src_pois):
        print("ERROR: output/amap-changsha/pois.json not found")
        return False

    dst_dir = os.path.join(DATA_DIR, "changsha")
    dst_pois = os.path.join(dst_dir, "pois.json")

    # Skip if pois.json already exists and has enriched data
    if os.path.exists(dst_pois):
        existing = json.load(open(dst_pois, "r", encoding="utf-8"))
        has_rec = sum(1 for p in existing if p.get("recommendation"))
        if has_rec > len(existing) * 0.5:
            print(f"Changsha pois.json already enriched ({has_rec}/{len(existing)} with recommendations), skipping restore")
            return True

    # Load raw POIs
    with open(src_pois, "r", encoding="utf-8") as f:
        raw_pois = json.load(f)
    print(f"Changsha raw POIs: {len(raw_pois)}")

    # Apply quality filter if available
    try:
        from poi_filters import filter_attractions, filter_restaurants, filter_hotels, filter_transit
        attrs = filter_attractions(raw_pois)
        rests = filter_restaurants(raw_pois)
        hotels = filter_hotels(raw_pois)
        transits = filter_transit(raw_pois)
        cleaned = attrs + rests + hotels + transits
        print(f"  After filter: {len(cleaned)} "
              f"(attr={len(attrs)}, rest={len(rests)}, hotel={len(hotels)}, transit={len(transits)})")
    except ImportError:
        print("  poi_filters not available, using raw data")
        cleaned = raw_pois

    # Write pois.json
    with open(dst_pois, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    print(f"  Written: {dst_pois}")

    # Copy edges.json
    if os.path.exists(src_edges):
        shutil.copy2(src_edges, dst_edges)
        print(f"  Copied: {dst_edges}")

    # Create backup
    backup = dst_pois + ".backup"
    with open(backup, "w", encoding="utf-8") as f:
        json.dump(raw_pois, f, ensure_ascii=False, indent=2)
    print(f"  Backup: {backup} ({len(raw_pois)} raw POIs)")

    return True


def fix_dangling_edges():
    """For all cities, remove edges that reference non-existent POI IDs."""
    print("\n=== Fixing dangling edge references ===")
    print(f"{'City':<18} {'POIs':>6} {'Edges Before':>13} {'Removed':>8} {'Edges After':>12}")
    print("-" * 62)

    total_removed = 0
    total_cities_fixed = 0

    for city_name in sorted(os.listdir(DATA_DIR)):
        city_dir = os.path.join(DATA_DIR, city_name)
        if not os.path.isdir(city_dir):
            continue

        pois_path = os.path.join(city_dir, "pois.json")
        edges_path = os.path.join(city_dir, "edges.json")

        if not os.path.exists(pois_path) or not os.path.exists(edges_path):
            continue

        # Load POI IDs
        with open(pois_path, "r", encoding="utf-8") as f:
            pois = json.load(f)
        poi_ids = {p["id"] for p in pois}

        # Load and filter edges
        with open(edges_path, "r", encoding="utf-8") as f:
            edges = json.load(f)

        before = len(edges)
        valid_edges = [
            e for e in edges
            if e.get("from", "") in poi_ids and e.get("to", "") in poi_ids
        ]
        removed = before - len(valid_edges)

        if removed > 0:
            with open(edges_path, "w", encoding="utf-8") as f:
                json.dump(valid_edges, f, ensure_ascii=False, indent=2)
            total_removed += removed
            total_cities_fixed += 1

        print(f"{city_name:<18} {len(pois):>6} {before:>13} {removed:>8} {len(valid_edges):>12}")

    print("-" * 62)
    print(f"Fixed {total_cities_fixed} cities, removed {total_removed} dangling edges total")
    return total_removed


if __name__ == "__main__":
    print("=== Restoring Changsha POI data ===")
    ok = restore_changsha()
    if not ok:
        print("Changsha restore failed!")

    fix_dangling_edges()
    print("\nDone! You should now restart the C++ backend to pick up the changes.")
