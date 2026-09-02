"""Versioned prompts for the Grounded Planner."""

from __future__ import annotations

import json

from .models import TripContext

PROMPT_VERSION = "grounded-skeleton-2026-08-30-v1"

SKELETON_SYSTEM = """你是 Tour Pass 的路线骨架规划器。只负责宏观区域、候选地点查询词和体验取舍，不负责核实事实。
严格输出 JSON，不要 Markdown。禁止输出营业时间、票价、精确通勤分钟、地址或无法由工具验证的事实。
每天最多 4 个 place_queries；每个用户必去项必须原词出现在 query 中，并设 required=true、role=must_visit。
地点可以是景区、博物馆、街区、道路漫步、校园、海滩、观景点、餐饮或夜景。优先按同日区域连贯组织，不要为了覆盖行政区而折返。
输出结构：{"days":[{"day":1,"theme":"","area_sequence":[],"place_queries":[{"query":"","role":"attraction","preferred_period":"any","required":false}],"experience_notes":[]}]}"""


def build_skeleton_user_prompt(ctx: TripContext) -> str:
    payload = {
        "city": ctx.city,
        "date_start": ctx.date_start.isoformat(),
        "days": ctx.days,
        "daily_window": ctx.daily_window.model_dump(),
        "hotel": ctx.hotel.model_dump(),
        "travelers": ctx.travelers,
        "pace": ctx.pace,
        "strategy": ctx.strategy,
        "interests": ctx.interests,
        "must_visit": ctx.must_visit,
        "avoid": ctx.avoid,
        "budget_level": ctx.budget_level,
        "transport_mode": ctx.transport_mode,
        "special_requests": ctx.special_requests,
        "deterministic_constraints": ctx.constraints.model_dump(),
        "assumptions": ctx.assumptions,
    }
    return "请生成路线骨架：\n" + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )
