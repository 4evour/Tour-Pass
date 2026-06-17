"""Build unified POI knowledge base from multiple data sources.

Usage:
    python scripts/build_poi_knowledge.py --city guangzhou
    python scripts/build_poi_knowledge.py --city guangzhou --dry-run

Inputs (per city):
    data/{city}/pois.json           - Amap POI data
    data/{city}/xhs_guides.json     - Raw XHS crawled notes
    data/{city}/city_tips.json      - Previously extracted XHS tips (optional)
    data/{city}/city_guide.json     - LLM-generated city guide (optional)

Output:
    data/{city}/poi_knowledge.json  - Unified knowledge base for agents
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("build_poi_knowledge")

# ---------------------------------------------------------------------------
# Text cleaning (reused from extract_xhs_tips.py)
# ---------------------------------------------------------------------------

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)
_HASHTAG_RE = re.compile(r"#[^\s#]+")
_URL_RE = re.compile(r"https?://\S+")


def clean_text(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = _HASHTAG_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Rule-based tip extraction (reused from extract_xhs_tips.py)
# ---------------------------------------------------------------------------

_RULES: list[tuple[str, re.Pattern, str]] = [
    ("time", re.compile(
        r"(?:开放时间|营业时间|开馆时间|开门时间)[：:]\s*"
        r"(\d{1,2}[：:]\d{2}\s*[-—~～至到]\s*\d{1,2}[：:]\d{2})"
    ), "opening_hours"),
    ("time", re.compile(r"(?:周[一二三四五六日天]|星期[一二三四五六日天])闭馆"), "closed_day"),
    ("time", re.compile(r"(?:免门票|免费|无需预约|不需预约|不要门票)"), "free_entry"),
    ("time", re.compile(r"(?:周一|星期一)闭馆"), "closed_monday"),
    ("transport", re.compile(
        r"(?:地铁|地铁线)\s*(\d+\s*号线|[A-Za-z]+\s*线)\s*"
        r"([\u4e00-\u9fff]+(?:站|口|出口))(?:.*?(?:步行|走)\s*(\d+)\s*[m米])?"
    ), "metro_directions"),
    ("transport", re.compile(r"(?:公交|巴士)\s*([\u4e00-\u9fff]+\s*(?:路|线))"), "bus_directions"),
    ("transport", re.compile(r"(?:停车|车位).*?(?:不方便|困难|紧张|收费)"), "parking_warning"),
    ("photography", re.compile(r"(?:拍照|出片|打卡|穿搭).{0,20}(?:建议|推荐|适合|穿)"), "photo_tip"),
    ("photography", re.compile(r"(?:穿|建议穿).{0,15}(?:色|系|裙子|衣服|服装)"), "outfit_tip"),
    ("duration", re.compile(
        r"(?:游览|游玩|逛|参观).*?(?:时间|小时|分钟)\s*[约大概]*\s*(\d+)\s*(?:小时|个?小时|h)"
    ), "visit_duration"),
    ("duration", re.compile(r"(?:至少|建议|需要).*?(\d+)\s*(?:小时|个?小时|h)"), "min_duration"),
    ("crowd", re.compile(r"(?:别|不要|避免|注意|小心|警惕).{0,30}(?:踩雷|上当|被宰|排队|挤|坑)"), "avoid_warning"),
    ("crowd", re.compile(r"(?:周末|节假日).{0,10}(?:人多|排队|挤|爆满)"), "crowd_warning"),
    ("food", re.compile(r"(?:推荐|必吃|必点|好吃).{0,20}(?:虾饺|烧鹅|肠粉|早茶|点心|煲仔饭|奶茶)"), "food_rec"),
]


def _extract_sentence_around(text: str, match: re.Match, window: int = 80) -> str:
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    snippet = text[start:end]
    snippet = re.sub(r"^\S{1,10}", "", snippet) if start > 0 else snippet
    snippet = re.sub(r"\S{1,10}$", "", snippet) if end < len(text) else snippet
    return snippet.strip()


def extract_tips_from_text(desc: str) -> list[dict]:
    """Extract structured tips from a note description using rules."""
    cleaned = clean_text(desc)
    if len(cleaned) < 10:
        return []

    tips = []
    seen = set()
    for category, pattern, label in _RULES:
        for m in pattern.finditer(cleaned):
            key = f"{category}_{label}"
            if key in seen:
                continue
            seen.add(key)
            text = _extract_sentence_around(cleaned, m)
            if text and len(text) >= 5:
                tips.append({"category": category, "text": text, "label": label})
    return tips


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def compute_confidence(source: str, likes: int = 0) -> float:
    if source == "xhs":
        base = 0.7
        if likes > 1000:
            base += 0.15
        elif likes > 500:
            base += 0.1
        return min(base, 1.0)
    if source == "city_guide":
        return 0.5
    if source == "llm_supplement":
        return 0.4
    return 0.5


# ---------------------------------------------------------------------------
# Step 1: Clean XHS data
# ---------------------------------------------------------------------------

def clean_xhs(notes: list[dict]) -> list[dict]:
    """Filter out garbage XHS notes, return clean ones."""
    clean = []
    for note in notes:
        desc = note.get("desc", "")
        # Remove rate-limited placeholders
        if not desc or "访问频繁" in desc:
            continue
        # Remove notes with no POI match
        pois = note.get("matchedPois", [])
        if not pois:
            continue
        # Remove very short descriptions
        if len(desc.strip()) < 30:
            continue
        clean.append(note)
    return clean


# ---------------------------------------------------------------------------
# Step 2: Extract tips from clean XHS notes
# ---------------------------------------------------------------------------

def extract_xhs_tips(notes: list[dict]) -> dict[str, list[dict]]:
    """Extract tips from XHS notes, grouped by POI name."""
    poi_tips: dict[str, list[dict]] = defaultdict(list)

    for note in notes:
        desc = note.get("desc", "")
        likes = int(note.get("likes", "0") or "0")
        matched = note.get("matchedPois", [])
        if not matched or not desc:
            continue

        tips = extract_tips_from_text(desc)
        if not tips:
            continue

        # Attribute tips to all matched POIs
        for poi in matched:
            name = poi.get("name", "")
            if not name:
                continue
            for tip in tips:
                poi_tips[name].append({
                    "category": tip["category"],
                    "text": tip["text"],
                    "source": "xhs",
                    "source_likes": likes,
                    "confidence": compute_confidence("xhs", likes),
                })

    return dict(poi_tips)


# ---------------------------------------------------------------------------
# Step 3: Merge city_tips.json (from previous extraction)
# ---------------------------------------------------------------------------

def merge_city_tips(existing_tips: dict) -> dict[str, list[dict]]:
    """Convert existing city_tips.json format to unified tip format."""
    result: dict[str, list[dict]] = {}
    for poi_name, info in existing_tips.items():
        tips_raw = info.get("tips", [])
        merged = []
        for t in tips_raw:
            likes = t.get("votes", 0) * 10  # rough conversion
            merged.append({
                "category": t.get("category", "general"),
                "text": t.get("text", ""),
                "source": "xhs",
                "source_likes": likes,
                "confidence": compute_confidence("xhs", likes),
            })
        if merged:
            result[poi_name] = merged
    return result


# ---------------------------------------------------------------------------
# Step 4: Extract tips from city_guide.json
# ---------------------------------------------------------------------------

def extract_guide_tips(guide: dict, poi_names: set[str]) -> dict[str, list[dict]]:
    """Match city_guide tips to specific POIs."""
    poi_tips: dict[str, list[dict]] = defaultdict(list)

    category_map = {
        "timing_tips": "time",
        "crowd_tips": "crowd",
        "food_tips": "food",
        "transport_tips": "transport",
        "hidden_gems": "hidden",
    }

    for guide_key, tip_category in category_map.items():
        items = guide.get(guide_key, [])
        for item in items:
            if not isinstance(item, str):
                continue
            # Find which POI this tip mentions
            matched_poi = None
            for name in poi_names:
                if name in item:
                    matched_poi = name
                    break
            if not matched_poi:
                continue
            poi_tips[matched_poi].append({
                "category": tip_category,
                "text": item,
                "source": "city_guide",
                "source_likes": 0,
                "confidence": compute_confidence("city_guide"),
            })

    return dict(poi_tips)


# ---------------------------------------------------------------------------
# Step 5: Extract metadata from XHS notes
# ---------------------------------------------------------------------------

def extract_metadata(notes: list[dict]) -> dict[str, dict]:
    """Extract closed_days, free, related_pois from XHS notes."""
    meta: dict[str, dict] = defaultdict(lambda: {
        "closed_days": set(),
        "free": False,
        "related_pois": set(),
    })

    for note in notes:
        desc = note.get("desc", "")
        matched = note.get("matchedPois", [])
        names = [p.get("name", "") for p in matched if p.get("name")]

        # closed_days
        if "周一闭馆" in desc or "星期一闭馆" in desc:
            for n in names:
                meta[n]["closed_days"].add("Monday")
        if "周二闭馆" in desc or "星期二闭馆" in desc:
            for n in names:
                meta[n]["closed_days"].add("Tuesday")

        # free
        if re.search(r"免门票|免费|无需预约", desc):
            for n in names:
                meta[n]["free"] = True

        # related_pois: POIs in the same note are related
        for i, a in enumerate(names):
            for j, b in enumerate(names):
                if i != j and b:
                    meta[a]["related_pois"].add(b)

    # Convert sets to lists for JSON serialization
    return {
        name: {
            "closed_days": sorted(list(v["closed_days"])),
            "free": v["free"],
            "related_pois": sorted(list(v["related_pois"])),
        }
        for name, v in meta.items()
    }


# ---------------------------------------------------------------------------
# Step 6: Deduplicate tips
# ---------------------------------------------------------------------------

def deduplicate_tips(tips: list[dict]) -> list[dict]:
    """Remove duplicate tips within a POI, keeping highest confidence."""
    seen_texts: dict[str, int] = {}  # text -> index in result
    result = []

    # Sort by confidence desc so highest wins
    for tip in sorted(tips, key=lambda t: t["confidence"], reverse=True):
        # Normalize for dedup: strip whitespace, lowercase
        norm = tip["text"].strip().lower()[:100]
        if norm in seen_texts:
            continue
        seen_texts[norm] = len(result)
        result.append(tip)

    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def build(city: str, data_dir: str = "data", dry_run: bool = False) -> dict:
    city_dir = Path(data_dir) / city
    if not city_dir.exists():
        logger.error("City directory not found: %s", city_dir)
        sys.exit(1)

    # Load POIs
    pois_path = city_dir / "pois.json"
    if not pois_path.exists():
        logger.error("pois.json not found: %s", pois_path)
        sys.exit(1)

    with open(pois_path, "r", encoding="utf-8") as f:
        pois = json.load(f)
    logger.info("Loaded %d POIs for %s", len(pois), city)

    # Build POI lookup by name
    poi_by_name: dict[str, dict] = {}
    for p in pois:
        poi_by_name[p["name"]] = p

    poi_names = set(poi_by_name.keys())

    # --- XHS tips ---
    xhs_tips: dict[str, list[dict]] = {}
    xhs_notes_clean = []
    xhs_path = city_dir / "xhs_guides.json"
    if xhs_path.exists():
        with open(xhs_path, "r", encoding="utf-8") as f:
            raw_notes = json.load(f)
        xhs_notes_clean = clean_xhs(raw_notes)
        logger.info("XHS: %d raw -> %d clean notes", len(raw_notes), len(xhs_notes_clean))
        xhs_tips = extract_xhs_tips(xhs_notes_clean)
        logger.info("XHS: extracted tips for %d POIs", len(xhs_tips))

    # --- Existing city_tips ---
    city_tips_merged: dict[str, list[dict]] = {}
    tips_path = city_dir / "city_tips.json"
    if tips_path.exists():
        with open(tips_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        city_tips_merged = merge_city_tips(existing)
        logger.info("city_tips: loaded tips for %d POIs", len(city_tips_merged))

    # --- City guide tips ---
    guide_tips: dict[str, list[dict]] = {}
    guide_path = city_dir / "city_guide.json"
    if guide_path.exists():
        with open(guide_path, "r", encoding="utf-8") as f:
            guide = json.load(f)
        guide_tips = extract_guide_tips(guide, poi_names)
        logger.info("city_guide: matched tips for %d POIs", len(guide_tips))

    # --- Metadata from XHS ---
    xhs_meta = extract_metadata(xhs_notes_clean)

    # --- Merge everything ---
    all_poi_names = set(poi_by_name.keys())
    merged_tips: dict[str, list[dict]] = defaultdict(list)

    # Merge order: city_tips (already extracted) -> xhs_tips (fresh) -> guide_tips (LLM)
    for name in all_poi_names:
        merged_tips[name].extend(city_tips_merged.get(name, []))
        merged_tips[name].extend(xhs_tips.get(name, []))
        merged_tips[name].extend(guide_tips.get(name, []))
        merged_tips[name] = deduplicate_tips(merged_tips[name])

    # Build final output
    pois_out = {}
    stats_sources = {"xhs": 0, "city_guide": 0, "llm_supplement": 0}
    pois_with_tips = 0
    total_tips = 0

    for poi in pois:
        name = poi["name"]
        tips = merged_tips.get(name, [])
        meta = xhs_meta.get(name, {})

        if tips:
            pois_with_tips += 1
            total_tips += len(tips)
            for t in tips:
                src = t.get("source", "unknown")
                if src in stats_sources:
                    stats_sources[src] += 1

        # Build POI entry
        entry = {
            "name": name,
            "type": poi.get("type", ""),
            "lat": poi.get("lat"),
            "lng": poi.get("lng"),
            "area": poi.get("area", ""),
            "open_time": poi.get("open_time", ""),
            "close_time": poi.get("close_time", ""),
            "visit_duration_minutes": poi.get("visit_duration_minutes", 60),
            "popularity": poi.get("popularity", 0),
            "price_level": poi.get("price_level", 0),
            "tags": poi.get("tags", []),
            "description": poi.get("description", ""),
            "recommendation": poi.get("recommendation", ""),
            "tips": tips,
            "related_pois": meta.get("related_pois", []),
            "closed_days": meta.get("closed_days", []),
            "free": meta.get("free", False),
        }
        pois_out[poi.get("id", name)] = entry

    result = {
        "city": city,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_pois": len(pois),
            "pois_with_tips": pois_with_tips,
            "total_tips": total_tips,
            "sources": stats_sources,
        },
        "pois": pois_out,
    }

    # --- Write output ---
    if dry_run:
        logger.info("=== DRY RUN ===")
        logger.info("Stats: %s", json.dumps(result["stats"], ensure_ascii=False))
        for pid, entry in list(pois_out.items())[:3]:
            logger.info("  %s: %d tips", entry["name"], len(entry["tips"]))
            for t in entry["tips"][:2]:
                logger.info("    [%s] %s (conf=%.2f)", t["category"], t["text"][:60], t["confidence"])
        return result

    out_path = city_dir / "poi_knowledge.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info("Wrote %s (%d POIs, %d tips)", out_path, len(pois_out), total_tips)

    # Also write clean XHS as intermediate artifact
    if xhs_notes_clean:
        clean_path = city_dir / "xhs_clean.json"
        with open(clean_path, "w", encoding="utf-8") as f:
            json.dump(xhs_notes_clean, f, ensure_ascii=False, indent=2)
        logger.info("Wrote clean XHS: %s (%d notes)", clean_path, len(xhs_notes_clean))

    return result


def main():
    parser = argparse.ArgumentParser(description="Build POI knowledge base")
    parser.add_argument("--city", required=True, help="City directory name")
    parser.add_argument("--data-dir", default="data", help="Data directory path")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    result = build(args.city, args.data_dir, args.dry_run)
    stats = result["stats"]
    logger.info(
        "Done. %d POIs, %d with tips, %d total tips",
        stats["total_pois"], stats["pois_with_tips"], stats["total_tips"],
    )


if __name__ == "__main__":
    main()
