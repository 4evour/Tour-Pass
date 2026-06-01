import { create } from 'zustand';
import type { Poi, Stop, DayPlan, RouteSegment, ItineraryState } from '../types';

const DEFAULT_START = 9 * 60; // 09:00

function recalcTimes(stops: Stop[], startMinutes = DEFAULT_START): Stop[] {
  let current = startMinutes;
  return stops.map((stop, i) => {
    const travel = i === 0 ? 0 : (stop.travelMinutes || 10);
    current += travel;
    const openMin = stop.poi.open_minutes ?? 0;
    const arrival = Math.max(current, openMin);
    const duration = stop.poi.visit_duration || 60;
    const departure = arrival + duration;
    current = departure;
    return { ...stop, arrival, departure, travelMinutes: travel };
  });
}

interface ItineraryActions {
  setCity: (city: string) => void;
  setHotel: (hotel: Poi) => void;
  addStop: (day: number, poi: Poi, travelMinutes?: number) => void;
  removeStop: (day: number, index: number) => void;
  reorderStops: (day: number, oldIndex: number, newIndex: number) => void;
  addDay: () => void;
  removeDay: (day: number) => void;
  setRoutes: (routes: RouteSegment[]) => void;
  getStopsForDay: (day: number) => Stop[];
  getTotalDays: () => number;
}

export const useItineraryStore = create<ItineraryState & ItineraryActions>((set, get) => ({
  city: '',
  hotel: null,
  days: [{ day: 1, stops: [] }],
  routes: [],

  setCity: (city) => set({ city }),

  setHotel: (hotel) => set({ hotel }),

  addStop: (day, poi, travelMinutes = 10) => {
    set((state) => {
      const dayIdx = state.days.findIndex(d => d.day === day);
      if (dayIdx === -1) return state;
      const newStop: Stop = {
        id: `${day}-${Date.now()}`,
        poi,
        arrival: 0,
        departure: 0,
        travelMinutes,
      };
      const newStops = [...state.days[dayIdx].stops, newStop];
      const recalced = recalcTimes(newStops);
      const newDays = [...state.days];
      newDays[dayIdx] = { ...newDays[dayIdx], stops: recalced };
      return { days: newDays };
    });
  },

  removeStop: (day, index) => {
    set((state) => {
      const dayIdx = state.days.findIndex(d => d.day === day);
      if (dayIdx === -1) return state;
      const newStops = state.days[dayIdx].stops.filter((_, i) => i !== index);
      const recalced = recalcTimes(newStops);
      const newDays = [...state.days];
      newDays[dayIdx] = { ...newDays[dayIdx], stops: recalced };
      return { days: newDays };
    });
  },

  reorderStops: (day, oldIndex, newIndex) => {
    set((state) => {
      const dayIdx = state.days.findIndex(d => d.day === day);
      if (dayIdx === -1) return state;
      const newStops = [...state.days[dayIdx].stops];
      const [moved] = newStops.splice(oldIndex, 1);
      newStops.splice(newIndex, 0, moved);
      const recalced = recalcTimes(newStops);
      const newDays = [...state.days];
      newDays[dayIdx] = { ...newDays[dayIdx], stops: recalced };
      return { days: newDays };
    });
  },

  addDay: () => {
    set((state) => ({
      days: [...state.days, { day: state.days.length + 1, stops: [] }],
    }));
  },

  removeDay: (day) => {
    set((state) => ({
      days: state.days.filter(d => d.day !== day).map((d, i) => ({ ...d, day: i + 1 })),
    }));
  },

  setRoutes: (routes) => set({ routes }),

  getStopsForDay: (day) => {
    const d = get().days.find(d => d.day === day);
    return d ? d.stops : [];
  },

  getTotalDays: () => get().days.length,
}));
