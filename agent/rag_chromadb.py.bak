"""RAG pipeline for city guide retrieval using ChromaDB."""
from __future__ import annotations
import json
import logging
import os
from typing import Optional

from .config import CHROMA_PERSIST_DIR, CHROMA_COLLECTION

logger = logging.getLogger(__name__)

# Lazy-init ChromaDB client
_chroma_client = None
_collection = None


def _get_collection():
    global _chroma_client, _collection
    if _collection is not None:
        return _collection

    try:
        import chromadb
        from chromadb.config import Settings
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _chroma_client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB collection '{CHROMA_COLLECTION}' ready, "
                     f"count={_collection.count()}")
        return _collection
    except Exception as e:
        logger.warning(f"ChromaDB init failed: {e}. RAG will be disabled.")
        mark_rag_skip()
        return None


# Flag to track if RAG is ready
_rag_ready = False
_rag_skip = False  # Set to True if ChromaDB init fails (e.g., model download)


def is_rag_ready() -> bool:
    """Check if RAG collection is available without blocking."""
    global _rag_ready, _rag_skip
    if _rag_skip:
        return False
    if _rag_ready:
        return True
    return False


def mark_rag_ready():
    """Mark RAG as ready after successful init."""
    global _rag_ready
    _rag_ready = True


def mark_rag_skip():
    """Mark RAG to be skipped (e.g., model download in progress)."""
    global _rag_skip
    _rag_skip = True
    logger.info("RAG marked as skipped (model download or init failure)")


def ingest_city_guide(city: str, guide_path: str) -> int:
    """Ingest a city_guide.json into ChromaDB. Returns number of chunks added."""
    collection = _get_collection()
    if collection is None:
        return 0

    if not os.path.exists(guide_path):
        logger.warning(f"Guide file not found: {guide_path}")
        return 0

    with open(guide_path, "r", encoding="utf-8") as f:
        guide = json.load(f)

    chunks = []

    # Best routes
    for i, route in enumerate(guide.get("best_routes", [])):
        chunks.append({
            "id": f"{city}_route_{i}",
            "text": f"【{city}最佳路线】{route}",
            "metadata": {"city": city, "category": "best_routes"},
        })

    # Timing tips
    for i, tip in enumerate(guide.get("timing_tips", [])):
        chunks.append({
            "id": f"{city}_timing_{i}",
            "text": f"【{city}时间建议】{tip}",
            "metadata": {"city": city, "category": "timing_tips"},
        })

    # Crowd tips
    for i, tip in enumerate(guide.get("crowd_tips", [])):
        chunks.append({
            "id": f"{city}_crowd_{i}",
            "text": f"【{city}避坑建议】{tip}",
            "metadata": {"city": city, "category": "crowd_tips"},
        })

    # Food tips
    for i, tip in enumerate(guide.get("food_tips", [])):
        chunks.append({
            "id": f"{city}_food_{i}",
            "text": f"【{city}美食推荐】{tip}",
            "metadata": {"city": city, "category": "food_tips"},
        })

    # Transport tips
    for i, tip in enumerate(guide.get("transport_tips", [])):
        chunks.append({
            "id": f"{city}_transport_{i}",
            "text": f"【{city}交通建议】{tip}",
            "metadata": {"city": city, "category": "transport_tips"},
        })

    # Seasonal tips
    for i, tip in enumerate(guide.get("seasonal_tips", [])):
        chunks.append({
            "id": f"{city}_seasonal_{i}",
            "text": f"【{city}季节建议】{tip}",
            "metadata": {"city": city, "category": "seasonal_tips"},
        })

    # Hidden gems
    for i, tip in enumerate(guide.get("hidden_gems", [])):
        chunks.append({
            "id": f"{city}_gems_{i}",
            "text": f"【{city}隐藏玩法】{tip}",
            "metadata": {"city": city, "category": "hidden_gems"},
        })

    if not chunks:
        return 0

    # Upsert into ChromaDB
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    logger.info(f"Ingested {len(chunks)} chunks for {city}")
    return len(chunks)


def ingest_guidebook(city: str, guidebook_path: str) -> int:
    """Ingest a guidebook.json (POI descriptions) into ChromaDB."""
    collection = _get_collection()
    if collection is None:
        return 0

    if not os.path.exists(guidebook_path):
        return 0

    with open(guidebook_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return 0

    chunks = []
    for i, entry in enumerate(data):
        name = entry.get("name", "")
        desc = entry.get("description", "")
        if not name or not desc:
            continue
        chunks.append({
            "id": f"{city}_poi_{i}",
            "text": f"【{name}】{desc}",
            "metadata": {"city": city, "category": "poi_description", "poi_name": name},
        })

    if chunks:
        collection.upsert(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
        )
        logger.info(f"Ingested {len(chunks)} POI descriptions for {city}")

    return len(chunks)


def search_guides(city: str, query: str, top_k: int = 5) -> list[str]:
    """Retrieve relevant city guide snippets for a query."""
    if not is_rag_ready():
        return []
    try:
        collection = _get_collection()
        if collection is None:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where={"city": city},
        )
        documents = results.get("documents", [[]])
        if documents and documents[0]:
            return documents[0]
        return []
    except Exception as e:
        logger.warning(f"RAG search failed: {e}")
        return []


def search_guides_broad(city: str, categories: list[str] | None = None, top_k: int = 10) -> list[str]:
    """Retrieve guide snippets by category without a specific query."""
    collection = _get_collection()
    if collection is None:
        return []

    try:
        where_filter = {"city": city}
        if categories:
            where_filter["category"] = {"$in": categories}

        results = collection.get(
            where=where_filter,
            limit=top_k,
        )
        return results.get("documents", [])
    except Exception as e:
        logger.warning(f"RAG broad search failed: {e}")
        return []



