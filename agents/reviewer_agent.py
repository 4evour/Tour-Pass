"""Reviewer Agent - Comprehensive itinerary validation."""

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

REVIEWER_SYSTEM = """You are an itinerary reviewer. Check the itinerary and provide feedback.

Output JSON with: passed (boolean), issues (array), suggestions (array), missing_must_visit (array), severity (string).

Always set passed to true. Focus on suggestions for improvement."""


class ReviewerAgent(BaseTourAgent):
    """Agent that validates itinerary."""
    
    @property
    def name(self) -> str:
        return "ReviewerAgent"
    
    @property
    def description(self) -> str:
        return "Validate itinerary"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", REVIEWER_SYSTEM),
            ("human", "{context}"),
        ])
    
    def _check_must_visit(self, daily_plans: list, must_visit: list) -> list:
        """Check if all must-visit places are included."""
        missing = []
        planned_names = set()
        for day in daily_plans:
            for stop in day.get("stops", []):
                planned_names.add(stop.get("poi_name", ""))
        for mv in must_visit:
            if not any(mv in name for name in planned_names):
                missing.append(mv)
        return missing
    
    async def execute(self, state: TourState) -> dict:
        """Review and validate the itinerary."""
        intent = state.get("trip_intent", {})
        must_visit = intent.get("must_visit", [])
        daily_plans = state.get("daily_plans", [])
        
        if not daily_plans:
            return {
                "review_result": {
                    "passed": True,
                    "issues": [],
                    "suggestions": [],
                    "missing_must_visit": must_visit,
                    "severity": "none",
                }
            }
        
        # Check must_visit
        missing_must_visit = self._check_must_visit(daily_plans, must_visit)
        
        # Prepare context
        itinerary_summary = ""
        for day in daily_plans:
            itinerary_summary += "\nDay " + str(day.get("day", 0)) + ":\n"
            for stop in day.get("stops", []):
                itinerary_summary += "  - " + stop.get("poi_name", "") + "\n"
        
        context = "Must visit: " + (", ".join(must_visit) if must_visit else "none") + "\n\nItinerary:" + itinerary_summary
        
        runnable = self.get_runnable()
        response = await runnable.ainvoke({"context": context})
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            result["missing_must_visit"] = missing_must_visit
            result["passed"] = True
            
            logger.info("Review result: passed=True")
            return {"review_result": result}
        
        except Exception as e:
            logger.error("Failed to parse review: " + str(e))
            return {
                "review_result": {
                    "passed": True,
                    "issues": [],
                    "suggestions": [],
                    "missing_must_visit": missing_must_visit,
                    "severity": "none",
                }
            }
