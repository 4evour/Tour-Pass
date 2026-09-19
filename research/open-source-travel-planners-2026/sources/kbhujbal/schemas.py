"""
Normalized data models for all services.
These provide a consistent format regardless of which API provider returned the data.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


# ── Flight Models ─────────────────────────────────────────────────────────────

class FlightSegment(BaseModel):
    airline: str
    flight_number: str
    departure_airport: str
    arrival_airport: str
    departure_time: str
    arrival_time: str
    duration: str
    cabin_class: str


class FlightOption(BaseModel):
    provider: str  # "amadeus" or "serpapi"
    segments: List[FlightSegment]
    total_duration: str
    layovers: int
    layover_cities: List[str] = []
    price_per_person: float
    total_price: float
    currency: str = "USD"
    baggage: str = ""
    booking_url: Optional[str] = None


class FlightSearchResult(BaseModel):
    origin: str
    destination: str
    departure_date: str
    return_date: Optional[str] = None
    travelers: int
    cabin_class: str
    options: List[FlightOption] = []
    source: str = ""  # which API provided the data


# ── Accommodation Models ──────────────────────────────────────────────────────

class AccommodationOption(BaseModel):
    provider: str  # "booking" or "airbnb"
    name: str
    property_type: str  # Hotel, Apartment, Villa, etc.
    rating: float
    review_count: int
    price_per_night: float
    total_price: float
    currency: str = "USD"
    neighborhood: str = ""
    distance_to_center_km: Optional[float] = None
    amenities: List[str] = []
    room_type: str = ""
    cancellation_policy: str = ""
    breakfast_included: bool = False
    image_url: Optional[str] = None
    booking_url: Optional[str] = None


class AccommodationSearchResult(BaseModel):
    destination: str
    check_in: str
    check_out: str
    nights: int
    guests: int
    options: List[AccommodationOption] = []
    source: str = ""


# ── Activity Models ───────────────────────────────────────────────────────────

class ActivityOption(BaseModel):
    provider: str  # "google_places", "viator", "yelp"
    name: str
    category: str
    description: str = ""
    rating: float
    review_count: int
    price: Optional[float] = None
    currency: str = "USD"
    duration: Optional[str] = None
    address: str = ""
    image_url: Optional[str] = None
    booking_url: Optional[str] = None
    opening_hours: Optional[str] = None


class ActivitySearchResult(BaseModel):
    destination: str
    interests: List[str]
    attractions: List[ActivityOption] = []  # from Google Places
    tours: List[ActivityOption] = []  # from Viator
    dining: List[ActivityOption] = []  # from Yelp


# ── Logistics Models ──────────────────────────────────────────────────────────

class TransportRoute(BaseModel):
    mode: str  # driving, transit, walking, bicycling
    origin: str
    destination: str
    distance: str
    duration: str
    steps: List[str] = []
    fare: Optional[str] = None


class WeatherForecast(BaseModel):
    date: str
    temperature_high: float
    temperature_low: float
    description: str
    humidity: int
    wind_speed: float
    icon: str = ""


class CurrencyInfo(BaseModel):
    base_currency: str
    target_currency: str
    rate: float
    last_updated: str = ""


class CountryInfo(BaseModel):
    name: str
    capital: str
    currency_name: str
    currency_code: str
    languages: List[str]
    timezone: str = ""
    calling_code: str = ""
    visa_info: str = ""
    vaccinations: str = ""
    safety_info: str = ""
    electricity: str = ""
    tipping_culture: str = ""


class LogisticsResult(BaseModel):
    routes: List[TransportRoute] = []
    weather: List[WeatherForecast] = []
    currency: Optional[CurrencyInfo] = None
    country: Optional[CountryInfo] = None


# ── Request Models ────────────────────────────────────────────────────────────

class TravelRequest(BaseModel):
    message: str


class TravelPlanParams(BaseModel):
    """Structured parameters extracted from natural language request by AI."""
    destinations: List[str]
    origin: str = ""
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    duration_days: int = 7
    travelers: int = 1
    budget_level: str = "mid-range"  # budget, mid-range, luxury
    interests: List[str] = []
    cabin_class: str = "economy"
    special_requirements: List[str] = []


# ── Response Models ───────────────────────────────────────────────────────────

class ItineraryResponse(BaseModel):
    id: str
    request: str
    itinerary: str
    created_at: str
    status: str

