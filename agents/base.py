"""Tour Pass Multi-Agent System - Base Agent Class.

Provides two base classes:
- ``BaseAgent``: lightweight base (no LLM) for deterministic agents.
- ``LLMAgent``: extends BaseAgent with an LLM chain for agents that
  actually need language-model inference, with built-in call-count
  governance (MAX_LLM_CALLS_PER_REQUEST).

Circuit Breaker:
- Critical agents (PoiAgent, SchedulerAgent) propagate errors upward
  so that the graph can abort early instead of silently producing empty
  itineraries.
- Non-critical agents (Weather, Ticket, Summary) are allowed to fail
  gracefully with a single retry and an error entry in state.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig

from agents.state import TourState
from agents.config import MAX_LLM_CALLS_PER_REQUEST

logger = logging.getLogger(__name__)

# Agents whose failure must abort the planning pipeline.
# Override via the ``is_critical`` property on concrete subclasses.
_CRITICAL_AGENT_NAMES = frozenset({"PoiAgent", "SchedulerAgent", "IntentAgent"})


class BaseAgent(ABC):
    """Lightweight base class for deterministic agents (no LLM required).

    Subclasses may set ``is_critical = True`` to signal that their failure
    should abort the pipeline rather than being silently swallowed.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name (for logging)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """What this agent does."""

    @property
    def is_critical(self) -> bool:
        """Whether this agent's failure should abort the pipeline."""
        return self.__class__.__name__ in _CRITICAL_AGENT_NAMES

    @property
    def max_retries(self) -> int:
        """Number of retry attempts on transient failure (0 = no retry)."""
        return 1 if not self.is_critical else 0

    @abstractmethod
    async def execute(self, state: TourState) -> dict:
        """Run the agent's logic and return state updates."""

    async def __call__(self, state: TourState, config: RunnableConfig | None = None) -> dict:
        """LangGraph node entry point with retry + circuit breaker."""
        logger.info("[%s] Executing (critical=%s)...", self.name, self.is_critical)
        last_error: Optional[Exception] = None

        for attempt in range(1 + self.max_retries):
            try:
                result = await self.execute(state)
                logger.info("[%s] Completed (attempt %d)", self.name, attempt + 1)
                return result
            except Exception as e:
                import traceback
                last_error = e
                logger.error(
                    "[%s] Failed (attempt %d/%d): %s\n%s",
                    self.name, attempt + 1, 1 + self.max_retries,
                    e, traceback.format_exc(),
                )
                if attempt < self.max_retries:
                    # Brief back-off before retry
                    await asyncio.sleep(0.5 * (attempt + 1))

        # All attempts exhausted
        error_msg = f"{self.name}: {last_error}"

        if self.is_critical:
            # Propagate to LangGraph — the graph will surface this to the API
            logger.critical("[%s] CRITICAL agent failed — aborting pipeline", self.name)
            raise RuntimeError(error_msg) from last_error

        # Non-critical: degrade gracefully
        logger.warning("[%s] Non-critical agent failed — degrading gracefully", self.name)
        return {
            "errors": [error_msg],
            "sse_events": [{
                "type": "warning",
                "content": f"⚠ {self.name} 执行失败，部分功能可能受限",
            }],
        }


class LLMAgent(BaseAgent):
    """Base class for agents that need an LLM chain."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self._runnable: Optional[Runnable] = None

    @abstractmethod
    def build_prompt(self) -> ChatPromptTemplate:
        """Build the prompt template."""

    def get_runnable(self) -> Runnable:
        """Lazily build and cache the prompt | llm chain."""
        if self._runnable is None:
            self._runnable = self.build_prompt() | self.llm
        return self._runnable

    async def invoke_llm(
        self,
        variables: dict,
        state: Optional[TourState] = None,
    ) -> str:
        """Convenience: invoke the cached chain and return raw text.

        If *state* is provided, increments ``llm_call_count`` and raises
        ``RuntimeError`` when ``MAX_LLM_CALLS_PER_REQUEST`` is exceeded.
        """
        if state is not None:
            current = state.get("llm_call_count", 0)
            if current >= MAX_LLM_CALLS_PER_REQUEST:
                raise RuntimeError(
                    f"Max LLM calls ({MAX_LLM_CALLS_PER_REQUEST}) reached in "
                    f"{self.name}"
                )
            state["llm_call_count"] = current + 1

        chain = self.get_runnable()
        response = await chain.ainvoke(variables)
        return response.content
