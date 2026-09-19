from langchain_core.messages import HumanMessage
from langchain_community.chat_models import ChatOllama
import json 

def recommend_activities(state):
    llm = ChatOllama(model="llama3.2", base_url="http://localhost:11434")
    prompt = f"""
    Based on the following preferences and itinerary, suggest unique local activities:
    Preferences: {json.dumps(state['preferences'], indent=2)}
    Itinerary: {state['itinerary']}

    Provide suggestions in bullet points for each day if possible.
    """
    try:
        result = llm.invoke([HumanMessage(content=prompt)]).content
        return {"activity_suggestions": result.strip()}
    except Exception as e:
        return {"activity_suggestions": "", "warning": str(e)}
