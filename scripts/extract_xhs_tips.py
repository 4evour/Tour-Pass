"""Extract structured travel tips from Xiaohongshu (小红书) guides.

Usage:
    python scripts/extract_xhs_tips.py                       # all cities
    python scripts/extract_xhs_tips.py --city guangzhou      # single city
    python scripts/extract_xhs_tips.py --dry-run             # preview only

Input:  data/{city}/xhs_guides.json
Output: data/{city}/city_tips.json

The script performs two strategies:
  1. Rule-based extraction (fast, no LLM needed) — regex patterns for
     time, transport, ticket, photography, duration, avoid tips.
  2. LLM-based extraction (optional, needs DEEPSEEK_API_KEY) — sends
     each note desc through DeepSeek for higher-quality structured tips.

By default uses rule-based only.  Pass --use-llm to enable LLM extraction.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("extract_xhs_tips")

# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FAFF"  # extended-A
    "\U00002702-\U000027B0"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # ZWJ
    "]+",
    flags=re.UNICODE,
)

_HASHTAG_RE = re.compile(r"#[^\s#]+")
_URL_RE = re.compile(r"https?://\S+")
_AD_PATTERNS = [
    re.compile(r"关注我.*?了解更多", re.DOTALL),
    re.compile(r"点击.*?链接", re.DOTALL),
    re.compile(r"复制.*?打开.*?app", re.DOTALL),
    re.compile(r"私信.*?领取", re.DOTALL),
    re.compile(r"广告", re.IGNORECASE),
]


def clean_desc(text: str) -> str:
    """Remove emoji, hashtags, URLs, and obvious ads from desc text."""
    text = _EMOJI_RE.sub("", text)
    text = _HASHTAG_RE.sub("", text)
    text = _URL_RE.sub("", text)
    for pat in _AD_PATTERNS:
        text = pat.sub("", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Rule-based tip extraction
# ---------------------------------------------------------------------------

# Each rule: (category, pattern, description)
_RULES: list[tuple[str, re.Pattern, str]] = [
    # Time / opening hours
    (
        "time",
        re.compile(
            r"(?:开放时间|营业时间|开馆时间|开门时间)[：:]\s*"
            r"(\d{1,2}[：:]\d{2}\s*[-—~～至到]\s*\d{1,2}[：:]\d{2})"
        ),
        "opening_hours",
    ),
    (
        "time",
        re.compile(r"(?:周[一二三四五六日天]|星期[一二三四五六日天])闭馆"),
        "closed_day",
    ),
    (
        "time",
        re.compile(r"(?:免门票|免费|无需预约|不需预约|不要门票)"),
        "free_entry",
    ),
    (
        "time",
        re.compile(r"(?:周一|星期一)闭馆"),
        "closed_monday",
    ),
    # Transport
    (
        "transport",
        re.compile(
            r"(?:地铁|地铁线)\s*(\d+\s*号线|[A-Za-z]+\s*线)\s*"
            r"([\u4e00-\u9fff]+(?:站|口|出口))(?:.*?(?:步行|走)\s*(\d+)\s*[m米])?"
        ),
        "metro_directions",
    ),
    (
        "transport",
        re.compile(r"(?:公交|巴士)\s*([\u4e00-\u9fff]+\s*(?:路|线))"),
        "bus_directions",
    ),
    (
        "transport",
        re.compile(r"(?:停车|车位).*?(?:不方便|困难|紧张|收费)"),
        "parking_warning",
    ),
    # Photography
    (
        "photography",
        re.compile(r"(?:拍照|出片|打卡|穿搭).{0,20}(?:建议|推荐|适合|穿)"),
        "photo_tip",
    ),
    (
        "photography",
        re.compile(r"(?:穿|建议穿).{0,15}(?:色|系|裙子|衣服|服装)"),
        "outfit_tip",
    ),
    # Duration
    (
        "duration",
        re.compile(r"(?:游览|游玩|逛|参观).*?(?:时间|小时|分钟)\s*[约大概]*\s*(\d+)\s*(?:小时|个?小时|h)"),
        "visit_duration",
    ),
    (
        "duration",
        re.compile(r"(?:至少|建议|需要).*?(\d+)\s*(?:小时|个?小时|h)"),
        "min_duration",
    ),
    # Avoid / warning
    (
        "avoid",
        re.compile(r"(?:别|不要|避免|注意|小心|警惕).{0,30}(?:踩雷|上当|被宰|排队|挤|坑)"),
        "avoid_warning",
    ),
    (
        "avoid",
        re.compile(r"(?:周末|节假日).{0,10}(?:人多|排队|挤|爆满)"),
        "crowd_warning",
    ),
    # Best time to visit
    (
        "best_time",
        re.compile(r"(?:建议|最好|推荐).*?(?:早上|上午|下午|傍晚|晚上|工作日|非周末|清晨)"),
        "best_time_tip",
    ),
    (
        "best_time",
        re.compile(r"(\d+)[点时].*?(?:去|到|来|前).{0,10}(?:人少|不挤|清静|光线好)"),
        "optimal_hour",
    ),
    # Food / restaurant nearby
    (
        "food",
        re.compile(r"(?:推荐|好吃|必吃|必点|招牌).{0,5}(?:菜|餐|小吃|奶茶|甜品|点心|火锅|烧烤)"),
        "food_recommendation",
    ),
]


def _extract_sentence_around(text: str, match: re.Match, window: int = 60) -> str:
    """Extract a clean sentence around a regex match."""
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    snippet = text[start:end]
    # Try to snap to sentence boundaries
    for sep in ("。", "！", "!", "；", "\n"):
        idx = snippet.find(sep)
        if idx > 0:
            snippet = snippet[: idx + 1]
            break
    return snippet.strip()


def extract_tips_rule_based(desc: str) -> list[dict]:
    """Extract structured tips from a single note description using rules."""
    cleaned = clean_desc(desc)
    if len(cleaned) < 10:
        return []

    tips = []
    seen_categories = set()

    for category, pattern, label in _RULES:
        matches = list(pattern.finditer(cleaned))
        for m in matches:
            # Avoid duplicate categories per note
            cat_key = f"{category}_{label}"
            if cat_key in seen_categories:
                continue
            seen_categories.add(cat_key)

            text = _extract_sentence_around(cleaned, m)
            if text and len(text) >= 5:
                tips.append(
                    {
                        "category": category,
                        "text": text,
                        "label": label,
                    }
                )

    return tips


# ---------------------------------------------------------------------------
# LLM-based extraction (optional)
# ---------------------------------------------------------------------------

_LLM_SYSTEM = """你是旅行攻略提炼专家。从小红书笔记中提取结构化旅行建议。

