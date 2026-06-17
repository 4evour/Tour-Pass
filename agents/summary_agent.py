"""Summary Agent - Generate itinerary summary and must_visit coverage report.

Migrated from agent/graph.py assemble_result logic.
Uses the ITINERARY_SUMMARY_SYSTEM prompt to generate a concise, attractive
summary of the generated itinerary.
"""

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import LLMAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

ITINERARY_SUMMARY_SYSTEM = """你是一个旅行攻略达人。根据生成的行程，写一段简洁有吸引力的行程总结。

要求：
1. 用轻松自然的语气
2. 突出 2-3 个亮点
3. 给 1-2 条实用贴士（穿什么、带什么、注意事项）
4. 如果有当地特色美食，提一下
5. 控制在 200 字以内

直接输出文字，不要加标题或前缀。
"""


class SummaryAgent(LLMAgent):
    """Generate itinerary summary and must_visit coverage report."""

    def __init__(self, llm: BaseChatModel):
        super().__init__(llm)

    @property
    def name(self) -> str:
        return "SummaryAgent"

    @property
    def description(self) -> str:
        return "Generate itinerary summary and must_visit coverage report"

    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", ITINERARY_SUMMARY_SYSTEM),
            ("human", "{context}"),
        ])

    async def execute(self, state: TourState) -> dict:
        intent = state.get("trip_intent") or {}
        daily_plans = state.get("daily_plans", [])
        city_guides = state.get("city_guides", [])
        sse_events: list[dict] = []

        if not daily_plans:
            return {
                "summary": "",
                "sse_events": [{"type": "summary_complete", "content": "行程为空，无法生成总结"}],
            }

        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", state.get("days", 3))
        pace = intent.get("pace", "balanced")
        travelers = intent.get("travelers", "普通")

        # Build itinerary text for LLM
        itinerary_text = ""
        for dp in daily_plans:
            itinerary_text += f"\n第{dp.get('day', '?')}天:\n"
            for s in dp.get("stops", []):
                itinerary_text += f"  {s.get('slot', '')} {s.get('poi_name', '')}"
                if s.get("reason"):
                    itinerary_text += f" - {s['reason']}"
                itinerary_text += "\n"

        guide_tips = "\n".join(city_guides[:3])

        summary_context = (
            f"城市: {city}, {days}天{pace}节奏\n"
            f"出行人群: {travelers}\n"
            f"行程安排:{itinerary_text}\n"
        )
        if guide_tips:
            summary_context += f"\n当地贴士:\n{guide_tips}\n"

        # Generate summary via LLM
        summary = ""
        try:
            content = await self.invoke_llm({"context": summary_context}, state=state)
            summary = content.strip()
        except Exception as e:
            logger.warning("Summary generation failed: %s", e)
            summary = f"{city}{days}天行程已生成"

        # Build must_visit coverage report (if not already done by SchedulerAgent)
        must_visit_coverage = state.get("must_visit_coverage", [])
        if not must_visit_coverage and intent.get("must_visit"):
            all_planned_names: set[str] = set()
            for dp in daily_plans:
                for s in dp.get("stops", []):
                    all_planned_names.add(s.get("poi_name", ""))

            for mv in intent["must_visit"]:
                included = False
                matched = ""
                for name in all_planned_names:
                    if mv in name:
                        included = True
                        matched = name
                        break
                must_visit_coverage.append({
                    "name": mv,
                    "included": included,
                    "matched_poi": matched,
                })

            covered = sum(1 for c in must_visit_coverage if c["included"])
            logger.info("Must-visit coverage: %d/%d", covered, len(must_visit_coverage))

        sse_events.append({
            "type": "itinerary_complete",
            "content": summary,
        })

        return {
            "summary": summary,
            "must_visit_coverage": must_visit_coverage,
            "sse_events": sse_events,
        }
