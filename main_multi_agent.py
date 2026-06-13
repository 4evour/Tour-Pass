"""Tour Pass Multi-Agent System - Entry Point.

Usage:
    python main_multi_agent.py
    python main_multi_agent.py --city 长沙 --days 3 --message "我想去长沙玩3天，一定要去橘子洲"
"""

import asyncio
import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from graph import build_tour_graph, create_initial_state

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_planning(
    user_message: str,
    model: str = "gpt-4o-mini",
    data_dir: str = "data",
) -> dict:
    """Run the multi-agent planning pipeline.

    The graph is compiled once and the thread_id is derived from the
    message content to avoid cross-request state pollution.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        return {"error": "OPENAI_API_KEY not set"}

    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.3,
    )

    graph = build_tour_graph(llm, data_dir)
    initial_state = create_initial_state(user_message)
    thread_id = hashlib.sha256(user_message.encode()).hexdigest()[:16]
    config = {"configurable": {"thread_id": thread_id}}

    logger.info("Starting planning for: %s...", user_message[:50])

    final_state = None
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        final_state = event
        errors = event.get("errors", [])
        for err in errors:
            logger.warning("Error: %s", err)

    if final_state:
        logger.info("Planning completed successfully")
        return final_state
    logger.error("Planning failed - no final state")
    return {"error": "Planning failed"}


def format_output(state: dict) -> str:
    """Format the planning result as readable text."""
    lines: list[str] = []

    intent = state.get("trip_intent", {})
    if intent:
        lines.append(f"📍 目的地: {intent.get('city', '')}")
        lines.append(f"📅 天数: {intent.get('days', 3)}天")
        if intent.get("must_visit"):
            lines.append(f"⭐ 必去: {', '.join(intent['must_visit'])}")
        lines.append("")

    weather = state.get("weather", [])
    if weather:
        lines.append("🌤️ 天气预报:")
        for i, w in enumerate(weather):
            lo = w.get("temperature_low", "?")
            hi = w.get("temperature_high", "?")
            lines.append(f"  第{i + 1}天: {w.get('condition', '')} {lo}-{hi}°C")
        lines.append("")

    hotel = state.get("selected_hotel")
    if hotel:
        lines.append(f"🏨 推荐酒店: {hotel.get('name', '')} ({hotel.get('area', '')})")
        lines.append("")

    daily_plans = state.get("daily_plans", [])
    if daily_plans:
        lines.append("📋 行程安排:")
        for day in daily_plans:
            lines.append(f"\n第{day.get('day', 0)}天 - {day.get('theme', '')}")
            lines.append(day.get("summary", ""))
            for stop in day.get("stops", []):
                sm = stop.get("start_minutes", 0)
                em = stop.get("end_minutes", 0)
                lines.append(f"  {sm // 60:02d}:{sm % 60:02d}-{em // 60:02d}:{em % 60:02d} {stop.get('poi_name', '')}")
                if stop.get("reason"):
                    lines.append(f"    └─ {stop['reason']}")

    restaurants = state.get("restaurants", [])
    if restaurants:
        lines.append("\n🍽️ 推荐餐厅:")
        for r in restaurants:
            lines.append(f"  第{r.get('day', '')}天 {r.get('meal_type', '')}: {r.get('name', '')} (人均{r.get('avg_price', 0)}元)")

    review = state.get("review_result")
    if review:
        lines.append(f"\n✅ 审核结果: {'通过' if review.get('passed') else '需要调整'} (severity: {review.get('severity', 'none')})")
        for issue in review.get("issues", []):
            lines.append(f"  ⚠️ [{issue.get('severity', '')}] {issue.get('detail', '')}")

    tickets = state.get("tickets", [])
    if tickets:
        lines.append("\n🎫 门票信息:")
        for t in tickets:
            price = t.get("price_estimate", "价格待查")
            lines.append(f"  {t.get('poi_name', '')}: {price}")
            if t.get("booking_tip"):
                lines.append(f"    └─ {t['booking_tip']}")

    errors = state.get("errors", [])
    if errors:
        lines.append("\n⚠️ 警告:")
        for err in errors:
            lines.append(f"  - {err}")

    return "\n".join(lines)


async def interactive_mode(data_dir: str = "data"):
    """Run in interactive mode."""
    print("=" * 60)
    print("🗺️ Tour Pass Multi-Agent Planning System v2.1")
    print("=" * 60)
    print("输入 'quit' 或 'q' 退出\n")

    while True:
        user_input = input("👤 请输入您的旅行需求: ").strip()
        if user_input.lower() in {"quit", "q", "exit"}:
            print("👋 再见！")
            break
        if not user_input:
            continue
        result = await run_planning(user_input, data_dir=data_dir)
        if "error" in result:
            print(f"❌ 错误: {result['error']}")
        else:
            print("\n" + format_output(result))
        print("\n" + "-" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Tour Pass Multi-Agent Planning System")
    parser.add_argument("--message", "-m", help="User message for planning")
    parser.add_argument("--city", "-c", help="Destination city")
    parser.add_argument("--days", "-d", type=int, default=3, help="Number of days")
    parser.add_argument("--model", default="gpt-4o-mini", help="LLM model name")
    parser.add_argument("--data-dir", default="data", help="Data directory")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    if args.interactive:
        asyncio.run(interactive_mode(args.data_dir))
    elif args.message:
        result = asyncio.run(run_planning(args.message, args.model, args.data_dir))
        if "error" in result:
            print(f"Error: {result['error']}")
            sys.exit(1)
        print(format_output(result))
    elif args.city:
        message = f"我想去{args.city}玩{args.days}天"
        result = asyncio.run(run_planning(message, args.model, args.data_dir))
        if "error" in result:
            print(f"Error: {result['error']}")
            sys.exit(1)
        print(format_output(result))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
