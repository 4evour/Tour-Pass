"""Lightweight RAG pipeline using TF-IDF — no ChromaDB or ML models needed."""
from __future__ import annotations
import json
import logging
import math
import os
import re
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory index
# ---------------------------------------------------------------------------
# Each entry: {"city": str, "category": str, "text": str, "tokens": list[str]}
_corpus: list[dict] = []
_idf: dict[str, float] = {}
_indexed_cities: set[str] = set()
_ready = False
_skip = False


def _tokenize(text: str) -> list[str]:
    """Tokenize Chinese/English text into character bigrams + word tokens."""
    text = text.lower()
    # Extract CJK characters as unigrams + bigrams
    cjk = re.findall(r'[\u4e00-\u9fff]', text)
    # Extract word tokens (latin/digits)
    words = re.findall(r'[a-z0-9]+', text)
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
    _idf = {t: math.log((n - freq + 0.5) / (freq + 0.5) + 1) for t, freq in df.items()}


def _bm25_score(query_tokens: list[str], doc_tokens: list[str],
                k1: float = 1.5, b: float = 0.75) -> float:
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
# Public interface (drop-in compatible with ChromaDB version)
# ---------------------------------------------------------------------------

def is_rag_ready() -> bool:
    return _ready and not _skip


def mark_rag_ready():
    global _ready
    _ready = True


def mark_rag_skip():
    global _skip
    _skip = True
    logger.info("RAG marked as skipped")


def _add_chunk(city: str, category: str, text: str):
    """Add a text chunk to the in-memory corpus."""
    _corpus.append({
        "city": city,
        "category": category,
        "text": text,
        "tokens": _tokenize(text),
    })


def ingest_city_guide(city: str, guide_path: str) -> int:
    """Load a city_guide.json into the TF-IDF index."""
    if not os.path.exists(guide_path):
        logger.warning(f"Guide file not found: {guide_path}")
        return 0

    with open(guide_path, "r", encoding="utf-8") as f:
        guide = json.load(f)

    category_labels = {
        "best_routes": "最佳路线",
        "timing_tips": "时间建议",
        "crowd_tips": "避坑建议",
        "food_tips": "美食推荐",
        "transport_tips": "交通建议",
        "seasonal_tips": "季节建议",
        "hidden_gems": "隐藏玩法",
    }

    count = 0
    for category, label in category_labels.items():
        for i, tip in enumerate(guide.get(category, [])):
            text = f"【{city}{label}】{tip}"
            _add_chunk(city, category, text)
            count += 1

    _indexed_cities.add(city)
    logger.info(f"Indexed {count} guide chunks for {city}")
    return count


def ingest_guidebook(city: str, guidebook_path: str) -> int:
    """Load a guidebook.json (POI descriptions) into the TF-IDF index."""
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

    logger.info(f"Indexed {count} POI descriptions for {city}")
    return count


def search_guides(city: str, query: str, top_k: int = 5) -> list[str]:
    """Retrieve relevant city guide snippets for a query using BM25."""
    if not is_rag_ready():
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # Filter to matching city
    candidates = [doc for doc in _corpus if doc["city"] == city]
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


def search_guides_broad(city: str, categories: list[str] | None = None,
                         top_k: int = 10) -> list[str]:
    """Retrieve guide snippets by category without a specific query."""
    if not is_rag_ready():
        return []

    candidates = [doc for doc in _corpus if doc["city"] == city]
    if categories:
        candidates = [doc for doc in candidates if doc["category"] in categories]

    return [doc["text"] for doc in candidates[:top_k]]


def init_rag(data_dir: str = "data"):
    """Initialize RAG by loading all city data. Call once at startup."""
    global _ready, _skip
    if _ready:
        return

    try:
        cities_loaded = 0
        for entry in os.listdir(data_dir):
            city_dir = os.path.join(data_dir, entry)
            if not os.path.isdir(city_dir):
                continue
            guide_path = os.path.join(city_dir, "city_guide.json")
            guidebook_path = os.path.join(city_dir, "guidebook.json")
            city_loaded = False
            try:
                if os.path.exists(guide_path):
                    ingest_city_guide(entry, guide_path)
                    city_loaded = True
            except Exception as e:
                logger.warning(f"Failed to ingest guide for {entry}: {e}")
            try:
                if os.path.exists(guidebook_path):
                    ingest_guidebook(entry, guidebook_path)
                    city_loaded = True
            except Exception as e:
                logger.warning(f"Failed to ingest guidebook for {entry}: {e}")
            if city_loaded:
                cities_loaded += 1

        _build_idf()
        _ready = True
        logger.info(f"Lightweight RAG ready: {cities_loaded} cities, "
                     f"{len(_corpus)} chunks indexed")
    except Exception as e:
        logger.warning(f"RAG init failed: {e}")
        _skip = True