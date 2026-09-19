"""
Crew Orchestrator — the main pipeline that:
1. Uses AI to parse the user request (Travel Manager)
2. Fetches real data from APIs in parallel (no AI)
3. Uses AI to compile the final itinerary (Itinerary Compiler)

This reduces LLM calls from ~15-20 down to 2-3.
"""

import asyncio
import json
import logging
from typing import Optional, Callable, Awaitable

from crewai import Crew, Process

from backend.agents.definitions import (
    create_travel_manager,
    create_travel_knowledge_agent,
    create_itinerary_compiler,
)
from backend.agents.tasks import (
    create_planning_task,
    create_knowledge_task,
    create_compilation_task,
)
from backend.agents.tools import TravelKnowledgeTool
from backend.services.flights import FlightService
from backend.services.accommodation import AccommodationService
from backend.services.activities import ActivityService
from backend.services.logistics import LogisticsService
from backend.models.schemas import (
    FlightSearchResult,
    AccommodationSearchResult,
    ActivitySearchResult,
    LogisticsResult,
)

logger = logging.getLogger(__name__)

# Type for progress callback
ProgressCallback = Optional[Callable[[str, str, str], Awaitable[None]]]


def _format_flights(data: FlightSearchResult) -> str:
    """Format flight data into readable text for the AI compiler."""
    if not data.options:
        return "No flight data available."

    lines = [f"**Route:** {data.origin} -> {data.destination}"]
    lines.append(f"**Date:** {data.departure_date}")
    if data.return_date:
        lines.append(f"**Return:** {data.return_date}")
    lines.append(f"**Travelers:** {data.travelers} | **Class:** {data.cabin_class}")
    lines.append(f"**Source:** {data.source}\n")

    for i, opt in enumerate(data.options[:5], 1):
        segments_str = " -> ".join(
            f"{s.departure_airport} to {s.arrival_airport} ({s.airline} {s.flight_number})"
            for s in opt.segments
        )
        lines.append(f"### Option {i}: ${opt.price_per_person}/person")
        lines.append(f"- Segments: {segments_str}")
        lines.append(f"- Total Duration: {opt.total_duration}")
        lines.append(f"- Layovers: {opt.layovers}")
        if opt.layover_cities:
            lines.append(f"- Layover Cities: {', '.join(opt.layover_cities)}")
        lines.append(f"- Total Price: ${opt.total_price} {opt.currency}")
        lines.append(f"- Baggage: {opt.baggage}")
        if opt.booking_url:
            lines.append(f"- Book: {opt.booking_url}")
        lines.append("")

    return "\n".join(lines)


def _format_accommodation(data: AccommodationSearchResult) -> str:
    """Format accommodation data into readable text."""
    if not data.options:
        return "No accommodation data available."

    lines = [f"**Location:** {data.destination}"]
    lines.append(f"**Dates:** {data.check_in} to {data.check_out} ({data.nights} nights)")
    lines.append(f"**Guests:** {data.guests} | **Source:** {data.source}\n")

    for i, opt in enumerate(data.options[:8], 1):
        lines.append(f"### Option {i}: {opt.name} ({opt.provider})")
        lines.append(f"- Type: {opt.property_type}")
        lines.append(f"- Rating: {opt.rating}/5 ({opt.review_count} reviews)")
        lines.append(f"- Price: ${opt.price_per_night}/night | Total: ${opt.total_price}")
        if opt.neighborhood:
            lines.append(f"- Neighborhood: {opt.neighborhood}")
        if opt.amenities:
            lines.append(f"- Amenities: {', '.join(opt.amenities[:8])}")
        lines.append(f"- Cancellation: {opt.cancellation_policy}")
        lines.append(f"- Breakfast: {'Included' if opt.breakfast_included else 'Not included'}")
        if opt.booking_url:
            lines.append(f"- Book: {opt.booking_url}")
        lines.append("")

    return "\n".join(lines)


