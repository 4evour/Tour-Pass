"""Reviewer Agent - Validate itinerary against constraints."""

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

REVIEWER_SYSTEM = """You are an itinerary reviewer and validator.

Your job is to check if the planned itinerary meets all constraints:

CHECK:
1. All must_visit places are included
2. No time conflicts (overlapping time slots)
3. Reasonable travel time between stops
4. Meal breaks are included
5. Weather-appropriate activities
6. Opening hours are respected
7. Daily schedule is not too exhausting

Output format (JSON):
{
  "passed": true/false,
  "issues": ["Issue 1", "Issue 2"],
  "suggestions": ["Suggestion 1", "Suggestion 2"],
  "missing_must_visit": ["Missing place 1"]
}

Be strict about must_visit places - they MUST be included."""


class ReviewerAgent(BaseTourAgent):
    """Agent that validates itinerary against constraints."""
    
    @property
    def name(self) -> str:
        return "ReviewerAgent"
    
    @property
    def description(self) -> str:
        return "Validate itinerary against constraints"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", REVIEWER_SYSTEM),
            ("human", "{context}"),
        ])
    
    async def execute(self, state: TourState) -> dict:
        """Review and validate the itinerary."""
        intent = state.get("intent", {})
        must_visit = intent.get("must_visit", [])
        daily_plans = state.get("daily_plans", [])
        weather = state.get("weather", [])
        
        if not daily_plans:
            return {
                "review_result": {
                    "passed": False,
                    "issues": ["No itinerary to review"],
                    "suggestions": [],
                    "missing_must_visit": must_visit,
                }
            }
        
        # Prepare itinerary summary
        itinerary_summary = ""
        for day in daily_plans:
            itinerary_summary += f"\n第{day.get('day', 0)}天 ({day.get('theme', '')}):\n"
            for stop in day.get("stops", []):
                start_h = stop.get("start_minutes", 0) // 60
                start_m = stop.get("start_minutes", 0) % 60
                end_h = stop.get("end_minutes", 0) // 60
                end_m = stop.get("end_minutes", 0) % 60
                itinerary_summary += (
                    f"  - {start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d} "
                    f"{stop.get('poi_name', '')} ({stop.get('area', '')})\n"
                )
        
        # Prepare weather info
        weather_info = "\n".join([
            f"- 第{i+1}天: {w.get('condition', '')}, {w.get('suggestion', '')}"
            for i, w in enumerate(weather)
        ])
        
        context = f"""必去景点: {', '.join(must_visit) if must_visit else '无'}

天气预报:
{weather_info}

计划行程:
{itinerary_summary}

请检查行程是否符合所有约束。"""
        
        runnable = self.get_runnable()
        response = await runnable.ainvoke({"context": context})
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            
            # Additional check: verify must_visit are actually in the itinerary
            planned_names = set()
            for day in daily_plans:
                for stop in day.get("stops", []):
                    planned_names.add(stop.get("poi_name", ""))
            
            actually_missing = []
            for mv in must_visit:
                if not any(mv in name for name in planned_names):
                    actually_missing.append(mv)
            
            if actually_missing:
                result["passed"] = False
                result["missing_must_visit"] = actually_missing
                result["issues"].append(f"缺少必去景点: {', '.join(actually_missing)}")
            
            logger.info(f"Review result: passed={result.get('passed')}, "
                       f"issues={len(result.get('issues', []))}")
            
            return {"review_result": result}
        
        except Exception as e:
            logger.error(f"Failed to parse review: {e}")
            # Fallback: check must_visit manually
            planned_names = set()
            for day in daily_plans:
                for stop in day.get("stops", []):
                    planned_names.add(stop.get("poi_name", ""))
            
            missing = [mv for mv in must_visit if not any(mv in name for name in planned_names)]
            
            return {
                "review_result": {
                    "passed": len(missing) == 0,
                    "issues": [f"缺少必去景点: {', '.join(missing)}"] if missing else [],
                    "suggestions": [],
                    "missing_must_visit": missing,
                }
            }
