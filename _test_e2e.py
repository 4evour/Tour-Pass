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

print(f'Test input: {user_msg}')
print(f'Running pipeline...\n')

config = {"configurable": {"thread_id": "test-e2e"}, "recursion_limit": 50}
start = time.time()

async def run():
    final_state = None
    node_log = []
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        final_state = event
        # Log which nodes produced output
        for key in event:
            if key in ('trip_intent', 'pois', 'hotels', 'restaurants', 'weather',
                       'city_guides', 'daily_plans', 'selected_hotel', 'review_result',
                       'tickets'):
                val = event[key]
                if val:
                    if isinstance(val, list):
                        node_log.append(f'  {key}: {len(val)} items')
                    elif isinstance(val, dict):
                        node_log.append(f'  {key}: {list(val.keys())[:3]}...')
                    else:
                        node_log.append(f'  {key}: {str(val)[:50]}')
    return final_state, node_log

final, log = asyncio.run(run())
elapsed = time.time() - start

print(f'Pipeline completed in {elapsed:.1f}s\n')
print('=== Node outputs ===')
for line in log:
    print(line)

if final:
    print(f'\n=== Final state summary ===')
    intent = final.get('trip_intent', {})
    print(f'  city: {intent.get("city", "?")}')
    print(f'  days: {intent.get("days", "?")}')
    print(f'  pace: {intent.get("pace", "?")}')
    print(f'  travelers: {intent.get("travelers", "?")}')
    print(f'  interests: {intent.get("interests", [])}')
    print(f'  must_visit: {intent.get("must_visit", [])}')

    guides = final.get('city_guides', [])
    print(f'  city_guides: {len(guides)} snippets')

    pois = final.get('pois', [])
    print(f'  pois: {len(pois)} attractions')

    hotel = final.get('selected_hotel', {})
    print(f'  hotel: {hotel.get("name", "none")}')

    weather = final.get('weather', [])
    print(f'  weather: {len(weather)} days')

    restaurants = final.get('restaurants', [])
    print(f'  restaurants: {len(restaurants)}')

    plans = final.get('daily_plans', [])
    print(f'  daily_plans: {len(plans)} days')
    for day in plans:
        stops = day.get('stops', [])
        print(f'    Day {day.get("day")}: {day.get("theme")} - {len(stops)} stops')
        for s in stops[:3]:
            print(f'      {s.get("slot")}: {s.get("poi_name")} ({s.get("start_minutes")}-{s.get("end_minutes")})')

    review = final.get('review_result', {})
    print(f'  review: passed={review.get("passed")}, issues={len(review.get("issues", []))}')
    missing = review.get('missing_must_visit', [])
    if missing:
        print(f'    missing_must_visit: {missing}')

    tickets = final.get('tickets', [])
    print(f'  tickets: {len(tickets)}')
    for t in tickets[:3]:
        print(f'    {t.get("poi_name")}: {t.get("price_estimate", "?")}')

    errors = final.get('errors', [])
    if errors:
        print(f'  ERRORS: {errors}')