def _format_activities(data: ActivitySearchResult) -> str:
    """Format activity data into readable text."""
    lines = [f"**Destination:** {data.destination}"]
    lines.append(f"**Interests:** {', '.join(data.interests)}\n")

    if data.attractions:
        lines.append("## Attractions & Places")
        for i, a in enumerate(data.attractions[:8], 1):
            lines.append(f"{i}. **{a.name}** — {a.category}")
            lines.append(f"   Rating: {a.rating}/5 ({a.review_count} reviews)")
            if a.address:
                lines.append(f"   Address: {a.address}")
            if a.price:
                lines.append(f"   Approx. cost: ${a.price}")
            if a.opening_hours:
                lines.append(f"   Hours: {a.opening_hours}")
        lines.append("")

    if data.tours:
        lines.append("## Tours & Experiences (Bookable)")
        for i, t in enumerate(data.tours[:8], 1):
            lines.append(f"{i}. **{t.name}**")
            lines.append(f"   {t.description}")
            lines.append(f"   Rating: {t.rating}/5 ({t.review_count} reviews)")
            if t.price:
                lines.append(f"   Price: ${t.price}/person")
            if t.duration:
                lines.append(f"   Duration: {t.duration}")
            if t.booking_url:
                lines.append(f"   Book: {t.booking_url}")
        lines.append("")

    if data.dining:
        lines.append("## Restaurants & Dining")
        for i, d in enumerate(data.dining[:8], 1):
            lines.append(f"{i}. **{d.name}** — {d.category}")
            lines.append(f"   Rating: {d.rating}/5 ({d.review_count} reviews)")
            if d.address:
                lines.append(f"   Address: {d.address}")
            if d.price:
                lines.append(f"   Approx. cost: ${d.price}/person")
            if d.booking_url:
                lines.append(f"   Link: {d.booking_url}")
        lines.append("")

    if not data.attractions and not data.tours and not data.dining:
        lines.append("No activity data available.")

    return "\n".join(lines)


def _format_logistics(data: LogisticsResult) -> str:
    """Format logistics data into readable text."""
    lines = []

    if data.routes:
        lines.append("## Transport Routes")
        for r in data.routes:
            lines.append(f"- **{r.mode.title()}:** {r.origin} -> {r.destination}")
            lines.append(f"  Distance: {r.distance} | Duration: {r.duration}")
            if r.fare:
                lines.append(f"  Fare: {r.fare}")
        lines.append("")

    if data.weather:
        lines.append("## Weather Forecast")
        for w in data.weather:
            lines.append(
                f"- {w.date}: {w.description}, "
                f"High {w.temperature_high}C / Low {w.temperature_low}C, "
                f"Humidity {w.humidity}%, Wind {w.wind_speed} m/s"
            )
        lines.append("")

    if data.currency:
        lines.append("## Currency")
        lines.append(
            f"1 {data.currency.base_currency} = "
            f"{data.currency.rate} {data.currency.target_currency}"
        )
        lines.append("")

    if data.country:
        c = data.country
        lines.append("## Country Information")
        lines.append(f"- **Country:** {c.name}")
        lines.append(f"- **Capital:** {c.capital}")
        lines.append(f"- **Currency:** {c.currency_name} ({c.currency_code})")
        lines.append(f"- **Languages:** {', '.join(c.languages)}")
        lines.append(f"- **Timezone:** {c.timezone}")
        lines.append(f"- **Calling Code:** {c.calling_code}")
        if c.visa_info:
            lines.append(f"- **Visa:** {c.visa_info}")
        if c.vaccinations:
            lines.append(f"- **Vaccinations:** {c.vaccinations}")
        if c.safety_info:
            lines.append(f"- **Safety:** {c.safety_info}")
        if c.electricity:
            lines.append(f"- **Electricity:** {c.electricity}")
        lines.append("")

    if not lines:
        return "No logistics data available."

    return "\n".join(lines)


async def run_travel_pipeline(
    user_request: str,
    progress_callback: ProgressCallback = None,
) -> str:
    """
    Main pipeline:
    1. AI parses user request -> structured params
    2. APIs fetch real data in parallel (no AI)
    3. AI compiles final itinerary from real data

    Args:
        user_request: Natural language travel request
        progress_callback: Optional async callback(step_key, label, status)

    Returns:
        Final itinerary as string
    """

    async def notify(key: str, label: str, status: str):
        if progress_callback:
            await progress_callback(key, label, status)

    # ── Step 1: AI parses user request ────────────────────────────────────
    await notify("planning", "Travel Planning Manager", "running")
    logger.info("Step 1: Parsing user request with AI...")

    knowledge_tool = TravelKnowledgeTool()
    manager = create_travel_manager(tools=[knowledge_tool])
    planning_task = create_planning_task(manager, user_request)

    planning_crew = Crew(
        agents=[manager],
        tasks=[planning_task],
        process=Process.sequential,
        verbose=True,
    )

    # crew.kickoff() is synchronous — run in thread to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    planning_result = str(await loop.run_in_executor(None, planning_crew.kickoff))
    await notify("planning", "Travel Planning Manager", "completed")
    logger.info(f"Planning result:\n{planning_result[:500]}")

    # ── Parse structured params from AI output ─────────────────────────────
    # Extract key parameters for API calls
    params = _extract_params(planning_result, user_request)

    # ── Step 2: Fetch real data from APIs in parallel (NO AI) ─────────────
    await notify("data_fetch", "Fetching Real-Time Data", "running")
    logger.info("Step 2: Fetching real-time data from APIs...")

    flight_service = FlightService()
    accommodation_service = AccommodationService()
    activity_service = ActivityService()
    logistics_service = LogisticsService()

    # All API calls happen in parallel — pure HTTP, no LLM
    flights_task = flight_service.search(
        origin=params["origin"],
        destination=params["destination"],
        departure_date=params["departure_date"],
        return_date=params.get("return_date"),
        travelers=params["travelers"],
        cabin_class=params["cabin_class"],
    )

    accommodation_task = accommodation_service.search(
        destination=params["destination"],
        check_in=params["departure_date"],
        check_out=params.get("return_date", params["departure_date"]),
        guests=params["travelers"],
    )

    activities_task = activity_service.search(
        destination=params["destination"],
        interests=params["interests"],
    )

    logistics_task = logistics_service.get_logistics(
        destination_city=params["destination"],
        destination_country=params["country"],
        origin=params["origin"],
    )

    # Execute all in parallel
    flights_data, accommodation_data, activities_data, logistics_data = await asyncio.gather(
        flights_task,
        accommodation_task,
        activities_task,
        logistics_task,
    )

    await notify("data_fetch", "Fetching Real-Time Data", "completed")
    logger.info("All API data fetched successfully")

    # ── Step 3: AI Knowledge Expert ─────────────────────────────────────
    await notify("knowledge", "Travel Knowledge Expert", "running")
    logger.info("Step 3: Getting travel knowledge from RAG...")

    knowledge_agent = create_travel_knowledge_agent(tools=[knowledge_tool])
    knowledge_task_obj = create_knowledge_task(
        knowledge_agent,
        destination=", ".join(params.get("destinations", [params["destination"]])),
    )

    knowledge_crew = Crew(
        agents=[knowledge_agent],
        tasks=[knowledge_task_obj],
        process=Process.sequential,
        verbose=True,
    )

    knowledge_result = str(await loop.run_in_executor(None, knowledge_crew.kickoff))
    await notify("knowledge", "Travel Knowledge Expert", "completed")

    # ── Step 4: AI compiles final itinerary ──────────────────────────────
    await notify("compilation", "Itinerary Compiler & Optimizer", "running")
    logger.info("Step 4: Compiling itinerary with AI...")

    # Format all API data into readable text
    flights_text = _format_flights(flights_data)
    accommodation_text = _format_accommodation(accommodation_data)
    activities_text = _format_activities(activities_data)
    logistics_text = _format_logistics(logistics_data)

    compiler = create_itinerary_compiler()
    compilation_task_obj = create_compilation_task(
        agent=compiler,
        user_request=user_request,
        planning_output=planning_result,
        flights_data=flights_text,
        accommodation_data=accommodation_text,
        activities_data=activities_text,
        logistics_data=logistics_text,
        knowledge_output=knowledge_result,
    )

    compilation_crew = Crew(
        agents=[compiler],
        tasks=[compilation_task_obj],
        process=Process.sequential,
        verbose=True,
    )

    final_result = str(await loop.run_in_executor(None, compilation_crew.kickoff))
    await notify("compilation", "Itinerary Compiler & Optimizer", "completed")

    logger.info(f"Itinerary compiled. Length: {len(final_result)} chars")
    return final_result


