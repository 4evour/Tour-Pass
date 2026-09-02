import sys, os, asyncio, json, time
sys.stdout.reconfigure(encoding='utf-8')

try:
    from dotenv import load_dotenv
    load_dotenv('agent/.env')
    load_dotenv('.env')
except: pass

from graph import build_tour_graph, create_initial_state
from langchain_openai import ChatOpenAI

api_key = os.getenv("DEEPSEEK_API_KEY", "")
base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=0.3)
graph = build_tour_graph(llm, data_dir="data")

# Run step by step using ainvoke to see intermediate states
user_msg = "广州三天美食之旅"
initial_state = create_initial_state(user_msg)
config = {"configurable": {"thread_id": "debug-1"}, "recursion_limit": 50}

# Just run the first few nodes manually
import traceback

async def run():
    from agents.intent_agent import IntentAgent
    from agents.retrieve_agent import RetrieveAgent
    from agents.poi_agent import PoiAgent
    from agents.scheduler_agent import SchedulerAgent
    from agents.reviewer_agent import ReviewerAgent
    
    # Step 1: Intent
    intent_agent = IntentAgent(llm)
    state = dict(initial_state)
    r = await intent_agent.execute(state)
    state.update(r)
    print(f"1. Intent: city={state.get('city')}, must_visit={state.get('trip_intent',{}).get('must_visit')}")
    
    # Step 2: Retrieve
    retrieve_agent = RetrieveAgent()
    r = await retrieve_agent.execute(state)
    state.update(r)
    print(f"2. Retrieve: {len(state.get('city_guides',[]))} guides")
    
    # Step 3: POI
    poi_agent = PoiAgent(llm, "data")
    r = await poi_agent.execute(state)
    state.update(r)
    pois = state.get("pois", [])
    print(f"3. POI: {len(pois)} items, types: {set(p.get('type') for p in pois)}")
    
    # Step 4: Scheduler
    sched_agent = SchedulerAgent()
    r = await sched_agent.execute(state)
    state.update(r)
    plans = state.get("daily_plans", [])
    print(f"4. Scheduler: {len(plans)} day plans")
    for p in plans:
        print(f"   Day {p.get('day')}: {type(p).__name__}, stops={len(p.get('stops',[]))}")
    
    # Step 5: Reviewer (the failing one)
    rev_agent = ReviewerAgent(llm)
    print(f"\n5. Reviewer input:")
    print(f"   daily_plans type: {type(state.get('daily_plans'))}")
    dp = state.get("daily_plans", [])
    for i, item in enumerate(dp):
        print(f"   item[{i}] type={type(item).__name__}, value={str(item)[:80]}")
    
    try:
        r = await rev_agent.execute(state)
        state.update(r)
        print(f"5. Reviewer: passed={r.get('review_result',{}).get('passed')}")
    except Exception as e:
        print(f"5. Reviewer FAILED: {e}")
        traceback.print_exc()

asyncio.run(run())
