#!/usr/bin/env python3
"""Clean non-tourist POIs from attraction lists in all city data files.

Problem: Many POIs classified as "attraction" are actually individual stores,
supermarkets, generic malls, jewelry shops, etc. that shouldn't appear in
tourist itineraries.

Strategy: Multi-rule filtering with whitelist/blacklist approach.
- KEEP: Scenic spots, historical sites, parks, famous commercial streets
- REMOVE: Individual stores, supermarkets, generic malls, banks, pharmacies

Usage:
    python scripts/clean_poi_attractions.py              # Clean all cities
    python scripts/clean_poi_attractions.py beijing      # Clean one city
    python scripts/clean_poi_attractions.py --dry-run    # Preview without writing
    python scripts/clean_poi_attractions.py --dry-run --verbose  # Show details
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path


# ── Tags that indicate a LEGITIMATE tourist attraction (whitelist) ────────────

KEEP_TAGS = {
    "风景名胜", "风景名胜相关", "旅游景点",
    "历史文化", "历史", "世界遗产", "古建筑",
    "博物馆", "科教文化服务", "美术馆", "展览馆",
    "寺庙", "宗教", "教堂", "道观",
    "公园", "公园广场", "植物园", "动物园", "水族馆",
    "自然", "山水", "湖泊", "海滩", "森林", "山脉", "峡谷",
    "温泉", "滑雪场", "游乐场", "主题公园",
    "特色商业街", "步行街",  # Famous tourist shopping streets
    "夜市", "小吃街", "美食街",
    "古镇", "古村", "古城",
    "纪念馆", "故居", "陵墓", "陵园",
    "体育场馆", "体育场",
    "剧院", "音乐厅", "文化宫",
    "天文馆", "科技馆", "海洋馆",
    "观景台", "观光塔", "电视塔",
    "码头", "游船",
    "文艺", "文创",
}

# ── Tags that indicate a NON-tourist POI (blacklist) ─────────────────────────

REMOVE_TAGS = {
    "超级市场", "超市", "便利店",
    "服装鞋帽皮具店", "品牌服装店", "服装鞋帽",
    "体育用品店", "运动用品",
    "珠宝首饰工艺品", "金银首饰", "珠宝",
    "药店", "药房", "医院", "诊所",
    "银行", "ATM", "金融",
    "4S店", "汽车销售", "汽车服务", "加油站",
    "写字楼", "公司企业", "产业园区",
    "普通商场",  # Generic malls (not tourist-worthy)
    "家居建材", "家电", "电器",
    "美容美发", "美甲", "SPA",
    "网吧", "游戏厅", "KTV",
    "洗浴", "足疗", "按摩",
    "房产中介", "律师事务所",
    "停车场", "充电站",
    "宠物店", "花店",
    "干洗店", "裁缝店",
    "眼镜店", "钟表店",
    "手机店", "数码店",
}

# ── Store/brand keywords in POI names (REMOVE) ──────────────────────────────

REMOVE_NAME_PATTERNS = [
    # Clothing brands
    r"海澜之家", r"优衣库", r"ZARA", r"H&M", r"UNIQLO", r"GAP",
    r"耐克", r"阿迪达斯", r"Nike", r"Adidas", r"李宁", r"安踏",
 r"森马", r"以纯", r"美特斯邦威", r"太平鸟", r"ONLY", r"VERO MODA",
    r"杰克琼斯", r"Jack.*Jones", r"GXG", r"CABBEEN", r"马克华菲",
    r"七匹狼", r"九牧王", r"利郎", r"雅戈尔", r"报喜鸟",
    r"ochirly", r"欧时力", r"MO&Co", r"JNBY", r"江南布衣",
    r"UR\b", r"SELECTED", r"MASSIMO DUTTI",
    # Jewelry brands
    r"周大福", r"周六福", r"老凤祥", r"周生生", r"谢瑞麟",
    r"潮宏基", r"通灵", r"IDO", r"卡地亚", r"Cartier",
    r"蒂芙尼", r"Tiffany", r"宝格丽", r"Bvlgari",
    r"潘多拉", r"Pandora", r"施华洛世奇", r"Swarovski",
    # Watch/luxury brands
    r"劳力士", r"Rolex", r"欧米茄", r"Omega", r"浪琴", r"Longines",
    r"万国", r"IWC", r"积家", r"Jaeger", r"百达翡丽",
    r"LV\b", r"路易威登", r"Louis Vuitton", r"古驰", r"Gucci",
    r"香奈儿", r"Chanel", r"迪奥", r"Dior", r"爱马仕", r"Hermes",
    r"普拉达", r"Prada", r"博柏利", r"Burberry",
    # Supermarket chains
    r"红旗超市", r"永辉超市", r"华润万家", r"大润发",
    r"沃尔玛", r"Walmart", r"家乐福", r"Carrefour",
    r"7-?11", r"全家", r"罗森", r"Lawson", r"便利蜂",
    r"盒马", r"叮咚买菜", r"山姆",
    # Drugstore chains
    r"大参林", r"海王星辰", r"老百姓大药房", r"益丰大药房",
    r"一心堂", r"国大药房", r"同仁堂",
    # Electronics/phone stores
    r"华为体验店", r"小米之家", r"苹果体验店", r"Apple Store",
    r"苏宁易购", r"国美电器", r"京东之家",
    # Other individual stores
    r"名创优品", r"MINISO", r"无印良品", r"MUJI",
    r"屈臣氏", r"Watsons", r"丝芙兰", r"Sephora",
    r"星巴克", r"Starbucks", r"瑞幸咖啡", r"luckin",
    r"肯德基", r"KFC", r"麦当劳", r"McDonald",
    r"必胜客", r"Pizza Hut",
    # Banks
    r"工商银行", r"建设银行", r"农业银行", r"中国银行",
    r"招商银行", r"交通银行", r"浦发银行", r"中信银行",
    r"兴业银行", r"民生银行", r"光大银行", r"华夏银行",
    r"邮储银行", r"平安银行",
]

# ── Well-known tourist commercial streets (always KEEP) ──────────────────────

FAMOUS_STREETS = [
    "春熙路", "太古里", "宽窄巷子", "锦里", "南锣鼓巷", "前门大街",
    "王府井", "西单", "三里屯", "后海", "什刹海",
    "南京路", "淮海路", "田子坊", "新天地", "外滩",
    "上下九", "北京路", "天河城",
    "河坊街", "南宋御街", "武林路", "延安路",
    "户部巷", "江汉路", "楚河汉街",
    "回民街", "永兴坊", "大唐不夜城",
    "中山路", "曾厝垵", "鼓浪屿",
    "台东步行街", "劈柴院",
    "中央大街", "索菲亚教堂",
    "四方街", "束河古镇", "丽江古城",
    "阳朔西街",
    "解放碑", "洪崖洞", "磁器口",
    "夫子庙", "老门东", "新街口",
    "平江路", "山塘街", "观前街",
    "东关街",
    "太平老街", "坡子街", "黄兴路步行街",
]

# ── Name branch indicators (suggests individual store) ───────────────────────

BRANCH_INDICATORS = [
    r"店$", r"旗舰店$", r"主力店$", r"概念店$",
    r"\(.*路店\)", r"\(.*街店\)", r"\(.*广场店\)",
    r"\(.*购物中心店\)", r"\(.*商场店\)",
    r"\(.*旗舰店\)", r"\(.*主力店\)",
    r"\(.*地铁.*店\)", r"\(.*站.*店\)",
]


def _has_keep_tag(tags: list[str]) -> bool:
    """Check if POI has any tag that indicates it's a legitimate tourist spot."""
    for tag in tags:
        if tag in KEEP_TAGS:
            return True
    return False


