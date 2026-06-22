"""Tour Pass Multi-Agent System - Unified Configuration.

Migrated from agent/config.py so that the multi-agent system shares the same
environment-variable conventions (CPP backend URL, Redis, LLM limits, etc.).
"""
import logging
import os

logger = logging.getLogger(__name__)


# ── Safe type conversion helpers ────────────────────────────────────────────────
def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning("Invalid int env value: %s, using default %s", value, default)
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning("Invalid float env value: %s, using default %s", value, default)
        return default


# ── Load .env file (search multiple candidate paths) ────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ENV_CANDIDATES = [
    os.path.join(_HERE, os.pardir, "agent", ".env"),   # legacy: agent/.env
    os.path.join(_HERE, os.pardir, ".env"),             # root: .env
    os.path.join(_HERE, ".env"),                         # agents/.env
]
_env_loaded = False
try:
    from dotenv import load_dotenv
    for p in _ENV_CANDIDATES:
        if os.path.exists(p):
            load_dotenv(p)
            _env_loaded = True
            break
except ImportError:
    for p in _ENV_CANDIDATES:
        if os.path.exists(p):
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ.setdefault(key.strip(), value.strip())
            _env_loaded = True
            break

# ── DeepSeek LLM ───────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# ── C++ algorithm backend ──────────────────────────────────────────────────────
CPP_BACKEND_URL: str = os.environ.get("CPP_BACKEND_URL", "http://127.0.0.1:8080")

# ── Redis cache ─────────────────────────────────────────────────────────────────
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
CACHE_TTL_SECONDS: int = _safe_int(os.environ.get("CACHE_TTL_SECONDS", "86400"), 86400)  # 24 h

# ── Amap (supplementary data) ───────────────────────────────────────────────────
AMAP_API_KEY: str = os.environ.get("AMAP_API_KEY", "")

# ── QWeather (和风天气) ───────────────────────────────────────────────────────
QWEATHER_KEY: str = (
    os.environ.get("QWEATHER_KEY")
    or os.environ.get("QWEATHER_API_KEY")
    or os.environ.get("HEFENG_WEATHER_KEY")
    or ""
)
QWEATHER_API_HOST: str = os.environ.get("QWEATHER_API_HOST", "devapi.qweather.com")
QWEATHER_GEO_URL: str = f"https://{QWEATHER_API_HOST}/v2/city/lookup"
QWEATHER_WEATHER_URL: str = f"https://{QWEATHER_API_HOST}/v7/weather/3d"
QWEATHER_INDICES_URL: str = f"https://{QWEATHER_API_HOST}/v7/indices/3d"
QWEATHER_WARNING_URL: str = f"https://{QWEATHER_API_HOST}/v7/warning/now"

# ── Agent behaviour ─────────────────────────────────────────────────────────────
MAX_LLM_CALLS_PER_REQUEST: int = _safe_int(os.environ.get("MAX_LLM_CALLS", "10"), 10)
LLM_TEMPERATURE: float = _safe_float(os.environ.get("LLM_TEMPERATURE", "0.3"), 0.3)
LLM_TIMEOUT_SECONDS: int = _safe_int(os.environ.get("LLM_TIMEOUT", "60"), 60)

# ── Route optimisation ───────────────────────────────────────────────────────────
# When true (default), SchedulerAgent delegates to the C++ Beam Search API.
# Falls back to pure-Python 2-opt when the backend is unreachable.
USE_CPP_ROUTE_OPTIMIZER: bool = os.environ.get("USE_CPP_ROUTE_OPTIMIZER", "true").lower() in ("1", "true", "yes")

# ── Server ───────────────────────────────────────────────────────────────────────
HOST: str = os.environ.get("AGENT_HOST", "0.0.0.0")
PORT: int = _safe_int(os.environ.get("AGENT_PORT", "8090"), 8090)

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
