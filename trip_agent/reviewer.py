from __future__ import annotations

import json
from typing import Any

from .model_schema import review_output_format


REVIEWER_PROMPT = """你是 Tour Pass 的独立行程质量审查员。你只审查候选结果，不修改行程。
只根据输入中的 user_constraints、candidate_plan、route_evidence 和 hard_validation_report 判断，不得补充外部事实。
重点检查：
1. 用户硬约束是否在结构化结果、时间轴和叙述中一致落实；
2. 地点、开放状态、预约、天气和路线表述是否有对应证据，是否把 unknown 说成已确认；
3. 日程区域顺序是否少折返，活动密度、停留时长、餐饮休息和通勤衔接是否自然；
4. overview、daily summary、narrative、risk 中出现的每个时间、出发与抵达语义是否和 schedule、transfers 一致；
5. 是否存在明显不可执行或会误导用户的体验安排。
不得推翻确定性校验结果，不得把风格偏好当成事实错误。用户没有提供日期时，不得把日期为空本身列为问题；开放或预约状态已标记 unknown 且结果明确提示用户时，不得重复列为质量问题。证据不足时使用 suspected_fact，不得把猜测写成事实。verdict=revise 时每项必须给 suggestion；verdict=pass 时不要制造无依据问题。最多返回 5 个最重要问题，严格符合给定 JSON Schema。"""


class ItineraryReviewer:
    version = "reviewer-v3"

    def __init__(self, llm: Any, *, shadow: bool = True) -> None:
        self.llm = llm
        self.shadow = shadow

    async def review(
        self,
        *,
        planning_context: dict[str, Any],
        plan: dict[str, Any],
        validation_report: dict[str, Any],
        trace: dict[str, Any] | None = None,
        on_model_event: Any = None,
    ) -> dict[str, Any]:
        digest = {
            "user_constraints": planning_context,
            "candidate_plan": {
                key: plan.get(key)
                for key in (
                    "city",
                    "overview",
                    "trip_profile",
                    "hotel",
                    "candidate_comparison",
                    "days",
                    "narrative",
                    "warnings",
                )
            },
            "route_evidence": plan.get("verified_routes", []),
            "hard_validation_report": validation_report,
        }
        response = await self.llm.ainvoke(
            [
                {"role": "system", "content": REVIEWER_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        digest, ensure_ascii=False, separators=(",", ":")
                    ),
                },
            ],
            trace={**(trace or {}), "stage": "independent_review"},
            on_progress=on_model_event,
            reasoning_effort="high",
            output_format=review_output_format(),
        )
        result = json.loads(response.content)
        result["reviewer_version"] = self.version
        result["shadow"] = self.shadow
        result["metrics"] = getattr(response, "metrics", {})
        return result