def _extract_params(planning_output: str, original_request: str) -> dict:
    """
    Extract structured parameters from the planning AI output.
    Falls back to reasonable defaults from the original request.
    """
    output_lower = planning_output.lower()
    request_lower = original_request.lower()

    # Simple extraction — in production, you'd use a more robust parser
    params = {
        "origin": "JFK",
        "destination": "",
        "destinations": [],
        "country": "",
        "departure_date": "2025-06-15",
        "return_date": "2025-06-22",
        "travelers": 1,
        "cabin_class": "economy",
        "interests": ["food", "culture", "history"],
    }

    # Extract destination from planning output
    common_cities = {
        "paris": ("Paris", "France"),
        "rome": ("Rome", "Italy"),
        "florence": ("Florence", "Italy"),
        "venice": ("Venice", "Italy"),
        "barcelona": ("Barcelona", "Spain"),
        "london": ("London", "United Kingdom"),
        "tokyo": ("Tokyo", "Japan"),
        "new york": ("New York", "United States"),
        "dubai": ("Dubai", "United Arab Emirates"),
        "bali": ("Bali", "Indonesia"),
        "amsterdam": ("Amsterdam", "Netherlands"),
        "berlin": ("Berlin", "Germany"),
        "lisbon": ("Lisbon", "Portugal"),
        "bangkok": ("Bangkok", "Thailand"),
        "sydney": ("Sydney", "Australia"),
    }

    destinations = []
    country = ""
    for city_key, (city_name, country_name) in common_cities.items():
        if city_key in output_lower or city_key in request_lower:
            destinations.append(city_name)
            if not country:
                country = country_name

    if destinations:
        params["destination"] = destinations[0]
        params["destinations"] = destinations
        params["country"] = country

    # Extract traveler count
    import re
    traveler_match = re.search(r"(\d+)\s*(traveler|adult|person|people)", output_lower)
    if traveler_match:
        params["travelers"] = int(traveler_match.group(1))

    # Extract dates
    date_match = re.findall(r"\d{4}-\d{2}-\d{2}", planning_output)
    if len(date_match) >= 1:
        params["departure_date"] = date_match[0]
    if len(date_match) >= 2:
        params["return_date"] = date_match[1]

    # Extract cabin class
    for cls in ["first", "business", "premium_economy"]:
        if cls in output_lower:
            params["cabin_class"] = cls
            break

    # Extract interests
    interest_keywords = [
        "food", "history", "art", "culture", "adventure", "nightlife",
        "shopping", "nature", "beach", "wine", "architecture", "music",
        "photography", "relaxation", "sports",
    ]
    found_interests = [k for k in interest_keywords if k in output_lower or k in request_lower]
    if found_interests:
        params["interests"] = found_interests

    # Extract budget
    if "luxury" in output_lower or "5-star" in output_lower:
        params["cabin_class"] = params.get("cabin_class", "business")

    return params


def run_pipeline_sync(user_request: str) -> str:
    """Synchronous wrapper for the async pipeline."""
    return asyncio.run(run_travel_pipeline(user_request))

