# TourPass Agent Service

AI-powered travel itinerary planning agent using DeepSeek + LangGraph + RAG.

## Architecture

```
User Input → [Intent Parser] → [RAG Guide Retrieval] → [POI/Hotel Search]
           → [Hotel Anchor Selection] → [Daily Planning] → [Route Optimization]
           → [Assembly & Summary] → SSE Stream Output
```

## Quick Start

### 1. Install dependencies

```bash
cd agent
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your DeepSeek API key
```

### 3. Ingest RAG data

```bash
python scripts/ingest_rag.py
```

### 4. Start the service

```bash
cd agent
python -m uvicorn agent.main:app --host 0.0.0.0 --port 8090 --reload
```

Or:

```bash
python agent/main.py
```

### 5. Test

```bash
# Streaming plan generation
curl -N -X POST http://localhost:8090/agent/plan \
  -H "Content-Type: application/json" \
  -d '{"message": "去长沙3天，想去岳麓山和橘子洲"}'

# Sync plan generation
curl -X POST http://localhost:8090/agent/plan-sync \
  -H "Content-Type: application/json" \
  -d '{"message": "去长沙3天，想去岳麓山和橘子洲"}'

# Health check
curl http://localhost:8090/agent/health
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/agent/plan` | Generate itinerary (SSE stream) |
| POST | `/agent/plan-sync` | Generate itinerary (sync JSON) |
| POST | `/agent/chat` | Chat to modify/ask about itinerary |
| GET | `/agent/hot` | List hot itineraries |
| GET | `/agent/hot/{city}/{days}/{pref}` | Get specific hot itinerary |
| POST | `/agent/rag/ingest` | Ingest city guides into RAG |
| GET | `/agent/health` | Health check |
| GET | `/agent/stats` | Cache and service stats |

## Data Strategy

**Local-first**: All POI, hotel, and route data comes from the C++ backend's local database.
Amap MCP is only used as a fallback when local data is insufficient.

**Caching**: Three levels of caching:
- L1: Hot itineraries (pre-generated for popular cities)
- L2: Redis itinerary cache (TTL 24h)
- L3: In-memory cache (fastest)