def _has_remove_tag(tags: list[str]) -> bool:
    """Check if POI has any tag that indicates it's non-tourist."""
    for tag in tags:
        if tag in REMOVE_TAGS:
            return True
    return False


def _matches_remove_name(name: str) -> bool:
    """Check if POI name matches any non-tourist store/brand pattern."""
    for pattern in REMOVE_NAME_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    return False


def _is_famous_street(name: str) -> bool:
    """Check if POI is a well-known tourist commercial street."""
    for street in FAMOUS_STREETS:
        if street in name:
            return True
    return False


def _has_branch_indicator(name: str) -> bool:
    """Check if POI name has branch/store indicators."""
    for pattern in BRANCH_INDICATORS:
        if re.search(pattern, name):
            return True
    return False


def should_remove(poi: dict) -> tuple[bool, str]:
    """Decide if a POI should be removed from attractions.
    
    Returns (should_remove, reason).
    """
    name = poi.get("name", "")
    tags = poi.get("tags", [])
    popularity = poi.get("popularity", 0)

    # Rule 0: If it has a strong KEEP tag, always keep
    if _has_keep_tag(tags):
        # Still remove if it's clearly an individual brand store (not a scenic area)
        # Exception: don't remove if name contains tourist area keywords
        if _matches_remove_name(name):
            # Check if it's actually a store or a scenic area named after a brand
            scenic_keywords = ["景区", "景点", "公园", "广场", "古镇", "古村", "古城", "遗址", "故居", "纪念馆"]
            if any(kw in name for kw in scenic_keywords):
                return False, ""
            return True, f"品牌店铺(有保留标签但名称匹配品牌): {name}"
        return False, ""

    # Rule 1: Name matches known store/brand → REMOVE
    if _matches_remove_name(name):
        return True, f"品牌/商店名称匹配: {name}"

    # Rule 2: Has blacklist tags → REMOVE
    if _has_remove_tag(tags):
        return True, f"黑名单标签命中: {[t for t in tags if t in REMOVE_TAGS]}"

    # Rule 3: Name has branch indicators AND no strong tourist tags → REMOVE
    # But be conservative: only remove if combined with other non-tourist signals
    if _has_branch_indicator(name):
        # Exception: hotels, resorts, hot springs are tourist attractions
        tourist_keywords = ["酒店", "宾馆", "民宿", "客栈", "温泉", "度假", "山庄", "庄园"]
        if any(kw in name for kw in tourist_keywords):
            return False, ""
        if not any(
            t in tags for t in ["风景名胜", "历史文化", "世界遗产", "博物馆", "特色商业街", "步行街"]
        ):
            # Only remove if also has non-tourist tags or matches a known store brand
            if _has_remove_tag(tags) or _matches_remove_name(name):
                return True, f"店铺分支标识+非旅游标签: {name}"

    # Rule 4: Has "购物服务" tag, low popularity, no tourist tags → REMOVE
    if "购物服务" in tags and popularity < 4.3:
        tourist_tags = {"风景名胜", "历史文化", "世界遗产", "博物馆", "特色商业街", "步行街", "古镇"}
        if not any(t in tags for t in tourist_tags):
            return True, f"低热度购物POI(pop={popularity}): {name}"

    # Rule 5: Name has "(XX路店)" pattern, likely individual store
    if re.search(r"\(.*路.*店\)", name) or re.search(r"\(.*街.*店\)", name):
        # But keep if it's a famous street
        if not _is_famous_street(name):
            return True, f"分店标识模式: {name}"

    return False, ""