对每条笔记提取以下类别的建议（有的才提取，没有就跳过）：
- time: 开放时间、闭馆日、预约信息
- transport: 交通方式、地铁/公交指引、停车信息
- avoid: 避坑建议、注意事项、踩雷提醒
- photography: 拍照建议、穿搭推荐、最佳拍摄时间
- duration: 建议游玩时长
- best_time: 最佳到访时间、避开人流建议
- food: 附近美食推荐
- ticket: 门票信息、购票建议
- hidden: 本地人推荐、隐藏玩法

输出 JSON 数组，每个元素: {"category": "...", "text": "建议内容（一句话）"}
只输出 JSON，不要其他文字。"""


def extract_tips_llm(desc: str, llm_client) -> list[dict]:
    """Extract tips using LLM (DeepSeek).  Requires an initialised client."""
    cleaned = clean_desc(desc)
    if len(cleaned) < 10:
        return []

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        resp = llm_client.invoke(
            [
                SystemMessage(content=_LLM_SYSTEM),
                HumanMessage(content=cleaned[:1500]),  # cap token usage
            ]
        )
        text = resp.content.strip()
        # Extract JSON array
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        tips = json.loads(text)
        if isinstance(tips, list):
            return [t for t in tips if isinstance(t, dict) and "category" in t and "text" in t]
    except Exception as e:
        logger.debug("LLM extraction failed for note: %s", e)

    return []


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate_tips(all_note_tips: list[tuple[str, list[dict], int]]) -> dict:
    """Aggregate tips across notes for the same POI.

    Args:
        all_note_tips: list of (poi_name, tips_list, likes)

    Returns:
        dict mapping poi_name -> aggregated tip info.
    """
    # Group by POI
    poi_data: dict[str, list[tuple[dict, int]]] = defaultdict(list)
    for poi_name, tips, likes in all_note_tips:
        if not poi_name:
            continue
        for tip in tips:
            poi_data[poi_name].append((tip, likes))

    result = {}
    for poi_name, tip_entries in poi_data.items():
        # Group by category
        category_tips: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for tip, likes in tip_entries:
            cat = tip.get("category", "general")
            text = tip.get("text", "").strip()
            if text and len(text) >= 5:
                category_tips[cat].append((text, likes))

        # For each category, pick the most-voted (longest) tip
        aggregated_tips = []
        for cat, entries in category_tips.items():
            # Score by: frequency (how many notes mention it) + total likes
            # Simple heuristic: pick the most common tip text (by substring similarity)
            # For now, pick the one with most likes, then deduplicate
            entries.sort(key=lambda x: x[1], reverse=True)
            best_text = entries[0][0]
            votes = len(entries)
            aggregated_tips.append(
                {
                    "category": cat,
                    "text": best_text,
                    "votes": votes,
                }
            )

        # Sort by votes descending, keep top 5
        aggregated_tips.sort(key=lambda t: t["votes"], reverse=True)
        aggregated_tips = aggregated_tips[:5]

        if aggregated_tips:
            # Calculate average likes
            all_likes = [likes for _, likes in tip_entries]
            result[poi_name] = {
                "tips": aggregated_tips,
                "source_count": len(tip_entries),
                "avg_likes": sum(all_likes) / len(all_likes) if all_likes else 0,
            }

    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def process_city(
    city_dir: Path,
    use_llm: bool = False,
    dry_run: bool = False,
) -> dict:
    """Process a single city's XHS guides into structured tips.

    Args:
        city_dir: Path to the city data directory.
        use_llm: Whether to use LLM for extraction.
        dry_run: If True, don't write output file.

    Returns:
        Aggregated tips dict.
    """
    xhs_file = city_dir / "xhs_guides.json"
    if not xhs_file.exists():
        logger.info("No xhs_guides.json for %s, skipping", city_dir.name)
        return {}

    with open(xhs_file, "r", encoding="utf-8") as f:
        notes = json.load(f)

    if not isinstance(notes, list):
        logger.warning("xhs_guides.json is not a list for %s", city_dir.name)
        return {}

    logger.info("Processing %d notes for %s", len(notes), city_dir.name)

    # Optional LLM client
    llm_client = None
    if use_llm:
        try:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            if api_key:
                from langchain_openai import ChatOpenAI

                llm_client = ChatOpenAI(
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    temperature=0.1,
                )
                logger.info("LLM extraction enabled (model=%s)", model)
            else:
                logger.warning("--use-llm requested but DEEPSEEK_API_KEY not set")
        except ImportError:
            logger.warning("langchain_openai not available, falling back to rules")

    # Extract tips from each note
    all_note_tips: list[tuple[str, list[dict], int]] = []

    for note in notes:
        desc = note.get("desc", "")
        title = note.get("title", "")
        likes_str = note.get("likes", "0")
        try:
            likes = int(likes_str)
        except (ValueError, TypeError):
            likes = 0

        # Determine POI name
        matched_pois = note.get("matchedPois", [])
        poi_name = ""
        if matched_pois:
            poi_name = matched_pois[0].get("name", "")
        if not poi_name:
            # Try to extract from title
            poi_name = title[:20] if title else ""

        if not desc or not poi_name:
            continue

        # Rule-based extraction
        tips = extract_tips_rule_based(desc)

        # LLM extraction (optional, for higher quality)
        if llm_client and desc:
            llm_tips = extract_tips_llm(desc, llm_client)
            if llm_tips:
                # Merge: prefer LLM tips, supplement with rule-based
                existing_cats = {t.get("category") for t in llm_tips}
                for rt in tips:
                    if rt.get("category") not in existing_cats:
                        llm_tips.append(rt)
                tips = llm_tips

        if tips:
            all_note_tips.append((poi_name, tips, likes))

    # Aggregate
    aggregated = aggregate_tips(all_note_tips)

    logger.info(
        "Extracted tips for %d POIs from %d notes in %s",
        len(aggregated),
        len(all_note_tips),
        city_dir.name,
    )

    # Write output
    if not dry_run and aggregated:
        output_file = city_dir / "city_tips.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(aggregated, f, ensure_ascii=False, indent=2)
        logger.info("Wrote %s", output_file)
    elif dry_run:
        logger.info("Dry run — would write %d POI tips", len(aggregated))
        # Print preview
        for poi_name, info in list(aggregated.items())[:5]:
            logger.info("  %s: %d tips", poi_name, len(info["tips"]))
            for tip in info["tips"][:3]:
                logger.info("    [%s] %s (votes=%d)", tip["category"], tip["text"], tip["votes"])

    return aggregated


def main():
    parser = argparse.ArgumentParser(description="Extract tips from XHS guides")
    parser.add_argument("--city", help="Process a single city (directory name)")
    parser.add_argument("--data-dir", default="data", help="Data directory path")
    parser.add_argument("--use-llm", action="store_true", help="Use LLM for extraction")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    data_path = Path(args.data_dir)
    if not data_path.exists():
        logger.error("Data directory not found: %s", data_path)
        sys.exit(1)

    cities_processed = 0
    total_pois = 0

    if args.city:
        city_dir = data_path / args.city
        if not city_dir.exists():
            logger.error("City directory not found: %s", city_dir)
            sys.exit(1)
        result = process_city(city_dir, use_llm=args.use_llm, dry_run=args.dry_run)
        total_pois = len(result)
        cities_processed = 1
    else:
        for entry in sorted(data_path.iterdir()):
            if not entry.is_dir():
                continue
            xhs_file = entry / "xhs_guides.json"
            if xhs_file.exists():
                result = process_city(entry, use_llm=args.use_llm, dry_run=args.dry_run)
                total_pois += len(result)
                cities_processed += 1

    logger.info(
        "Done. Processed %d cities, extracted tips for %d POIs total.",
        cities_processed,
        total_pois,
    )


if __name__ == "__main__":
    main()

