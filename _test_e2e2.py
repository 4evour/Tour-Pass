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

user_msg = "广州三天美食之旅，想去广州塔和陈家祠，预算中等"
initial_state = create_initial_state(user_msg)

print(f'Test: {user_msg}\n')

config = {"configurable": {"thread_id": "e2e-test"}, "recursion_limit": 50}
start = time.time()

async def run():
    final = None
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        final = event
        # Quick progress log
        for k in ('trip_intent', 'city_guides', 'pois', 'selected_hotel',
                   'weather', 'restaurants', 'daily_plans', 'review_result', 'tickets'):
            v = event.get(k)
            if v:
                if isinstance(v, list):
                    print(f'  [{k}] {len(v)} items')
                elif isinstance(v, dict):
                    name = v.get('city', v.get('name', v.get('passed', '')))
                    print(f'  [{k}] {name}')
    return final

try:
    final = asyncio.run(asyncio.wait_for(run(), timeout=90))
    elapsed = time.time() - start
    print(f'\nDone in {elapsed:.1f}s')

    if final:
        intent = final.get('trip_intent', {})
        print(f'\n=== Summary ===')
        print(f'  city={intent.get("city")} days={intent.get("days")} pace={intent.get("pace")}')
        print(f'  interests={intent.get("interests")} must_visit={intent.get("must_visit")}')
        print(f'  guides={len(final.get("city_guides",[]))}')
        print(f'  pois={len(final.get("pois",[]))}')
        hotel = final.get("selected_hotel") or {}
        print(f'  hotel={hotel.get("name","none")}')
        print(f'  weather={len(final.get("weather",[]))}d')
        print(f'  restaurants={len(final.get("restaurants",[]))}')
        plans = final.get("daily_plans", [])
        print(f'  daily_plans={len(plans)}d')
        for day in plans:
            stops = day.get("stops", [])
            names = [s.get("poi_name","") for s in stops[:4]]
            print(f'    Day{day.get("day")}: {day.get("theme")} -> {", ".join(names)}')
        review = final.get("review_result") or {}
        print(f'  review: passed={review.get("passed")} issues={len(review.get("issues",[]))}')
        print(f'  tickets={len(final.get("tickets",[]))}')
        errs = final.get("errors", [])
        if errs:
            print(f'  ERRORS: {errs[:3]}')
except asyncio.TimeoutError:
    print(f'\nTIMEOUT after 90s')
except Exception as e:
    print(f'\nERROR: {e}')
    import traceback
    traceback.print_exc()
