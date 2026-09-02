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
config = {"configurable": {"thread_id": "e2e-final"}, "recursion_limit": 50}
start = time.time()

async def run():
    final = None
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        final = event
    return final

try:
    final = asyncio.run(asyncio.wait_for(run(), timeout=60))
    elapsed = time.time() - start
    print(f'Done in {elapsed:.1f}s\n')
    
    intent = final.get('trip_intent', {})
    plans = final.get("daily_plans", [])
    review = final.get("review_result") or {}
    tickets = final.get("tickets", [])
    hotel = final.get("selected_hotel") or {}
    guides = final.get("city_guides", [])
    errs = final.get("errors", [])
    
    print(f'=== Final Result ===')
    print(f'  city={intent.get("city")} days={intent.get("days")} pace={intent.get("pace")}')
    print(f'  travelers={intent.get("travelers")} budget={intent.get("budget")}')
    print(f'  interests={intent.get("interests")} must_visit={intent.get("must_visit")}')
    print(f'  city_guides: {len(guides)} snippets')
    print(f'  pois: {len(final.get("pois",[]))} attractions')
    print(f'  hotel: {hotel.get("name","none")}')
    print(f'  weather: {len(final.get("weather",[]))}d')
    print(f'  restaurants: {len(final.get("restaurants",[]))}')
    print(f'  daily_plans: {len(plans)}d')
    for day in plans:
        stops = day.get("stops", [])
        names = [s.get("poi_name","") for s in stops]
        print(f'    Day{day.get("day")} ({day.get("theme","")[:15]}): {", ".join(names[:5])}')
    print(f'  review: passed={review.get("passed")} cycle={final.get("review_cycle",0)} severity={review.get("severity","")} issues={len(review.get("issues",[]))}')
    if review.get("issues"):
        for iss in review["issues"][:3]:
            print(f'    - [{iss.get("severity","")}] {iss.get("type","")}: {iss.get("detail","")[:60]}')
    print(f'  tickets: {len(tickets)}')
    for t in tickets[:3]:
        print(f'    {t.get("poi_name")}: {t.get("price_estimate","")}')
    if errs:
        print(f'  errors: {errs[:2]}')
except asyncio.TimeoutError:
    print(f'TIMEOUT')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback; traceback.print_exc()
