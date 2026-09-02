import sys, os, asyncio
sys.stdout.reconfigure(encoding='utf-8')

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv('agent/.env')
    load_dotenv('.env')
except: pass

print('=== Testing graph construction ===')
from graph import build_tour_graph, create_initial_state
from langchain_openai import ChatOpenAI

api_key = os.getenv("DEEPSEEK_API_KEY", "")
base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

if not api_key:
    print("WARNING: DEEPSEEK_API_KEY not set, using dummy LLM")
    # Create a mock LLM for testing graph structure
    from unittest.mock import MagicMock
    llm = MagicMock()
    llm.invoke = MagicMock(return_value=MagicMock(content='{"city":"test"}'))
else:
    print(f"Using DeepSeek API: {base_url}, model={model}")
    llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=0.3)

graph = build_tour_graph(llm, data_dir="data")
print(f"Graph built successfully: {type(graph).__name__}")

# Check graph nodes
print(f"\nGraph nodes: {list(graph.get_graph().nodes)}")

# Test initial state
state = create_initial_state("test message")
print(f"\nInitial state keys: {list(state.keys())}")
print(f"  city_guides: {state.get('city_guides', 'MISSING')}")
print(f"  has all required keys: {all(k in state for k in ['user_message','trip_intent','city','days','pois','hotels','restaurants','weather','city_guides','daily_plans','selected_hotel','review_result','tickets','errors'])}")
