"""Grounded Planner domain errors."""


class PlannerError(RuntimeError):
    code = "PLANNER_ERROR"


class LlmBudgetExceeded(PlannerError):
    code = "LLM_BUDGET_EXCEEDED"


class SkeletonError(PlannerError):
    code = "SKELETON_INVALID"


class EvidenceError(PlannerError):
    code = "EVIDENCE_UNAVAILABLE"


class SolverError(PlannerError):
    code = "SOLVER_NO_FEASIBLE_PLAN"
