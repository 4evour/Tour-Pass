import sys, os, asyncio, json
sys.stdout.reconfigure(encoding='utf-8')

try:
    from dotenv import load_dotenv
    load_dotenv('agent/.env')
    load_dotenv('.env')
except: pass

from agents.scheduler_agent import SchedulerAgent
from langchain_openai import ChatOpenAI

api_key = os.getenv("DEEPSEEK_API_KEY", "")
base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=0.3)

async def test():
    agent = SchedulerAgent(llm)
    
    # Simulate a state with POIs
    state = {
        "trip_intent": {"city": "广州", "days": 3, "pace": "balanced", "must_visit": ["广州塔"]},
        "city": "广州",
        "days": 3,
        "pois": [
            {"id": "amap_001", "name": "广州塔", "type": "attraction", "lat": 23.1, "lng": 113.3, "area": "海珠区", "visit_duration_minutes": 90, "tags": ["景点"], "popularity": 4.9, "recommend_reason": "地标"},
            {"id": "amap_002", "name": "陈家祠", "type": "attraction", "lat": 23.12, "lng": 113.25, "area": "荔湾区", "visit_duration_minutes": 60, "tags": ["文化"], "popularity": 4.7, "recommend_reason": "岭南建筑"},
            {"id": "amap_003", "name": "沙面岛", "type": "attraction", "lat": 23.11, "lng": 113.24, "area": "荔湾区", "visit_duration_minutes": 60, "tags": ["拍照"], "popularity": 4.6, "recommend_reason": "欧式建筑"},
        ],
        "selected_hotel": {"name": "测试酒店", "lat": 23.13, "lng": 113.28},
        "restaurants": [
            {"id": "r001", "name": "银灯食府", "type": "restaurant", "lat": 23.12, "lng": 113.26, "area": "荔湾区"},
        ],
        "weather": [{"condition": "多云", "temperature_high": 30, "temperature_low": 24}],
        "city_guides": ["广州塔建议下午去"],
        "review_result": None,
        "errors": [],
    }
    
    result = await agent.execute(state)
    plans = result.get("daily_plans", [])
    print(f"daily_plans type: {type(plans)}")
    print(f"daily_plans count: {len(plans)}")
    for p in plans:
        print(f"  item type: {type(p)}")
        if isinstance(p, dict):
            print(f"    day: {p.get('day')}, theme: {p.get('theme')}, stops: {len(p.get('stops',[]))}")
            for s in p.get('stops', [])[:2]:
                print(f"      {s.get('slot')}: {s.get('poi_name')} ({s.get('start_minutes')}-{s.get('end_minutes')})")
        else:
            print(f"    VALUE: {str(p)[:100]}")

asyncio.run(test())
