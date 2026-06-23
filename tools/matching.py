"""Centralized must_visit matching utilities.

Provides a consistent matching strategy across poi_agent, scheduler_agent,
reviewer_agent, and clustering, replacing scattered `mv in name` patterns.
"""
from typing import Optional

_SHORT_KEYWORD_EXCLUDED_NAME_TERMS = (
    "伴手礼", "纪念品", "文创", "冰箱贴", "礼品", "小店",
    "专卖店", "专营店", "土特产", "特产店", "礼品饰品店", "核雕",
)
_SHORT_KEYWORD_MAX_EXTRA_CHARS = 8


def _compact_landmark_name(text: str) -> str:
    if "碑" not in (text or ""):
        return (text or "").strip()
    compact = (text or "").replace("人民", "").replace("纪念", "")
    return compact.strip()


def _is_bounded_name_match(keyword: str, name: str) -> bool:
    if not keyword or len(keyword) < 2 or keyword not in name:
        return False
    if any(term in name for term in _SHORT_KEYWORD_EXCLUDED_NAME_TERMS):
        return False
    return len(name) <= len(keyword) + _SHORT_KEYWORD_MAX_EXTRA_CHARS


def match_must_visit(keyword: str, pois: list[dict]) -> list[dict]:
    """Match a must_visit keyword against POI list with priority:

    1. Exact name match
    2. ID match
    3. Bounded substring match (keyword len >= 2, target name <= keyword len + 4)

    Returns matched POIs or empty list if no match.
    """
    if not keyword or not pois:
        return []

    # 1. Exact name match
    exact = [p for p in pois if p.get("name") == keyword]
    if exact:
        return exact

    # 2. ID match
    by_id = [p for p in pois if p.get("id") == keyword]
    if by_id:
        return by_id

    # Landmark aliases such as "解放碑" -> "人民解放纪念碑".
    compact_keyword = _compact_landmark_name(keyword)
    compact_name_matches = [
        p for p in pois
        if compact_keyword
        and compact_keyword == _compact_landmark_name(p.get("name", ""))
    ]
    if compact_name_matches:
        return compact_name_matches

    # 3. Bounded substring match
    substring_matches = [
        p for p in pois
        if _is_bounded_name_match(keyword, p.get("name", ""))
    ]
    if substring_matches:
        return substring_matches

    return []


def is_must_visit_covered(keyword: str, planned_names: set[str], planned_ids: Optional[set[str]] = None) -> bool:
    """Check if a must_visit keyword is covered by the planned stops.

    Uses the same priority logic as match_must_visit but against name/id sets.
    """
    if not keyword:
        return True

    # Exact name
    if keyword in planned_names:
        return True

    # ID
    if planned_ids and keyword in planned_ids:
        return True

    compact_keyword = _compact_landmark_name(keyword)
    if compact_keyword and any(compact_keyword == _compact_landmark_name(name) for name in planned_names):
        return True

    # Bounded substring
    for name in planned_names:
        if _is_bounded_name_match(keyword, name):
            return True

    return False
