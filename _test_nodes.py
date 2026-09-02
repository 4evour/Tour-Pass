import sys, os, asyncio, json, time
sys.stdout.reconfigure(encoding='utf-8')

try:
    from dotenv import load_dotenv
    load_dotenv('agent/.env')
    load_dotenv('.env')
except: pass

from agents.intent_agent import IntentAgent
from agents.retrieve_agent import RetrieveAgent
from langchain_openai import ChatOpenAI

api_key = os.getenv("DEEPSEEK_API_KEY", "")
base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=0.3)

async def test_intent():
    agent = IntentAgent(llm)
    state = {"user_message": "广州三天美食之旅，想去广州塔和陈家祠，预算中等"}
    t0 = time.time()
    result = await agent.execute(state)
    elapsed = time.time() - t0
    print(f'IntentAgent: {elapsed:.1f}s')
    print(f'  result: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}')
    return result

async def test_retrieve(intent_result):
    agent = RetrieveAgent()
    state = {
        "trip_intent": intent_result.get("trip_intent"),
        "city": intent_result.get("city", ""),
    }
    t0 = time.time()
    result = await agent.execute(state)
    elapsed = time.time() - t0
    print(f'\nRetrieveAgent: {elapsed:.1f}s')
    guides = result.get("city_guides", [])
    print(f'  guides: {len(guides)} snippets')
    for g in guides[:3]:
        print(f'    - {g[:80]}...')
    return result

async def main():
    intent = await test_intent()
    await test_retrieve(intent)

asyncio.run(main())
