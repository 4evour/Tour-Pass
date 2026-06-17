#!/usr/bin/env python3
"""
Extract structured travel routes from XHS note data.

Processes raw XHS notes (from crawl_xhs_guides.json or crawl output)
and uses LLM to extract structured day-by-day itineraries.

Output: data/{city}/xhs_routes.json

Usage:
  python scripts/extract_routes.py --city guangzhou
  python scripts/extract_routes.py --city guangzhou --input data/guangzhou/xhs_guides.json
  python scripts/extract_routes.py --all
  python scripts/extract_routes.py --city guangzhou --reextract   (re-process existing routes)
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

ALL_CITIES = [
    "beijing", "changsha", "chengdu", "chongqing", "dali", "guangzhou", "guilin",
    "hangzhou", "harbin", "kunming", "lijiang", "nanjing", "qingdao", "sanya",
    "shanghai", "shenzhen", "suzhou", "wuhan", "xiamen", "xian", "zhangjiajie",
]

CITY_NAMES = {
    "beijing": "北京", "changsha": "长沙", "chengdu": "成都", "chongqing": "重庆",
    "dali": "大理", "guangzhou": "广州", "guilin": "桂林", "hangzhou": "杭州",
    "harbin": "哈尔滨", "kunming": "昆明", "lijiang": "丽江", "nanjing": "南京",
    "qingdao": "青岛", "sanya": "三亚", "shanghai": "上海", "shenzhen": "深圳",
    "suzhou": "苏州", "wuhan": "武汉", "xiamen": "厦门", "xian": "西安",
    "zhangjiajie": "张家界",
}


def load_llm_config():
    cfg_path = ROOT / "config" / "llm.local.json"
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    return {
        "api_key": cfg.get("api_key") or cfg.get("apiKey") or os.environ.get("DEEPSEEK_API_KEY", ""),
        "base_url": (cfg.get("base_url") or cfg.get("baseUrl") or os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")).rstrip("/"),
        "model": cfg.get("model") or os.environ.get("LLM_MODEL", "deepseek-chat"),
    }


ROUTE_EXTRACT_PROMPT = """你是旅游路线分析专家。从小红书笔记中提取完整的旅游行程路线。

返回 JSON 对象，格式如下：
{
  "days": 2,
  "travel_style": "休闲/穷游/亲子/情侣/闺蜜/独自旅行",
  "season": "春秋/夏/冬/全年/未提及",
  "budget_hint": "经济/中等/高端/未提及",
  "itinerary": [
    {
      "day": 1,
      "label": "第一天",
      "stops": [
        {
          "time_hint": "上午/中午/下午/傍晚/晚上",
          "name": "景点或地点名称",
          "duration_hint": "2小时/半天/1小时/未提及",
          "activity": "简短活动描述",
          "transport_to_next": "步行/地铁/打车/公交/未提及"
        }
      ]
    }
  ],
  "route_summary": "一句话概括这条路线的核心逻辑",
  "tags": ["关键词标签"]
}

