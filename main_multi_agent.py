"""Tour Pass Multi-Agent System - Entry Point.

Usage:
    python main.py
    python main.py --city 长沙 --days 3 --message "我想去长沙玩3天，一定要去橘子洲"
"""

import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

# Add project root to path
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
    
    Args:
        user_message: User's natural language request.
        model: LLM model name.
        data_dir: Directory containing city data.
    
    Returns:
        Final state with itinerary.
    """
    # Initialize LLM
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        return {"error": "OPENAI_API_KEY not set"}
    
    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.3,
    )
    
    # Build graph
    memory = MemorySaver()
    graph = build_tour_graph(llm, data_dir, checkpointer=memory)
    
    # Create initial state
    initial_state = create_initial_state(user_message)
    
    # Run graph
    config = {"configurable": {"thread_id": "default"}}
    
    logger.info(f"Starting planning for: {user_message[:50]}...")
    
    final_state = None
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        final_state = event
        
        # Log progress
        if "errors" in event and event["errors"]:
            for err in event["errors"]:
                logger.warning(f"Error: {err}")
    
    if final_state:
        logger.info("Planning completed successfully")
        return final_state
    else:
        logger.error("Planning failed - no final state")
        return {"error": "Planning failed"}


def format_output(state: dict) -> str:
    """Format the planning result as readable text."""
    lines = []
    
    # Intent
    intent = state.get("intent", {})
    if intent:
        lines.append(f"📍 目的地: {intent.get('city', '')}")
        lines.append(f"📅 天数: {intent.get('days', 3)}天")
        if intent.get("must_visit"):
            lines.append(f"⭐ 必去: {', '.join(intent['must_visit'])}")
        lines.append("")
    
    # Weather
    weather = state.get("weather", [])
    if weather:
        lines.append("🌤️ 天气预报:")
        for i, w in enumerate(weather):
            lines.append(f"  第{i+1}天: {w.get('condition', '')} {w.get('temperature_low', 0)}-{w.get('temperature_high', 0)}°C")
        lines.append("")
    
    # Hotel
    hotel = state.get("selected_hotel")
    if hotel:
        lines.append(f"🏨 推荐酒店: {hotel.get('name', '')} ({hotel.get('area', '')})")
        lines.append("")
    
    # Daily plans
    daily_plans = state.get("daily_plans", [])
    if daily_plans:
        lines.append("📋 行程安排:")
        for day in daily_plans:
            lines.append(f"\n第{day.get('day', 0)}天 - {day.get('theme', '')}")
            lines.append(day.get("summary", ""))
            for stop in day.get("stops", []):
                start_h = stop.get("start_minutes", 0) // 60
                start_m = stop.get("start_minutes", 0) % 60
                end_h = stop.get("end_minutes", 0) // 60
                end_m = stop.get("end_minutes", 0) % 60
                lines.append(
                    f"  {start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d} "
                    f"{stop.get('poi_name', '')}"
                )
                if stop.get("reason"):
                    lines.append(f"    └─ {stop['reason']}")
    
    # Restaurants
    restaurants = state.get("restaurants", [])
    if restaurants:
        lines.append("\n🍽️ 推荐餐厅:")
        for r in restaurants:
            day = r.get("day", "")
            meal = r.get("meal_type", "")
            lines.append(f"  第{day}天 {meal}: {r.get('name', '')} (人均{r.get('avg_price', 0)}元)")
    
    # Review
    review = state.get("review_result")
    if review:
        lines.append(f"\n✅ 审核结果: {'通过' if review.get('passed') else '需要调整'}")
        if review.get("issues"):
            for issue in review["issues"]:
                lines.append(f"  ⚠️ {issue}")
    
    # Tickets
    tickets = state.get("tickets", [])
    if tickets:
        lines.append("\n🎫 门票信息:")
        for t in tickets:
            price = f"¥{t['price']}" if t.get("price") else "价格待查"
            lines.append(f"  {t.get('poi_name', '')}: {price}")
            if t.get("notes"):
                lines.append(f"    └─ {t['notes']}")
    
    # Errors
    errors = state.get("errors", [])
    if errors:
        lines.append("\n⚠️ 警告:")
        for err in errors:
            lines.append(f"  - {err}")
    
    return "\n".join(lines)


async def interactive_mode(data_dir: str = "data"):
    """Run in interactive mode."""
    print("=" * 60)
    print("🗺️ Tour Pass Multi-Agent Planning System")
    print("=" * 60)
    print("输入 'quit' 或 'q' 退出")
    print()
    
    while True:
        user_input = input("👤 请输入您的旅行需求: ").strip()
        
        if user_input.lower() in ["quit", "q", "exit"]:
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
        else:
            print(format_output(result))
    elif args.city:
        message = f"我想去{args.city}玩{args.days}天"
        result = asyncio.run(run_planning(message, args.model, args.data_dir))
        if "error" in result:
            print(f"Error: {result['error']}")
            sys.exit(1)
        else:
            print(format_output(result))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
