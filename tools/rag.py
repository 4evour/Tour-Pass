"""Tour Pass Multi-Agent System - Lightweight RAG (BM25) for city guides and XHS tips.

Migrated from agent/rag.py with enhancements for multi-agent architecture.
No ChromaDB or ML model dependencies.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Chinese city name -> directory name mapping
_CITY_DIR_MAP = {
    "广州": "guangzhou", "北京": "beijing", "上海": "shanghai",
    "深圳": "shenzhen", "成都": "chengdu", "重庆": "chongqing",
    "杭州": "hangzhou", "武汉": "wuhan", "南京": "nanjing",
    "西安": "xian", "长沙": "changsha", "昆明": "kunming",
    "大理": "dali", "丽江": "lijiang", "三亚": "sanya",
    "桂林": "guilin", "厦门": "xiamen", "青岛": "qingdao",
    "哈尔滨": "harbin", "苏州": "suzhou", "张家界": "zhangjiajie",
}


def _normalize_city(city: str) -> str:
    """Map Chinese city name to directory name if needed."""
    return _CITY_DIR_MAP.get(city, city)

# ---------------------------------------------------------------------------
# In-memory index
# ---------------------------------------------------------------------------
# Each entry: {"city": str, "category": str, "text": str, "tokens": list[str]}
_corpus: list[dict] = []
_idf: dict[str, float] = {}
_indexed_cities: set[str] = set()
_ready = False
_skip = False

# POI knowledge store: city -> {poi_name: {name, tips, closed_days, ...}}
_poi_knowledge: dict[str, dict[str, dict]] = {}


def _tokenize(text: str) -> list[str]:
    """Tokenize Chinese/English text into character bigrams + word tokens."""
    text = text.lower()
    # Extract CJK characters as unigrams
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    # Extract word tokens (latin/digits)
    words = re.findall(r"[a-z0-9]+", text)
    tokens = list(cjk) + words
    # Add bigrams for CJK
    for i in range(len(cjk) - 1):
        tokens.append(cjk[i] + cjk[i + 1])
    return tokens


def _build_idf():
    """Rebuild IDF from current corpus."""
    global _idf
    n = len(_corpus)
    if n == 0:
        _idf = {}
        return
    df: Counter = Counter()
    for doc in _corpus:
        unique = set(doc["tokens"])
        for t in unique:
            df[t] += 1
    _idf = {
        t: math.log((n - freq + 0.5) / (freq + 0.5) + 1)
        for t, freq in df.items()
    }


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """BM25 scoring between query and document tokens."""
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_len = len(doc_tokens)
    avg_dl = 50.0  # approximate average doc length
    tf = Counter(doc_tokens)
    score = 0.0
    for qt in set(query_tokens):
        if qt not in tf:
            continue
        idf = _idf.get(qt, 0.0)
        term_freq = tf[qt]
        numerator = term_freq * (k1 + 1)
        denominator = term_freq + k1 * (1 - b + b * doc_len / avg_dl)
        score += idf * numerator / denominator
    return score


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def is_rag_ready() -> bool:
    """Check if RAG index is ready."""
    return _ready and not _skip


def is_city_indexed(city: str) -> bool:
    """Check if a city's RAG data has been indexed."""
    return _normalize_city(city) in _indexed_cities


def mark_rag_ready():
    """Mark RAG as ready."""
    global _ready
    _ready = True


def mark_rag_skip():
    """Mark RAG as skipped."""
    global _skip
    _skip = True
    logger.info("RAG marked as skipped")


def _add_chunk(city: str, category: str, text: str):
    """Add a text chunk to the in-memory corpus."""
    _corpus.append(
        {
            "city": city,
            "category": category,
            "text": text,
            "tokens": _tokenize(text),
        }
    )


# ---------------------------------------------------------------------------
# Ingestion: city_guide.json
# ---------------------------------------------------------------------------

CATEGORY_LABELS = {
    "best_routes": "最佳路线",
    "timing_tips": "时间建议",
    "crowd_tips": "避坑建议",
    "food_tips": "美食推荐",
    "transport_tips": "交通建议",
    "seasonal_tips": "季节建议",
    "hidden_gems": "隐藏玩法",
}


def ingest_city_guide(city: str, guide_path: str) -> int:
    """Load a city_guide.json into the BM25 index.

    Returns the number of chunks added.
    """
    if not os.path.exists(guide_path):
        logger.warning("Guide file not found: %s", guide_path)
        return 0

    with open(guide_path, "r", encoding="utf-8") as f:
        guide = json.load(f)

    count = 0
    for category, label in CATEGORY_LABELS.items():
        for tip in guide.get(category, []):
            if not tip or not tip.strip():
                continue
            text = f"【{city}{label}】{tip}"
            _add_chunk(city, category, text)
            count += 1

    _indexed_cities.add(city)
    logger.info("Indexed %d guide chunks for %s", count, city)
    return count


# ---------------------------------------------------------------------------
# Ingestion: guidebook.json (POI descriptions)
# ---------------------------------------------------------------------------


