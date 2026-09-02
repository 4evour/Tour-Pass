import sys, os, asyncio, time
sys.stdout.reconfigure(encoding='utf-8')
try:
    from dotenv import load_dotenv
    load_dotenv('agent/.env'); load_dotenv('.env')
except: pass

import logging
logging.basicConfig(level=logging.INFO, format='%(name)s %(message)s', stream=sys.stderr)

from graph import build_tour_graph, create_initial_state
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    api_key=os.getenv("DEEPSEEK_API_KEY", ""),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    temperature=0.3,
)
graph = build_tour_graph(llm, data_dir="data")
initial_state = create_initial_state("广州三天美食之旅")
config = {"configurable": {"thread_id": "e2e-debug"}, "recursion_limit": 50}

async def run():
    final = None
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        final = event
    return final

final = asyncio.run(asyncio.wait_for(run(), timeout=60))
print(f"Done. plans={len(final.get('daily_plans',[]))} review_passed={final.get('review_result',{}).get('passed')}")
