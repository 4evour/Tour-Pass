import sys, os, asyncio, time
sys.stdout.reconfigure(encoding='utf-8')
try:
    from dotenv import load_dotenv
    load_dotenv('agent/.env'); load_dotenv('.env')
except: pass

from graph import build_tour_graph, create_initial_state
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    api_key=os.getenv("DEEPSEEK_API_KEY", ""),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    temperature=0.3,
)
graph = build_tour_graph(llm, data_dir="data")
initial_state = create_initial_state("广州三天美食之旅，想去广州塔和陈家祠，预算中等")
config = {"configurable": {"thread_id": "rest-v2"}, "recursion_limit": 50}
start = time.time()

async def run():
    final = None
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        final = event
    return final

final = asyncio.run(asyncio.wait_for(run(), timeout=60))
elapsed = time.time() - start
print(f'Done in {elapsed:.1f}s\n')

plans = final.get("daily_plans", [])
all_rest = []
print('=== Daily Plans ===')
for day in plans:
    stops = day.get("stops", [])
    for s in stops:
        if s.get("poi_type") == "restaurant":
            all_rest.append(s.get("poi_name",""))
            print(f'  Day{day.get("day")} {s.get("slot")}: {s.get("poi_name")} ({s.get("start_minutes")}-{s.get("end_minutes")})')

print(f'\n=== Dedup: {len(set(all_rest))}/{len(all_rest)} unique ===')
review = final.get("review_result") or {}
print(f'Review: passed={review.get("passed")} issues={len(review.get("issues",[]))}')
for iss in (review.get("issues") or [])[:3]:
    print(f'  [{iss.get("severity")}] {iss.get("detail","")[:80]}')
