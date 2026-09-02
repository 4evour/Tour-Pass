import sys
sys.stdout.reconfigure(encoding='utf-8')
from agents.base import BaseAgent, LLMAgent

# Test if BaseAgent subclass accepts args
class TestAgent(BaseAgent):
    @property
    def name(self): return "test"
    @property
    def description(self): return "test"
    async def execute(self, state): return {}

try:
    a = TestAgent("some_arg")
    print(f"TestAgent('some_arg') OK: {a}")
except TypeError as e:
    print(f"TestAgent('some_arg') FAIL: {e}")

try:
    from agents.scheduler_agent import SchedulerAgent
    s = SchedulerAgent("some_arg")
    print(f"SchedulerAgent('some_arg') OK")
except TypeError as e:
    print(f"SchedulerAgent('some_arg') FAIL: {e}")

from abc import ABC
print(f"\nBaseAgent MRO: {[c.__name__ for c in BaseAgent.__mro__]}")
