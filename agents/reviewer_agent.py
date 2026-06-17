"""Reviewer Agent - Comprehensive itinerary validation.

Validates itinerary with hard-coded rules + LLM review.
"""

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import LLMAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

REVIEWER_SYSTEM = """You are an itinerary reviewer. Check the itinerary and provide feedback.

Output JSON with: passed (boolean), issues (array), suggestions (array),
missing_must_visit (array), severity (string: none|low|medium|high|critical).

Check for:
1. Time overlap: stops on the same day with overlapping time windows.
2. Unrealistic scheduling: too many stops (>6) or empty days.
3. Logical routing: stops on the same day should be geographically close.
4. Missing context: must_visit places not in the itinerary.
5. Generic issues: vague names, duplicate entries.

Set passed=true ONLY if there are zero critical and zero high severity issues."""


def _safe_get_stops(day) -> list:
    """Safely get stops from a day plan item."""
    if isinstance(day, dict):
        stops = day.get("stops", [])
        if isinstance(stops, list):
            return stops
    return []


class ReviewerAgent(LLMAgent):
    """Validate itinerary with hard-coded rules + LLM review."""

    def __init__(self, llm: BaseChatModel):
        super().__init__(llm)

    @property
    def name(self) -> str:
        return "ReviewerAgent"

    @property
    def description(self) -> str:
        return "Validate itinerary comprehensively"

    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", REVIEWER_SYSTEM),
            ("human", "{context}"),
        ])

    @staticmethod
    def _check_must_visit(daily_plans: list, must_visit: list) -> list:
        planned = set()
        for day in daily_plans:
            for stop in _safe_get_stops(day):
                if isinstance(stop, dict):
                    planned.add(stop.get("poi_name", ""))
        return [mv for mv in must_visit if not any(mv in name for name in planned)]

    def _hard_check(self, daily_plans: list, must_visit: list, missing: list) -> list:
        issues = []

        if missing:
            issues.append({
                "type": "missing_must_visit", "severity": "critical",
                "detail": "Missing: " + ", ".join(missing),
            })

        for day in daily_plans:
            if not isinstance(day, dict):
                continue
            day_num = day.get("day", 0)
            stops = _safe_get_stops(day)

            # Too many stops
            if len(stops) > 6:
                issues.append({
                    "type": "too_many_stops", "severity": "high",
                    "detail": f"Day {day_num}: {len(stops)} stops (max 6).",
                })

            # Empty day
            if not stops:
                issues.append({
                    "type": "empty_day", "severity": "critical",
                    "detail": f"Day {day_num}: no stops.",
                })

            # Time overlap
            for i in range(len(stops)):
                for j in range(i + 1, len(stops)):
                    si, sj = stops[i], stops[j]
                    if not (isinstance(si, dict) and isinstance(sj, dict)):
                        continue
                    si_s = si.get("start_minutes", 0)
                    si_e = si.get("end_minutes", 0)
                    sj_s = sj.get("start_minutes", 0)
                    sj_e = sj.get("end_minutes", 0)
                    if si_s and si_e and sj_s and sj_e and si_s < sj_e and sj_s < si_e:
                        issues.append({
                            "type": "time_overlap", "severity": "high",
                            "detail": f"Day {day_num}: {si.get('poi_name','?')} overlaps {sj.get('poi_name','?')}",
                        })

            # Duplicate POI
            names = [s.get("poi_name", "") for s in stops if isinstance(s, dict)]
            seen = set()
            for n in names:
                if n and n in seen:
                    issues.append({
                        "type": "duplicate_poi", "severity": "low",
                        "detail": f"Day {day_num}: duplicate '{n}'.",
                    })
                seen.add(n)

        return issues

    async def execute(self, state: TourState) -> dict:
        intent = state.get("trip_intent") or {}
        if isinstance(intent, str):
            try:
                intent = json.loads(intent)
            except Exception:
                intent = {}
        must_visit = intent.get("must_visit", []) if isinstance(intent, dict) else []
        daily_plans = state.get("daily_plans", [])

        # Debug: log types
        if daily_plans:
            first = daily_plans[0]
            logger.info("Reviewer debug: daily_plans[0] type=%s, value=%s",
                        type(first).__name__, str(first)[:100])
        if not daily_plans:
            review = {
                "passed": False,
                "issues": [{"type": "empty_itinerary", "severity": "critical", "detail": "No plans."}],
                "suggestions": [], "missing_must_visit": must_visit, "severity": "critical",
            }
            return {"review_result": review, "review_feedback": review,
                    "review_cycle": state.get("review_cycle", 0) + 1}

        missing = self._check_must_visit(daily_plans, must_visit)
        hard_issues = self._hard_check(daily_plans, must_visit, missing)

        # Build context for LLM
        lines = ["Must visit: " + (", ".join(must_visit) if must_visit else "none")]
        for day in daily_plans:
            if not isinstance(day, dict):
                continue
            lines.append(f"\nDay {day.get('day', 0)}:")
            for stop in _safe_get_stops(day):
                if isinstance(stop, dict):
                    lines.append(f"  - {stop.get('poi_name', '')} [{stop.get('start_minutes', 0)}-{stop.get('end_minutes', 0)}min]")

        llm_result = {}
        try:
            content = await self.invoke_llm({"context": "\n".join(lines)}, state=state)
            if "```json" in content:
                content = content.split("```json", 1)[1].rsplit("```", 1)[0]
            elif "```" in content:
                content = content.split("```", 1)[1].rsplit("```", 1)[0]
            llm_result = json.loads(content.strip())
        except Exception as e:
            logger.warning("LLM review parse failed: %s", e)

        raw_issues = llm_result.get("issues", []) if isinstance(llm_result.get("issues"), list) else []
        llm_issues = [i for i in raw_issues if isinstance(i, dict)]
        all_issues = hard_issues + llm_issues

        has_critical = any(i.get("severity") == "critical" for i in all_issues)
        has_high = any(i.get("severity") == "high" for i in all_issues)
        severity = "critical" if has_critical else ("high" if has_high else llm_result.get("severity", "low" if all_issues else "none"))
        passed = not has_critical and not has_high

        review = {
            "passed": passed, "issues": all_issues,
            "suggestions": llm_result.get("suggestions", []),
            "missing_must_visit": missing, "severity": severity,
        }

        new_cycle = state.get("review_cycle", 0) + 1
        logger.info("Review cycle %d: passed=%s, severity=%s, issues=%d",
                     new_cycle, passed, severity, len(all_issues))

        return {
            "review_result": review,
            "review_feedback": review,
            "review_cycle": new_cycle,
            "sse_events": [{
                "type": "review_complete",
                "content": f"审核完成: {'通过' if passed else '需修改'}（{severity}）",
            }],
        }
