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
}

export interface DayPlan {
  day: number;
  stops: Stop[];
}

export interface RouteSegment {
  from: string;
  to: string;
  travelMinutes: number;
  coords: [number, number][];
}

export interface ItineraryState {
  city: string;
  hotel: Poi | null;
  days: DayPlan[];
  routes: RouteSegment[];
}

export type PoiTypeFilter = 'all' | 'attraction' | 'restaurant' | 'nightlife';
