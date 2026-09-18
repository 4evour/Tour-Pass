# Multi-Agent AI Travel Planner v2.0

An AI travel planning system that combines **real-time API data** with **AI-powered analysis** to create personalized travel itineraries. Built with CrewAI, featuring 11 external API integrations and RAG for travel knowledge.

## Key Concepts

- **3 AI Agents** handle reasoning: parsing requests, cultural knowledge, and itinerary compilation
- **4 API Services** fetch real-time data: flights, accommodation, activities, and logistics
- **RAG Knowledge Base** provides cultural tips, visa info, and practical advice via ChromaDB
- **AI only does analysis** — all travel data comes from real APIs, not hallucinated by the LLM

## Architecture

```
User Request
    |
[AI] Travel Planning Manager --- parses request into structured params
    |
[API] 4 services fetch in parallel (no AI, pure HTTP)
    |--- Flights: Amadeus + SerpApi (fallback)
    |--- Accommodation: Booking.com + Airbnb
    |--- Activities: Google Places + Viator + Yelp
    |--- Logistics: Google Maps + OpenWeatherMap + Currency + Country Info
    |
[AI] Travel Knowledge Expert --- RAG for cultural/visa/practical info
    |
[AI] Itinerary Compiler --- synthesizes ALL real data into day-by-day plan
    |
Final Itinerary (with real prices, real hotels, booking links)
```

## Quick Start

### Prerequisites