def ingest_guidebook(city: str, guidebook_path: str) -> int:
    """Load a guidebook.json (POI descriptions) into the BM25 index.

    Returns the number of chunks added.
    """
    if not os.path.exists(guidebook_path):
        return 0

    with open(guidebook_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return 0

    count = 0
    for entry in data:
        name = entry.get("name", "")
        desc = entry.get("description", "")
        if not name or not desc:
            continue
        text = f"【{name}】{desc}"
        _add_chunk(city, "poi_description", text)
        count += 1

    logger.info("Indexed %d POI descriptions for %s", count, city)
    return count


# ---------------------------------------------------------------------------
# Ingestion: city_tips.json (extracted from XHS)
# ---------------------------------------------------------------------------


def ingest_city_tips(city: str, tips_path: str) -> int:
    """Load a city_tips.json (extracted XHS tips) into the BM25 index.

    Returns the number of chunks added.
    """
    if not os.path.exists(tips_path):
        return 0

    with open(tips_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for poi_name, info in data.items():
        tips = info.get("tips", [])
        if not tips:
            continue
        tips_text = "；".join(t["text"] for t in tips[:5])
        text = f"【{poi_name}·小红书攻略】{tips_text}"
        _add_chunk(city, "xhs_tips", text)
        count += 1

    logger.info("Indexed %d XHS tip entries for %s", count, city)
    return count


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search_guides(city: str, query: str, top_k: int = 5) -> list[str]:
    """Retrieve relevant guide snippets for a query using BM25.

    Args:
        city: City name to filter by.
        query: Search query.
        top_k: Maximum results.

    Returns:
        List of matching text snippets.
    """
    if not is_rag_ready():
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # Filter to matching city
    norm_city = _normalize_city(city)
    candidates = [doc for doc in _corpus if doc["city"] == norm_city]
    if not candidates:
        return []

    # Score and sort
    scored = []
    for doc in candidates:
        score = _bm25_score(query_tokens, doc["tokens"])
        if score > 0:
            scored.append((score, doc["text"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:top_k]]


def search_guides_broad(
    city: str,
    categories: Optional[list[str]] = None,
    top_k: int = 10,
) -> list[str]:
    """Retrieve guide snippets by category without a specific query.

    Args:
        city: City name.
        categories: Optional category filter.
        top_k: Maximum results.

    Returns:
        List of text snippets.
    """
    if not is_rag_ready():
        return []

    norm_city = _normalize_city(city)
    candidates = [doc for doc in _corpus if doc["city"] == norm_city]
    if categories:
        candidates = [doc for doc in candidates if doc["category"] in categories]

    return [doc["text"] for doc in candidates[:top_k]]


def search_for_poi(city: str, poi_name: str, top_k: int = 3) -> list[str]:
    """Retrieve tips and descriptions for a specific POI.

    Args:
        city: City name.
        poi_name: POI name to search for.
        top_k: Maximum results.

    Returns:
        List of relevant text snippets about this POI.
    """
    if not is_rag_ready():
        return []

    query_tokens = _tokenize(poi_name)
    if not query_tokens:
        return []

    # Filter to matching city and relevant categories
    candidates = [
        doc
        for doc in _corpus
        if doc["city"] == _normalize_city(city)
        and doc["category"] in ("poi_description", "xhs_tips")
    ]

    scored = []
    for doc in candidates:
        # Check if POI name appears in the document text
        if poi_name in doc["text"]:
            score = _bm25_score(query_tokens, doc["tokens"])
            if score > 0:
                scored.append((score, doc["text"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:top_k]]


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# POI Knowledge (poi_knowledge.json)
# ---------------------------------------------------------------------------


def ingest_poi_knowledge(city: str, knowledge_path: str) -> int:
    """Load poi_knowledge.json into both the BM25 index and the direct lookup store."""
    if not os.path.exists(knowledge_path):
        logger.debug("poi_knowledge.json not found for %s", city)
        return 0

    with open(knowledge_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pois = data.get("pois", {})
    if not pois:
        return 0

    norm_city = _normalize_city(city)

    # Store for direct lookup
    _poi_knowledge[norm_city] = pois

    # Index tips into BM25 corpus
    count = 0
    for poi_id, poi in pois.items():
        name = poi.get("name", "")
        tips = poi.get("tips", [])
        if not tips:
            continue
        tip_texts = [f"[{t['category']}] {t['text']}" for t in tips]
        combined = f"【{name}攻略】" + "；".join(tip_texts)
        _add_chunk(norm_city, "poi_knowledge", combined)
        count += 1

    _indexed_cities.add(norm_city)
    logger.info("Indexed %d POI knowledge entries for %s", count, city)
    return count


def get_poi_knowledge(city: str) -> dict[str, dict]:
    """Get the full POI knowledge store for a city."""
    norm_city = _normalize_city(city)
    return _poi_knowledge.get(norm_city, {})


def get_poi_tips(city: str, poi_name: str) -> list[dict]:
    """Get tips for a specific POI by name (fuzzy match)."""
    norm_city = _normalize_city(city)
    pois = _poi_knowledge.get(norm_city, {})
    # Exact match first
    for pid, poi in pois.items():
        if poi.get("name") == poi_name:
            return poi.get("tips", [])
    # Substring match
    for pid, poi in pois.items():
        name = poi.get("name", "")
        if poi_name in name or name in poi_name:
            return poi.get("tips", [])
    return []


def search_poi_tips(city: str, query: str, top_k: int = 3) -> list[str]:
    """Search POI knowledge tips by query, return tip texts."""
    if not is_rag_ready():
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    norm_city = _normalize_city(city)
    candidates = [doc for doc in _corpus if doc["city"] == norm_city and doc["category"] == "poi_knowledge"]
    if not candidates:
        return []

    scored = []
    for doc in candidates:
        score = _bm25_score(query_tokens, doc["tokens"])
        if score > 0:
            scored.append((score, doc["text"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:top_k]]


# Initialization
# ---------------------------------------------------------------------------


def init_rag(data_dir: str = "data") -> int:
    """Initialize RAG by loading all city data.

    Call once at startup.  Returns the number of cities loaded.
    """
    global _ready, _skip
    if _ready:
        return len(_indexed_cities)

    cities_loaded = 0
    data_path = Path(data_dir)

    for entry in data_path.iterdir():
        if not entry.is_dir():
            continue
        city_name = entry.name
        city_loaded = False

        # city_guide.json
        guide_path = entry / "city_guide.json"
        if guide_path.exists():
            try:
                ingest_city_guide(city_name, str(guide_path))
                city_loaded = True
            except Exception as e:
                logger.warning("Failed to ingest guide for %s: %s", city_name, e)

        # guidebook.json
        guidebook_path = entry / "guidebook.json"
        if guidebook_path.exists():
            try:
                ingest_guidebook(city_name, str(guidebook_path))
                city_loaded = True
            except Exception as e:
                logger.warning("Failed to ingest guidebook for %s: %s", city_name, e)

        # poi_knowledge.json (unified knowledge base)
        knowledge_path = entry / "poi_knowledge.json"
        if knowledge_path.exists():
            try:
                ingest_poi_knowledge(city_name, str(knowledge_path))
                city_loaded = True
            except Exception as e:
                logger.warning("Failed to ingest poi_knowledge for %s: %s", city_name, e)

        # city_tips.json (from XHS extraction)
        tips_path = entry / "city_tips.json"
        if tips_path.exists():
            try:
                ingest_city_tips(city_name, str(tips_path))
                city_loaded = True
            except Exception as e:
                logger.warning("Failed to ingest XHS tips for %s: %s", city_name, e)

        if city_loaded:
            cities_loaded += 1

    _build_idf()
    _ready = True
    logger.info(
        "RAG ready: %d cities, %d chunks indexed",
        cities_loaded,
        len(_corpus),
    )
    return cities_loaded


def init_city_rag(data_dir: str = "data", city: str = "") -> bool:
    """Initialize RAG data for a single city.

    This keeps Render free-tier planning requests from loading all city guide
    data into memory just to answer one city itinerary.
    """
    global _ready
    norm_city = _normalize_city(city)
    if not norm_city:
        return False
    if norm_city in _indexed_cities:
        _ready = True
        return True

    entry = Path(data_dir) / norm_city
    if not entry.is_dir():
        logger.warning("RAG city directory not found: %s", entry)
        return False

    city_loaded = False

    guide_path = entry / "city_guide.json"
    if guide_path.exists():
        try:
            ingest_city_guide(norm_city, str(guide_path))
            city_loaded = True
        except Exception as e:
            logger.warning("Failed to ingest guide for %s: %s", norm_city, e)

    guidebook_path = entry / "guidebook.json"
    if guidebook_path.exists():
        try:
            ingest_guidebook(norm_city, str(guidebook_path))
            city_loaded = True
        except Exception as e:
            logger.warning("Failed to ingest guidebook for %s: %s", norm_city, e)

    knowledge_path = entry / "poi_knowledge.json"
    if knowledge_path.exists():
        try:
            ingest_poi_knowledge(norm_city, str(knowledge_path))
            city_loaded = True
        except Exception as e:
            logger.warning("Failed to ingest poi_knowledge for %s: %s", norm_city, e)

    tips_path = entry / "city_tips.json"
    if tips_path.exists():
        try:
            ingest_city_tips(norm_city, str(tips_path))
            city_loaded = True
        except Exception as e:
            logger.warning("Failed to ingest XHS tips for %s: %s", norm_city, e)

    if city_loaded:
        _build_idf()
        _ready = True
        logger.info(
            "RAG city ready: %s, %d total chunks indexed",
            norm_city,
            len(_corpus),
        )
    return city_loaded


def get_index_stats() -> dict:
    """Return current index statistics."""
    return {
        "ready": _ready,
        "skip": _skip,
        "cities": len(_indexed_cities),
        "chunks": len(_corpus),
        "indexed_cities": sorted(_indexed_cities),
    }