def clean_city(city_dir: str, dry_run: bool = False, verbose: bool = False) -> dict:
    """Clean non-tourist POIs from a city's pois.json. Returns stats."""
    pois_path = os.path.join(city_dir, "pois.json")
    if not os.path.exists(pois_path):
        return {"city": os.path.basename(city_dir), "error": "pois.json not found"}

    with open(pois_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    original_total = len(data)
    original_attractions = sum(1 for p in data if p.get("type") == "attraction")

    removed = []
    kept = []
    for poi in data:
        if poi.get("type") != "attraction":
            kept.append(poi)
            continue
        should_rm, reason = should_remove(poi)
        if should_rm:
            removed.append({"name": poi.get("name"), "reason": reason})
            if verbose:
                print(f"    REMOVE: {reason}")
        else:
            kept.append(poi)

    new_attractions = sum(1 for p in kept if p.get("type") == "attraction")

    if not dry_run and removed:
        # Backup original
        backup_path = pois_path + ".backup"
        if not os.path.exists(backup_path):
            with open(pois_path, "r", encoding="utf-8") as f:
                with open(backup_path, "w", encoding="utf-8") as f2:
                    f2.write(f.read())

        with open(pois_path, "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False, indent=2)

    return {
        "city": os.path.basename(city_dir),
        "original_attractions": original_attractions,
        "removed": len(removed),
        "remaining": new_attractions,
        "removal_rate": f"{len(removed)/original_attractions*100:.1f}%" if original_attractions else "0%",
        "removed_details": removed,
    }


def main():
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    target_city = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and not arg.startswith("-"):
            target_city = arg

    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    if not os.path.isdir(data_dir):
        print(f"ERROR: data directory not found at {data_dir}")
        sys.exit(1)

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

    total_removed = 0
    total_original = 0

    for city_dir in cities:
        result = clean_city(city_dir, dry_run=dry_run, verbose=verbose)
        if "error" in result:
            print(f"  SKIP {result['city']}: {result['error']}")
            continue

        total_removed += result["removed"]
        total_original += result["original_attractions"]

        status = "REMOVED" if not dry_run else "WOULD REMOVE"
        print(f"  {result['city']:15s} | {result['original_attractions']:3d} -> {result['remaining']:3d} "
              f"attractions | {status}: {result['removed']:3d} ({result['removal_rate']})")

        if verbose and result["removed_details"]:
            for d in result["removed_details"][:5]:
                print(f"    - {d['reason']}")
            if len(result["removed_details"]) > 5:
                print(f"    ... and {len(result['removed_details'])-5} more")

    mode = "DRY RUN" if dry_run else "WRITTEN"
    rate = f"{total_removed/total_original*100:.1f}%" if total_original else "0%"
    print(f"\n[{mode}] Total: {total_removed}/{total_original} attractions removed ({rate}) across {len(cities)} cities")


if __name__ == "__main__":
    main()


