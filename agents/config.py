"""Tour Pass Multi-Agent System - Unified Configuration.

Migrated from agent/config.py so that the multi-agent system shares the same
environment-variable conventions (CPP backend URL, Redis, LLM limits, etc.).
"""
import os

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "agent", ".env"))
except ImportError:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "agent", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

# ── DeepSeek LLM ───────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# ── C++ algorithm backend ──────────────────────────────────────────────────────
CPP_BACKEND_URL: str = os.environ.get("CPP_BACKEND_URL", "http://127.0.0.1:8080")

# ── Redis cache ─────────────────────────────────────────────────────────────────
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL_SECONDS", "86400"))  # 24 h

# ── Amap (supplementary data) ───────────────────────────────────────────────────
AMAP_API_KEY: str = os.environ.get("AMAP_API_KEY", "")

# ── Agent behaviour ─────────────────────────────────────────────────────────────
MAX_LLM_CALLS_PER_REQUEST: int = int(os.environ.get("MAX_LLM_CALLS", "10"))
LLM_TEMPERATURE: float = float(os.environ.get("LLM_TEMPERATURE", "0.3"))
LLM_TIMEOUT_SECONDS: int = int(os.environ.get("LLM_TIMEOUT", "60"))

# ── Route optimisation ───────────────────────────────────────────────────────────
# When true (default), SchedulerAgent delegates to the C++ Beam Search API.
# Falls back to pure-Python 2-opt when the backend is unreachable.
USE_CPP_ROUTE_OPTIMIZER: bool = os.environ.get("USE_CPP_ROUTE_OPTIMIZER", "true").lower() in ("1", "true", "yes")

# ── Server ───────────────────────────────────────────────────────────────────────
HOST: str = os.environ.get("AGENT_HOST", "0.0.0.0")
PORT: int = int(os.environ.get("AGENT_PORT", "8090"))

# ── Hot itineraries ───────────────────────────────────────────────────────────────
HOT_CITIES: list[str] = [
    "beijing", "shanghai", "guangzhou", "shenzhen", "chengdu",
    "chongqing", "hangzhou", "wuhan", "nanjing", "xian",
    "changsha", "kunming", "dali", "lijiang", "sanya",
    "guilin", "xiamen", "qingdao", "harbin", "suzhou",
    "zhangjiajie",
]
HOT_DAY_OPTIONS: list[int] = [2, 3, 4, 5]
HOT_PREFERENCES: list[str] = ["balanced", "culture", "food", "nature"]
