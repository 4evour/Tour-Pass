"""Tour Pass Multi-Agent System - Base Agent Class.

This module provides the base class for all agents in the system.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig

from agents.state import TourState

logger = logging.getLogger(__name__)


class BaseTourAgent(ABC):
    """Base class for all Tour Pass agents.
    
    Each agent is a node in the LangGraph workflow. It:
    1. Receives the shared state
    2. Performs its specialized task
    3. Returns updated state
    """
    
    def __init__(self, llm: BaseChatModel):
        """Initialize the agent.
        
        Args:
            llm: The language model to use.
        """
        self.llm = llm
        self._runnable: Optional[Runnable] = None
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name (for logging and debugging)."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Agent description (what it does)."""
        pass
    
    @abstractmethod
    def build_prompt(self) -> ChatPromptTemplate:
        """Build the prompt template for this agent."""
        pass
    
    @abstractmethod
    async def execute(self, state: TourState) -> dict:
        """Execute the agent's task.
        
        Args:
            state: Current shared state.
        
        Returns:
            State updates to merge.
        """
        pass
    
    def get_runnable(self) -> Runnable:
        """Get or create the runnable chain."""
        if self._runnable is None:
            prompt = self.build_prompt()
            self._runnable = prompt | self.llm
        return self._runnable
    
    async def __call__(self, state: TourState, config: RunnableConfig = None) -> dict:
        """Call the agent (used as a LangGraph node).
        
        Args:
            state: Current shared state.
            config: Optional configuration.
        
        Returns:
            State updates.
        """
        logger.info(f"[{self.name}] Executing...")
        try:
            result = await self.execute(state)
            logger.info(f"[{self.name}] Completed successfully")
            return result
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            return {"errors": state.get("errors", []) + [f"{self.name}: {str(e)}"]}