- Python 3.9+
- API keys (see [API Keys Required](#api-keys-required) below)

### Installation

```bash
# Clone the project
cd "Multi Agent AI Travel Agent"

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and add your API keys
```

### Running

**Backend:**
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload --reload-exclude "venv/*" --reload-exclude "data/*"
```

**Frontend** (separate terminal):
```bash
cd frontend
npm install
npm run dev
```

**CLI mode** (no frontend needed):
```bash
python main.py
```

## API Keys Required

### Required
| Key | Purpose | Get it from |
|-----|---------|-------------|
| `GEMINI_API_KEY` | AI agents (needs paid plan) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

### Flight APIs (need at least one)
| Key | Purpose | Get it from |
|-----|---------|-------------|
| `AMADEUS_API_KEY` + `AMADEUS_API_SECRET` | Primary flight search | [developers.amadeus.com](https://developers.amadeus.com/) |
| `SERPAPI_KEY` | Fallback flight search | [serpapi.com](https://serpapi.com/) |

### Accommodation APIs (need at least one)
| Key | Purpose | Get it from |
|-----|---------|-------------|
| `BOOKING_API_KEY` | Hotels (Booking.com via RapidAPI) | [rapidapi.com](https://rapidapi.com/DataCrawler/api/booking-com15) |
| `AIRBNB_API_KEY` | Rentals (Airbnb via RapidAPI) | [rapidapi.com](https://rapidapi.com/3b-data-3b-data-default/api/airbnb19) |

### Activity APIs (need at least one)
| Key | Purpose | Get it from |
|-----|---------|-------------|
| `GOOGLE_PLACES_API_KEY` | Attractions & restaurants | [console.cloud.google.com](https://console.cloud.google.com/) |
| `VIATOR_API_KEY` | Bookable tours | [docs.viator.com](https://docs.viator.com/) |
| `YELP_API_KEY` | Dining (5,000 calls/day free) | [yelp.com/developers](https://www.yelp.com/developers/) |

### Logistics APIs (all free)
| Key | Purpose | Get it from |
|-----|---------|-------------|
| `GOOGLE_MAPS_API_KEY` | Transport routes | [console.cloud.google.com](https://console.cloud.google.com/) |
| `OPENWEATHER_API_KEY` | Weather forecast | [openweathermap.org](https://openweathermap.org/api) |

### Optional
| Key | Purpose |
|-----|---------|
| `OPENAI_API_KEY` | RAG embeddings (only if using knowledge base) |
| `EXCHANGE_RATE_API_KEY` | Currency rates (fallback uses free API without key) |

Services gracefully skip any provider whose key isn't configured.

## Project Structure

```
backend/
├── app.py                          # FastAPI entry point
├── config/
│   └── settings.py                 # All API keys & service URLs
├── api/
│   ├── routes.py                   # REST endpoints
│   └── websocket.py                # WebSocket + progress updates
├── services/                       # Pure API calls, NO AI
│   ├── flights/
│   │   ├── amadeus.py              # Amadeus API (primary)
│   │   ├── serpapi.py              # SerpApi Google Flights (fallback)
│   │   └── service.py              # FlightService coordinator
│   ├── accommodation/
│   │   ├── booking.py              # Booking.com via RapidAPI
│   │   ├── airbnb.py              # Airbnb via RapidAPI
│   │   └── service.py             # AccommodationService coordinator
│   ├── activities/
│   │   ├── google_places.py        # Attractions & restaurants
│   │   ├── viator.py              # Bookable tours
│   │   ├── yelp.py                # Dining recommendations
│   │   └── service.py             # ActivityService coordinator
│   ├── logistics/
│   │   ├── google_maps.py         # Directions & routes
│   │   ├── weather.py             # OpenWeatherMap
│   │   ├── currency.py            # Exchange rates
│   │   ├── country_info.py        # REST Countries + Travelbriefing
│   │   └── service.py             # LogisticsService coordinator
│   └── knowledge/
│       └── rag.py                 # ChromaDB RAG
├── agents/                         # Only 3 AI agents
│   ├── llm.py                     # Gemini LLM factory
│   ├── definitions.py             # Travel Manager, Knowledge Expert, Compiler
│   ├── tasks.py                   # Task definitions
│   └── tools.py                   # CrewAI tool wrapper (RAG only)
├── crew/
│   └── orchestrator.py            # Main pipeline
├── models/
│   └── schemas.py                 # Normalized Pydantic models
frontend/                           # React + Vite UI
data/
├── travel_knowledge/              # RAG documents (.txt)
└── chroma_db/                     # Vector store (auto-generated)
main.py                             # CLI entry point
```

## How It Works

### The Pipeline (2-3 AI calls instead of 15-20)

1. **AI Step 1** — Travel Manager parses natural language into structured parameters (destinations, dates, budget, interests)
2. **API Step** — 4 services fetch real data in parallel via `asyncio.gather` (flights, hotels, activities, logistics) — pure HTTP, no AI
3. **AI Step 2** — Knowledge Expert queries RAG for cultural/visa/practical info
4. **AI Step 3** — Itinerary Compiler takes ALL real API data + knowledge and creates a personalized day-by-day plan

### Adding Travel Knowledge

Add `.txt` files to `data/travel_knowledge/`. Delete `data/chroma_db/` to force re-indexing. The RAG system automatically indexes new documents on next run.

## Tech Stack

- **CrewAI** — Multi-agent orchestration
- **Google Gemini** — LLM (via LiteLLM)
- **FastAPI** — REST + WebSocket API
- **httpx** — Async HTTP client for all API services
- **ChromaDB** — Vector database for RAG
- **React + Vite** — Frontend
- **Pydantic** — Data models and validation

## Troubleshooting

### "Rate limit error" / "429" / "RESOURCE_EXHAUSTED"
Your Gemini free tier quota is exhausted. Enable billing at [aistudio.google.com](https://aistudio.google.com/) or wait for daily reset.

### "API key expired"
Generate a new key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and update `.env`.

### Server reloads during execution
Run with: `uvicorn backend.app:app --reload --reload-exclude "venv/*" --reload-exclude "data/*"`

### "ModuleNotFoundError"
Activate your venv and run: `pip install -r requirements.txt`

### ChromaDB errors
Delete `data/chroma_db/` and run again.

## License

MIT License — see [LICENSE](LICENSE) for details.

