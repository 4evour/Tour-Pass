"""Tour Pass Multi-Agent System - Base Agent Class.

Provides two base classes:
- ``BaseAgent``: lightweight base (no LLM) for deterministic agents.
- ``LLMAgent``: extends BaseAgent with an LLM chain for agents that
  actually need language-model inference.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig

from agents.state import TourState

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Lightweight base class for deterministic agents (no LLM required)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name (for logging)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """What this agent does."""

    @abstractmethod
    async def execute(self, state: TourState) -> dict:
        """Run the agent's logic and return state updates."""

    async def __call__(self, state: TourState, config: RunnableConfig | None = None) -> dict:
        """LangGraph node entry point."""
        logger.info("[%s] Executing...", self.name)
        try:
            result = await self.execute(state)
            logger.info("[%s] Completed", self.name)
            return result
        except Exception as e:
            import traceback
            logger.error("[%s] Failed: %s\n%s", self.name, e, traceback.format_exc())
            return {"errors": [f"{self.name}: {e}"]}


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

    async def invoke_llm(self, variables: dict) -> str:
        """Convenience: invoke the cached chain and return raw text."""
        chain = self.get_runnable()
        response = await chain.ainvoke(variables)
        return response.content
