"""Enrich Changsha POI data to match other cities' quality.

Steps:
1. Ensure all POIs have required fields (source_id, description, etc.)
2. Generate default recommendations for POIs that lack them
3. Prepare data for photo download script
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def enrich_changsha():
    pois_path = DATA_DIR / "changsha" / "pois.json"
    raw_path = OUTPUT_DIR / "amap-changsha" / "pois.json"

    # Load current (filtered) and raw data
    with open(pois_path, "r", encoding="utf-8") as f:
        pois = json.load(f)
    with open(raw_path, "r", encoding="utf-8") as f:
        raw_pois = json.load(f)

    # Build lookup from raw data (has more fields like description)
    raw_by_id = {p["id"]: p for p in raw_pois}
    raw_by_name = {p["name"]: p for p in raw_pois}

    print(f"Changsha: {len(pois)} filtered POIs, {len(raw_pois)} raw POIs")

    # Enrich each POI
    enriched = 0
    for poi in pois:
        pid = poi.get("id", "")
        raw = raw_by_id.get(pid) or raw_by_name.get(poi.get("name", ""))

        if raw:
            # Copy missing fields from raw data
            for field in ["description", "source_id", "source", "open_time", "close_time",
                          "visit_duration_minutes", "popularity", "price_level", "area",
                          "lat", "lng", "tags", "meal_type", "image_url", "images"]:
                if not poi.get(field) and raw.get(field):
                    poi[field] = raw[field]
                    enriched += 1

        # Ensure required defaults
        if not poi.get("description"):
            poi["description"] = f"{poi.get('name', '')}，{poi.get('area', '长沙')}的热门地点。"
        if not poi.get("source_id"):
            poi["source_id"] = pid  # Use existing ID as source_id
        if not poi.get("popularity"):
            poi["popularity"] = 4.0
        if not poi.get("price_level"):
            poi["price_level"] = 1
        if not poi.get("tags"):
            poi["tags"] = []
        if poi.get("type") == "attraction" and "景点" not in poi.get("tags", []):
            poi.setdefault("tags", []).append("景点")

    # Generate placeholder recommendations (will be replaced by LLM later)
    for poi in pois:
        if not poi.get("recommendation"):
            name = poi.get("name", "")
            area = poi.get("area", "长沙")
            ptype = poi.get("type", "attraction")
            if ptype == "attraction":
                poi["recommendation"] = f"{name}是{area}值得一去的景点，建议提前规划好路线，避开节假日高峰。"
            elif ptype == "restaurant":
                poi["recommendation"] = f"{name}是当地口碑不错的餐厅，建议避开用餐高峰期前往。"
            elif ptype == "hotel":
                poi["recommendation"] = f"{name}位于{area}，交通便利，适合作为旅行住宿选择。"
            else:
                poi["recommendation"] = f"{name}位于{area}，值得一去。"

    # Save enriched data
    with open(pois_path, "w", encoding="utf-8") as f:
        json.dump(pois, f, ensure_ascii=False, indent=2)

    # Stats
    has_rec = sum(1 for p in pois if p.get("recommendation"))
    has_desc = sum(1 for p in pois if p.get("description"))
    has_img = sum(1 for p in pois if p.get("image_url"))
    has_sid = sum(1 for p in pois if p.get("source_id"))

    print(f"After enrichment:")
    print(f"  recommendation: {has_rec}/{len(pois)}")
    print(f"  description:    {has_desc}/{len(pois)}")
    print(f"  image_url:      {has_img}/{len(pois)}")
    print(f"  source_id:      {has_sid}/{len(pois)}")
    print(f"  Saved to {pois_path}")


if __name__ == "__main__":
    enrich_changsha()
