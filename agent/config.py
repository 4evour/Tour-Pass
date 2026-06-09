"""Configuration for TourPass Agent service."""
import os

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    # python-dotenv not installed, try manual loading
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

# DeepSeek LLM
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# C++ backend
CPP_BACKEND_URL = os.environ.get("CPP_BACKEND_URL", "http://127.0.0.1:8080")

# Redis cache
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "86400"))  # 24h

# ChromaDB RAG
CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", "data/chromadb")
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "city_guides")

# Amap (supplementary)
AMAP_API_KEY = os.environ.get("AMAP_API_KEY", "")

# Agent
MAX_LLM_CALLS_PER_REQUEST = int(os.environ.get("MAX_LLM_CALLS", "10"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.3"))
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT", "60"))

# Server
HOST = os.environ.get("AGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("AGENT_PORT", "8090"))

# Hot itineraries
HOT_CITIES = [
    "beijing", "shanghai", "guangzhou", "shenzhen", "chengdu",
    "chongqing", "hangzhou", "wuhan", "nanjing", "xian",
    "changsha", "kunming", "dali", "lijiang", "sanya",
    "guilin", "xiamen", "qingdao", "harbin", "suzhou",
    "zhangjiajie",
]
HOT_DAY_OPTIONS = [2, 3, 4, 5]
HOT_PREFERENCES = ["balanced", "culture", "food", "nature"]

