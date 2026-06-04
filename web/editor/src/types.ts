export interface Poi {
  id: string;
  name: string;
  type: 'attraction' | 'restaurant' | 'hotel' | 'nightlife' | 'transit';
  area: string;
  lat: number;
  lng: number;
  popularity: number;
  price_level: number;
  description: string;
  meal_type: string;
  recommendation: string;
  open_minutes?: number;
  close_minutes?: number;
  visit_duration?: number;
}

export interface Stop {
  id: string;
  poi: Poi;
  arrival: number;      // minutes from midnight
  departure: number;
  travelMinutes: number; // travel time from previous stop
  arrivalOverride?: number; // user-pinned arrival time (F8)
}

export type StartPointType = 'hotel' | 'station' | 'airport' | 'custom';

export interface StartPoint {
  type: StartPointType;
  poi: Poi | null;  // null = use day's effective hotel
}

export interface DayPlan {
  day: number;
  stops: Stop[];
  hotel: Poi | null;       // per-day hotel, null = inherit defaultHotel
  startPoint: StartPoint;  // where the day begins
}

export interface RouteSegment {
  from: string;
  to: string;
  travelMinutes: number;
  coords: [number, number][];
}

export interface ItineraryState {
  city: string;
  defaultHotel: Poi | null;  // global default hotel
  days: DayPlan[];
  routes: RouteSegment[];
  lastRemovedStop: { day: number; poi: Poi; index: number } | null; // for F3 replacement suggestions
}

export type PoiTypeFilter = 'all' | 'attraction' | 'restaurant' | 'nightlife' | 'hotel' | 'transit';
