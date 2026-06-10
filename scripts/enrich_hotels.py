#!/usr/bin/env python3
"""Enrich hotel data with brand category, price range, and star rating.

Reads each city's pois.json, identifies hotels, and enriches them with:
- brand_category: 经济型/中端/高端/豪华 (based on brand keywords)
- price_range: estimated nightly price range (e.g., "200-400元/晚")
- star_rating: inferred star rating (2-5)
- price_level: recalibrated 1-5 scale

Usage:
    python scripts/enrich_hotels.py              # Enrich all cities
    python scripts/enrich_hotels.py beijing      # Enrich one city
    python scripts/enrich_hotels.py --dry-run    # Preview without writing
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

# ── Brand knowledge base ──────────────────────────────────────────────────────
# Maps brand keywords to (brand_category, price_range, star_rating, price_level)
# Price ranges are typical China market rates per night in CNY (2024-2026)

BRAND_TABLE: list[tuple[list[str], str, str, int, int]] = [
    # (keywords, category, price_range, star_rating, price_level)

    # === 豪华型 (Luxury) ===
    (["丽思卡尔顿", "瑞吉", "华尔道夫", "安缦", "半岛", "宝格丽", "瑰丽",
      "四季", "文华东方", "柏悦", "安麓", "嘉里"],
     "豪华", "1200-3000元/晚", 5, 5),

    (["万豪", "希尔顿", "洲际", "凯悦", "香格里拉", "威斯汀", "艾美",
      "索菲特", "铂尔曼", "喜来登", "凯宾斯基", "君悦", "悦榕庄",
      "JW万豪", "康莱德", "W酒店"],
     "高端", "600-1500元/晚", 5, 4),

    # === 高端型 (Upper-upscale) ===
    (["万丽", "希尔顿逸林", "华邑", "凯悦嘉轩", "凯悦尚萃", "诺富特",
      "美憬阁", "英迪格", "傲途格", "德尔塔", "嘉悦里"],
     "高端", "500-1000元/晚", 4, 4),

    # === 中端型 (Upscale/Midscale) ===
    (["亚朵", "全季", "桔子水晶", "美居", "维也纳国际", "锦江都城",
      "麓枫", "丽柏", "城际", "开元名都", "君亭", "书香府邸",
      "花间堂", "松赞", "安仕"],
     "中端", "300-600元/晚", 4, 3),

    (["维也纳", "锦江之星", "汉庭优佳", "如家精选", "如家商旅",
      "7天优品", "星程", "格林豪泰精选", "都市花园", "都市118精选",
      "尚客优品", "希岸", "潮漫", "IU", "ZMAX", "非繁城品"],
     "中端", "250-450元/晚", 3, 3),

    # === 经济型 (Economy) ===
    (["如家", "汉庭", "7天", "锦江之星", "格林豪泰", "城市便捷",
      "速8", "布丁", "海友", "百时快捷", "易佰", "99优选",
      "贝壳", "尚客优", "都市118", "驿家365", "怡莱",
      "青年旅舍", "青旅", "yha", "hostel"],
     "经济型", "100-250元/晚", 2, 1),

    # === 民宿/特色 ===
    (["民宿", "客栈", "公寓", "别墅", "小院", "驿站", "山庄",
      "度假村", "农家乐"],
     "特色", "150-800元/晚", 0, 2),
]

# ── Area-based price adjustment factors ───────────────────────────────────────
# Core/prime areas get a price premium
AREA_PREMIUM_KEYWORDS = [
    "市中心", "天安门", "故宫", "外滩", "陆家嘴", "西湖", "天府广场",
    "春熙路", "解放碑", "夫子庙", "中山陵", "鼓楼", "新街口",
    "王府井", "国贸", "三里屯", "朝阳", "黄浦", "静安",
]


def _infer_from_name(name: str) -> tuple[str, str, int, int]:
    """Infer hotel attributes from its name using brand table.
    
    Returns (brand_category, price_range, star_rating, price_level).
    Falls back to ("", "", 0, 1) if no brand match.
    """
    name_lower = name.lower()
    for keywords, category, price_range, star_rating, price_level in BRAND_TABLE:
        for kw in keywords:
            if kw.lower() in name_lower or kw in name:
                return category, price_range, star_rating, price_level

    # Heuristic: check for star rating in name
    star_match = re.search(r'(\d)星', name)
    if star_match:
        stars = int(star_match.group(1))
        if stars >= 5:
            return "高端", "600-1500元/晚", 5, 4
        elif stars >= 4:
            return "中端", "300-600元/晚", 4, 3
        elif stars >= 3:
            return "中端", "200-400元/晚", 3, 2
        else:
            return "经济型", "100-250元/晚", 2, 1

    return "", "", 0, 1


def _area_price_adjustment(area: str, price_range: str) -> str:
    """Adjust price range upward if hotel is in a premium area."""
    if not price_range:
        return price_range
    is_premium = any(kw in area for kw in AREA_PREMIUM_KEYWORDS)
    if not is_premium:
        return price_range

    nums = re.findall(r'\d+', price_range)
    if len(nums) >= 2:
        lo = int(int(nums[0]) * 1.2)
        hi = int(int(nums[1]) * 1.3)
        return f"{lo}-{hi}元/晚"
    return price_range


def enrich_hotel(item: dict) -> dict:
    """Enrich a single hotel item with inferred attributes. Returns modified item."""
    name = item.get("name", "")
    area = item.get("area", "")

    cat, price_range, stars, level = _infer_from_name(name)

    if cat:
        item["brand_category"] = cat
        item["price_range"] = _area_price_adjustment(area, price_range)
        item["star_rating"] = stars
        item["price_level"] = level
    else:
        # No brand match — use existing price_level to set category
        existing_level = item.get("price_level", 1)
        if existing_level <= 1:
            item.setdefault("brand_category", "经济型")
            item.setdefault("price_range", "100-250元/晚")
            item.setdefault("star_rating", 2)
        elif existing_level <= 2:
            item.setdefault("brand_category", "中端")
            item.setdefault("price_range", "200-400元/晚")
            item.setdefault("star_rating", 3)
        else:
            item.setdefault("brand_category", "中端")
            item.setdefault("price_range", "300-600元/晚")
            item.setdefault("star_rating", 4)

    return item


def enrich_city(city_dir: str, dry_run: bool = False) -> dict:
    """Enrich all hotels in a city's pois.json. Returns stats."""
    pois_path = os.path.join(city_dir, "pois.json")
    if not os.path.exists(pois_path):
        return {"city": city_dir, "error": "pois.json not found"}

    with open(pois_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    hotel_count = 0
    enriched_count = 0
    category_counts: dict[str, int] = {}

    for item in data:
        if item.get("type") != "hotel":
            continue
        hotel_count += 1
        old_level = item.get("price_level", 1)
        enrich_hotel(item)
        cat = item.get("brand_category", "")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if item.get("price_level", 1) != old_level or cat:
            enriched_count += 1

    if not dry_run:
        # Backup original
        backup_path = pois_path + ".backup"
        if not os.path.exists(backup_path):
            with open(pois_path, "r", encoding="utf-8") as f:
                backup_data = f.read()
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(backup_data)

        with open(pois_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "city": os.path.basename(city_dir),
        "hotels": hotel_count,
        "enriched": enriched_count,
        "categories": category_counts,
    }


def main():
    dry_run = "--dry-run" in sys.argv
    target_city = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            target_city = arg

    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    if not os.path.isdir(data_dir):
        print(f"ERROR: data directory not found at {data_dir}")
        sys.exit(1)

    total_hotels = 0
    total_enriched = 0

    if target_city:
        city_dir = os.path.join(data_dir, target_city)
        if not os.path.isdir(city_dir):
            print(f"ERROR: city directory not found: {city_dir}")
            sys.exit(1)
        cities = [city_dir]
    else:
        cities = sorted([
            os.path.join(data_dir, d)
            for d in os.listdir(data_dir)
            if os.path.isdir(os.path.join(data_dir, d))
        ])

    for city_dir in cities:
        result = enrich_city(city_dir, dry_run=dry_run)
        if "error" in result:
            print(f"  SKIP {result['city']}: {result['error']}")
            continue

        total_hotels += result["hotels"]
        total_enriched += result["enriched"]

        cats = result.get("categories", {})
        cat_str = ", ".join(f"{k}:{v}" for k, v in sorted(cats.items()) if k)
        print(f"  {result['city']:15s} | {result['hotels']:3d} hotels | "
              f"enriched: {result['enriched']:3d} | {cat_str}")

    mode = "DRY RUN" if dry_run else "WRITTEN"
    print(f"\n[{mode}] Total: {total_hotels} hotels, {total_enriched} enriched across {len(cities)} cities")


if __name__ == "__main__":
    main()