规则：
- 只提取文中明确提到的地点，不编造
- 地点名称保持原文用法
- 如果文中没有明确分天，按时间顺序排列为一天
- stops 的顺序就是游览顺序
- 如果内容不包含完整路线信息（只是单个景点介绍），返回 null
- 只返回 JSON，不要其他文字"""


def call_llm(llm_cfg, system_prompt, user_prompt):
    """Call LLM API and return parsed response."""
    url = llm_cfg["base_url"] + "/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {llm_cfg['api_key']}",
    }
    body = {
        "model": llm_cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 3000,
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        # Extract JSON from response
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            route = json.loads(m.group())
            if route and route.get("itinerary") and len(route["itinerary"]) > 0:
                return route
        return None
    except Exception as e:
        log.warning(f"LLM error: {e}")
        return None


def is_route_content(title, desc):
    """Quick heuristic: does this note likely contain a route/itinerary?"""
    route_keywords = [
        "路线", "行程", "攻略", "一日游", "二日游", "三日游", "四日", "五日",
        "两天", "三天", "四天", "五天", "天游", "天夜", "保姆", "干货",
        "合集", "必去", "打卡", "推荐", "安排", "怎么玩", "游玩",
    ]
    text = title + desc
    return any(kw in text for kw in route_keywords)


def load_notes(city, input_file=None):
    """Load XHS notes from various sources."""
    notes = []

    if input_file:
        p = Path(input_file)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                notes = data
            log.info(f"Loaded {len(notes)} notes from {input_file}")
        return notes

    # Try multiple sources in priority order
    city_dir = DATA_DIR / city

    # 1. xhs_guides.json (from crawl_xhs_guides.js)
    guides_path = city_dir / "xhs_guides.json"
    if guides_path.exists():
        data = json.loads(guides_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            notes.extend(data)
            log.info(f"Loaded {len(data)} notes from xhs_guides.json")

    # 2. xhs_clean.json (if exists)
    clean_path = city_dir / "xhs_clean.json"
    if clean_path.exists():
        data = json.loads(clean_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            notes.extend(data)
            log.info(f"Loaded {len(data)} notes from xhs_clean.json")

    return notes


def extract_routes_from_notes(city, notes, llm_cfg, reextract=False):
    """Extract structured routes from notes using LLM."""
    city_name = CITY_NAMES.get(city, city)
    routes = []
    skipped = 0
    processed = 0

    # Load existing routes to avoid re-processing
    existing_ids = set()
    existing_routes = []
    out_path = DATA_DIR / city / "xhs_routes.json"
    if out_path.exists() and not reextract:
        try:
            existing_routes = json.loads(out_path.read_text(encoding="utf-8"))
            existing_ids = {r.get("source_note_id") for r in existing_routes}
            log.info(f"Existing routes: {len(existing_routes)}")
        except Exception:
            pass

    for i, note in enumerate(notes):
        note_id = note.get("noteId") or note.get("source_note_id") or note.get("id", f"unknown_{i}")
        title = note.get("title") or note.get("source_title") or ""
        desc = note.get("desc") or note.get("content") or note.get("raw_content") or ""
        likes = note.get("likes", "0")
        note_url = note.get("noteUrl") or note.get("source_url") or f"https://www.xiaohongshu.com/explore/{note_id}"

        if note_id in existing_ids and not reextract:
            skipped += 1
            continue

        # Quick filter: skip notes that clearly aren't routes
        if not is_route_content(title, desc):
            log.info(f"  [{i+1}/{len(notes)}] Skip (not route content): {title[:40]}")
            skipped += 1
            continue

        if len(desc) < 80:
            log.info(f"  [{i+1}/{len(notes)}] Skip (too short): {title[:40]}")
            skipped += 1
            continue

        log.info(f"  [{i+1}/{len(notes)}] Processing: {title[:50]}")

        # Call LLM
        route = call_llm(
            llm_cfg,
            ROUTE_EXTRACT_PROMPT,
            f"城市：{city_name}\n标题：{title}\n内容：\n{desc[:5000]}",
        )

        if route:
            total_stops = sum(len(d.get("stops", [])) for d in route.get("itinerary", []))
            log.info(f"    -> Route: {route.get('days', '?')} days, {total_stops} stops")

            route_entry = {
                "source_note_id": note_id,
                "source_url": note_url,
                "source_title": title,
                "source_likes": str(likes),
                "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "city": city,
                "city_name": city_name,
                **route,
            }
            routes.append(route_entry)
            processed += 1
        else:
            log.info(f"    -> No route extracted")
            skipped += 1

        # Rate limit: ~1 request per 2 seconds
        time.sleep(1.5)

    log.info(f"\nProcessed: {processed}, Skipped: {skipped}")
    return routes, existing_routes


def save_routes(city, new_routes, existing_routes):
    """Merge and save routes."""
    out_path = DATA_DIR / city / "xhs_routes.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Deduplicate
    merged = list(existing_routes)
    existing_ids = {r.get("source_note_id") for r in merged}
    new_count = 0
    for r in new_routes:
        if r["source_note_id"] not in existing_ids:
            merged.append(r)
            existing_ids.add(r["source_note_id"])
            new_count += 1

    # Sort by days then likes
    merged.sort(key=lambda r: (r.get("days", 99), -int(str(r.get("source_likes", "0")).replace("wan", "0000"))))

    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Saved: {len(merged)} total routes ({new_count} new) -> {out_path}")
    return new_count


def main():
    parser = argparse.ArgumentParser(description="Extract travel routes from XHS notes")
    parser.add_argument("--city", help="City to process")
    parser.add_argument("--all", action="store_true", help="Process all cities")
    parser.add_argument("--input", help="Input JSON file (overrides default search)")
    parser.add_argument("--reextract", action="store_true", help="Re-process all notes (ignore existing)")
    args = parser.parse_args()

    llm_cfg = load_llm_config()
    if not llm_cfg["api_key"]:
        log.error("No LLM API key configured. Set config/llm.local.json or DEEPSEEK_API_KEY env")
        sys.exit(1)

    log.info(f"LLM: {llm_cfg['model']} @ {llm_cfg['base_url']}")

    cities = ALL_CITIES if args.all else ([args.city] if args.city else ["guangzhou"])

    total_new = 0
    for city in cities:
        city_name = CITY_NAMES.get(city, city)
        log.info(f"\n{'='*50}")
        log.info(f"City: {city_name} ({city})")

        notes = load_notes(city, args.input)
        if not notes:
            log.warning(f"  No notes found for {city}")
            continue

        log.info(f"  Loaded {len(notes)} notes")

        routes, existing = extract_routes_from_notes(city, notes, llm_cfg, args.reextract)
        new_count = save_routes(city, routes, existing)
        total_new += new_count

    log.info(f"\n=== Done: {total_new} new routes total ===")


if __name__ == "__main__":
    main()
