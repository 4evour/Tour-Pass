import sys, os, asyncio, time, logging
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.DEBUG, format='%(name)s %(message)s', stream=sys.stderr)
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
initial_state = create_initial_state("广州三天美食之旅")
config = {"configurable": {"thread_id": "e2e-tb"}, "recursion_limit": 50}

async def run():
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        pass

asyncio.run(asyncio.wait_for(run(), timeout=30))
