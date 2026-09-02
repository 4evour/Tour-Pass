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
config = {"configurable": {"thread_id": "rest-test"}, "recursion_limit": 50}
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
all_rest_names = []
print('=== Daily Plans ===')
for day in plans:
    stops = day.get("stops", [])
    rest_stops = [s for s in stops if s.get("poi_type") == "restaurant"]
    attr_stops = [s for s in stops if s.get("poi_type") != "restaurant"]
    rest_names = [s.get("poi_name", "") for s in rest_stops]
    attr_names = [s.get("poi_name", "") for s in attr_stops[:3]]
    all_rest_names.extend(rest_names)
    print(f'  Day{day.get("day")}:')
    print(f'    Attractions: {", ".join(attr_names)}')
    print(f'    Restaurants: {", ".join(rest_names)}')

print(f'\n=== Restaurant Dedup Check ===')
print(f'  All restaurant names: {all_rest_names}')
unique = set(all_rest_names)
print(f'  Unique: {len(unique)} / Total: {len(all_rest_names)}')
if len(unique) == len(all_rest_names):
    print(f'  PASS: No duplicate restaurants across days!')
else:
    dupes = [n for n in all_rest_names if all_rest_names.count(n) > 1]
    print(f'  FAIL: Duplicates found: {set(dupes)}')

review = final.get("review_result") or {}
print(f'\n=== Review ===')
print(f'  passed={review.get("passed")} cycle={final.get("review_cycle",0)}')
if review.get("issues"):
    for iss in review["issues"][:3]:
        print(f'  [{iss.get("severity","")}] {iss.get("type","")}: {iss.get("detail","")[:60]}')
