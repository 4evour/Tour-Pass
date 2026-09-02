import sys, os, asyncio, traceback
sys.stdout.reconfigure(encoding='utf-8')
try:
    from dotenv import load_dotenv
    load_dotenv('agent/.env'); load_dotenv('.env')
except: pass

from agents.reviewer_agent import ReviewerAgent
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    api_key=os.getenv("DEEPSEEK_API_KEY", ""),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    temperature=0.3,
)

async def test():
    agent = ReviewerAgent(llm)
    state = {
        "trip_intent": {"city": "广州", "must_visit": ["广州塔", "陈家祠"]},
        "daily_plans": [
            {
                "day": 1, "theme": "文化",
                "stops": [
                    {"poi_name": "广州塔", "start_minutes": 540, "end_minutes": 630, "slot": "morning"},
                    {"poi_name": "陈家祠", "start_minutes": 810, "end_minutes": 870, "slot": "afternoon"},
                ],
                "summary": "Day 1",
            }
        ],
        "review_cycle": 0,
    }
    try:
        result = await agent.execute(state)
        print(f"OK: passed={result.get('review_result', {}).get('passed')}")
        print(f"  issues: {result.get('review_result', {}).get('issues')}")
    except Exception as e:
        print(f"FAILED: {e}")
        traceback.print_exc()

asyncio.run(test())
