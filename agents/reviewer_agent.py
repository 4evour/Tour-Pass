"""Reviewer Agent - Comprehensive itinerary validation.

This agent checks:
1. Must-visit places inclusion
2. Time conflicts
3. Schedule density
4. Weather appropriateness
5. Geographic efficiency
"""

import json
import logging
from collections import defaultdict

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

REVIEWER_SYSTEM = """You are an itinerary reviewer and validator.

Check the planned itinerary against these constraints:

1. MUST-VISIT CHECK:
   - All must_visit places MUST be included
   - They should have adequate time allocated

2. TIME CONFLICT CHECK:
   - No overlapping time slots
   - Sufficient travel time between stops
   - Realistic visit durations

3. SCHEDULE DENSITY CHECK:
   - Not too many activities per day
   - Adequate breaks between activities
   - Consider pace preference (relaxed/balanced/intense)

4. WEATHER APPROPRIATENESS:
   - Outdoor activities on sunny days
   - Indoor alternatives for rainy days

5. GEOGRAPHIC EFFICIENCY:
   - Activities clustered by area
   - Minimize cross-city travel

Output format (JSON):
{
  "passed": true/false,
  "issues": ["Issue 1", "Issue 2"],
  "suggestions": ["Suggestion 1", "Suggestion 2"],
  "missing_must_visit": ["Missing place 1"],
  "severity": "none/minor/major/critical"
}

severity levels:
- none: No issues, can proceed
- minor: Suggestions but can proceed
- major: Should revise before proceeding
- critical: Must revise (missing must-visit, time conflicts)"""


class ReviewerAgent(BaseTourAgent):
    """Agent that validates itinerary with comprehensive checks."""
    
    @property
    def name(self) -> str:
        return "ReviewerAgent"
    
    @property
    def description(self) -> str:
        return "Validate itinerary with comprehensive constraint checking"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", REVIEWER_SYSTEM),
            ("human", "{context}"),
        ])
    
    def _check_time_conflicts(self, daily_plans: list[dict]) -> list[str]:
        """Check for time conflicts in the itinerary."""
        issues = []
        
        for day in daily_plans:
            stops = day.get("stops", [])
            
            for i in range(len(stops) - 1):
                current = stops[i]
                next_stop = stops[i + 1]
                
                current_end = current.get("end_minutes", 0)
                next_start = next_stop.get("start_minutes", 0)
                
                if current_end > next_start:
                    issues.append(
                        f"第{day.get('day', 0)}天: {current.get('poi_name', '')} "
                        f"({current_end // 60}:{current_end % 60:02d}) 与 "
                        f"{next_stop.get('poi_name', '')} ({next_start // 60}:{next_start % 60:02d}) "
                        f"时间冲突"
                    )
        
        return issues
    
    def _check_schedule_density(self, daily_plans: list[dict], pace: str) -> list[str]:
        """Check if schedule is too dense."""
        issues = []
        
        max_stops = {"relaxed": 4, "balanced": 6, "intense": 8}.get(pace, 6)
        
        for day in daily_plans:
            stops = day.get("stops", [])
            attractions = [s for s in stops if s.get("poi_type") in ("attraction", "nightlife")]
            
            if len(attractions) > max_stops:
                issues.append(
                    f"第{day.get('day', 0)}天: 安排了{len(attractions)}个景点，"
                    f"超过{pace}节奏建议的{max_stops}个"
                )
        
        return issues
    
    def _check_must_visit(self, daily_plans: list[dict], must_visit: list[str]) -> list[str]:
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
        intent = state.get("intent", {})
        must_visit = intent.get("must_visit", [])
        pace = intent.get("pace", "balanced")
        daily_plans = state.get("daily_plans", [])
        weather = state.get("weather", [])
        
        if not daily_plans:
            return {
                "review_result": {
                    "passed": False,
                    "issues": ["No itinerary to review"],
                    "suggestions": [],
                    "missing_must_visit": must_visit,
                    "severity": "critical",
                }
            }
        
        # Automated checks
        logger.info("Running automated checks...")
        
        time_conflicts = self._check_time_conflicts(daily_plans)
        density_issues = self._check_schedule_density(daily_plans, pace)
        missing_must_visit = self._check_must_visit(daily_plans, must_visit)
        
        # Prepare itinerary summary for LLM
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
        
        # Weather info
        weather_info = ""
        if weather:
            weather_info = "\n天气预报:\n" + "\n".join([
                f"  第{i+1}天: {w.get('condition', '')}, {w.get('suggestion', '')}"
                for i, w in enumerate(weather)
            ])
        
        # Automated check results
        auto_check = ""
        if time_conflicts:
            auto_check += f"\n自动检查发现时间冲突:\n" + "\n".join(f"  - {c}" for c in time_conflicts)
        if density_issues:
            auto_check += f"\n自动检查发现密度问题:\n" + "\n".join(f"  - {d}" for d in density_issues)
        if missing_must_visit:
            auto_check += f"\n自动检查发现缺少必去景点:\n" + "\n".join(f"  - {m}" for m in missing_must_visit)
        
        context = f"""必去景点: {', '.join(must_visit) if must_visit else '无'}
节奏偏好: {pace}
{weather_info}

计划行程:
{itinerary_summary}
{auto_check}

请综合评估行程质量。"""
        
        runnable = self.get_runnable()
        response = await runnable.ainvoke({"context": context})
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            
            # Merge automated check results
            all_issues = result.get("issues", []) + time_conflicts + density_issues
            if missing_must_visit:
                all_issues.extend([f"缺少必去景点: {m}" for m in missing_must_visit])
            
            result["issues"] = all_issues
            result["missing_must_visit"] = missing_must_visit
            
            # Determine severity
            if missing_must_visit:
                result["severity"] = "critical"
                result["passed"] = False
            elif time_conflicts:
                result["severity"] = "major"
                result["passed"] = False
            elif density_issues:
                result["severity"] = "minor"
                result["passed"] = True  # Can proceed with warnings
            else:
                result["severity"] = "none"
                result["passed"] = True
            
            logger.info(f"Review result: passed={result['passed']}, severity={result['severity']}, "
                       f"issues={len(result['issues'])}")
            
            return {"review_result": result}
        
        except Exception as e:
            logger.error(f"Failed to parse review: {e}")
            # Fallback: use automated checks only
            passed = len(missing_must_visit) == 0 and len(time_conflicts) == 0
            
            return {
                "review_result": {
                    "passed": passed,
                    "issues": time_conflicts + density_issues + [f"缺少: {m}" for m in missing_must_visit],
                    "suggestions": [],
                    "missing_must_visit": missing_must_visit,
                    "severity": "critical" if missing_must_visit else ("major" if time_conflicts else "none"),
                }
            }
