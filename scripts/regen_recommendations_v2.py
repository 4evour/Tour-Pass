"""Regenerate POI recommendations with differentiation.

Each POI gets a recommendation with two parts:
1. 景点介绍: Core feature/highlight of the attraction
2. 实用建议: Practical tip from one of 6 universal angles

Angles (6 universal):
- 隐藏玩法 (hidden gems / insider tips)
- 最佳时间 (best time to visit)
- 避坑指南 (what to avoid)
- 交通攻略 (transport tips)
- 省钱技巧 (money-saving tips)
- 本地人推荐 (local recommendations)
"""
from __future__ import annotations
import json
import os
import sys
import asyncio
import logging
import re
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Recommendation angles — 6 universal angles that apply to all POI types
ANGLES = [
    {"key": "hidden", "label": "隐藏玩法", "instruction": "给一个本地人才知道的体验技巧"},
    {"key": "timing", "label": "最佳时间", "instruction": "说清楚什么时间段去体验最好及原因"},
    {"key": "avoid", "label": "避坑指南", "instruction": "提醒一个容易踩的坑或常见误区"},
    {"key": "transport", "label": "交通攻略", "instruction": "给一个具体的交通建议（地铁、公交、自驾）"},
    {"key": "saving", "label": "省钱技巧", "instruction": "给一个省钱的小窍门（门票、优惠、免费时段）"},
    {"key": "local", "label": "本地人推荐", "instruction": "给一个本地人才知道的推荐"},
]


def assign_angles(pois: list[dict]) -> list[dict]:
    """Assign a unique angle to each POI, cycling through angles."""
    for i, poi in enumerate(pois):
        angle = ANGLES[i % len(ANGLES)]
        poi["_angle"] = angle
    return pois


async def regenerate_batch(pois: list[dict], batch_size: int = 8) -> list[dict]:
    """Regenerate recommendations for a batch of POIs using LLM."""
    import httpx

    results = []
    for i in range(0, len(pois), batch_size):
        batch = pois[i:i+batch_size]

        # Build prompt for batch
        items_desc = []
        for j, poi in enumerate(batch):
            angle = poi["_angle"]
            items_desc.append(
                f"{j+1}. 【{poi['name']}】(类型:{poi.get('type','')}, 区域:{poi.get('area','')})\n"
                f"   当前简介: {(poi.get('description') or '无')[:100]}\n"
                f"   推荐角度: {angle['label']} — {angle['instruction']}"
            )

        system_prompt = """你是旅行攻略达人。为每个景点写一句推荐语。

【重要要求】推荐语必须包含两部分，用句号连接：
1. 第一部分：景点介绍（用一句话概括景点的核心特色，如高度、建造时间、历史背景、特色等）
2. 第二部分：实用建议（按照指定的"推荐角度"写一句实用建议）

示例：
- 故宫博物院：明清两代皇宫，拥有太和殿、珍宝馆等宏伟建筑。建议早上开门就进，租讲解器沿中轴线游览。
- 雍和宫：北京最大藏传佛教寺院，供奉26米高白檀木弥勒大佛。建议上午去，先领免费香再顺时针参观。
- 广州塔：高600米的地标建筑，可俯瞰珠江两岸美景。建议傍晚去，同时欣赏日落和夜景。

【注意】
- 总长度控制在30-50字
- 语言简洁有力，像本地朋友给的建议
- 不要用"推荐"、"建议"等空话开头
- 直接输出 JSON 数组，不要其他文字

输出格式：
[{"name": "景点名", "recommendation": "推荐语"}]"""

        user_prompt = "请为以下景点各写一句推荐语（必须包含景点介绍+实用建议）：\n\n" + "\n\n".join(items_desc)

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{DEEPSEEK_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": DEEPSEEK_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.8,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()

            # Parse JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            recs = json.loads(text)
            rec_map = {r["name"]: r["recommendation"] for r in recs if "name" in r and "recommendation" in r}

            for poi in batch:
                new_rec = rec_map.get(poi["name"], "")
                if new_rec:
                    poi["recommendation"] = f"{new_rec}"
                    results.append(poi)
                    logger.info(f"  {poi['name']}: {new_rec}")
                else:
                    results.append(poi)
                    logger.warning(f"  {poi['name']}: no recommendation generated")

        except Exception as e:
            logger.error(f"Batch {i//batch_size + 1} failed: {e}")
            for poi in batch:
                results.append(poi)

        # Rate limit
        if i + batch_size < len(pois):
            await asyncio.sleep(1)

    return results


async def regenerate_city(city: str, data_dir: str = "data", test_count: int = 0):
    """Regenerate recommendations for a single city."""
    pois_path = os.path.join(data_dir, city, "pois.json")
    if not os.path.exists(pois_path):
        logger.error(f"File not found: {pois_path}")
        return

    with open(pois_path, "r", encoding="utf-8") as f:
        pois = json.load(f)

    # Filter to attractions only (exclude restaurants and other types)
    targets = [p for p in pois if p.get("type") == "attraction"
               and p.get("description")]

    # Skip POIs that already have non-template recommendations
    template_prefixes = [
        "推荐在", "是当地热门", "适合城市游览", "建议游览",
        "人气评分", "是当地景点",
    ]
    # Also match patterns like "XXX适合城市游览" or "XXX是当地热门"
    template_patterns = [
        r".*适合城市游览.*",
        r".*是当地热门景点.*",
        r".*建议游览\d+分钟左右.*",
        r".*人气评分.*",
    ]

    needs_regen = []
    for p in targets:
        rec = p.get("recommendation", "")
        is_template = any(rec.startswith(prefix) for prefix in template_prefixes)
        if not is_template:
            is_template = any(re.match(pat, rec) for pat in template_patterns)
        if not rec or is_template:
            needs_regen.append(p)

    logger.info(f"{city}: {len(needs_regen)} POIs need recommendation regeneration (of {len(targets)} total)")

    if not needs_regen:
        logger.info(f"{city}: All recommendations look good, skipping")
        return

    # Test mode: only process first N POIs
    if test_count > 0:
        needs_regen = needs_regen[:test_count]
        logger.info(f"{city}: Test mode - processing {len(needs_regen)} POIs")

    # Assign angles
    assign_angles(needs_regen)

    # Regenerate
    updated = await regenerate_batch(needs_regen)

    # Update the original data
    updated_map = {p["name"]: p for p in updated if "recommendation" in p}
    for poi in pois:
        if poi["name"] in updated_map:
            poi["recommendation"] = updated_map[poi["name"]]["recommendation"]

    # Save
    with open(pois_path, "w", encoding="utf-8") as f:
        json.dump(pois, f, ensure_ascii=False, indent=2)

    logger.info(f"{city}: Updated {len(updated_map)} recommendations")


async def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
    city = sys.argv[2] if len(sys.argv) > 2 else ""
    test_count = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    if city:
        await regenerate_city(city, data_dir, test_count)
    else:
        # Process all cities
        for entry in sorted(os.listdir(data_dir)):
            city_dir = os.path.join(data_dir, entry)
            if os.path.isdir(city_dir) and os.path.exists(os.path.join(city_dir, "pois.json")):
                logger.info(f"--- Processing {entry} ---")
                await regenerate_city(entry, data_dir, test_count)


if __name__ == "__main__":
    asyncio.run(main())
