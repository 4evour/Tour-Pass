import { create } from 'zustand';
import type { Poi, Stop, DayPlan, StartPoint, RouteSegment, ItineraryState } from '../types';
import { saveToStorage, loadFromStorage } from '../utils/persistence';

const DEFAULT_START = 9 * 60; // 09:00

function recalcTimes(stops: Stop[], startMinutes = DEFAULT_START): Stop[] {
  let current = startMinutes;
  return stops.map((stop, i) => {
    const travel = i === 0 ? 0 : (stop.travelMinutes || 10);
    current += travel;
    // If user pinned an arrival time, use it
    const arrival = stop.arrivalOverride ?? Math.max(current, stop.poi.open_minutes ?? 0);
    const duration = stop.poi.visit_duration || 60;
    const departure = arrival + duration;
    current = departure;
    return { ...stop, arrival, departure, travelMinutes: travel };
  });
}

function makeDefaultStartPoint(): StartPoint {
  return { type: 'hotel', poi: null };
}

function makeDefaultDay(day: number): DayPlan {
  return { day, stops: [], hotel: null, startPoint: makeDefaultStartPoint() };
}

// Load persisted state or use defaults
const persisted = loadFromStorage();

interface ItineraryActions {
  setCity: (city: string) => void;
  setDefaultHotel: (hotel: Poi) => void;
  setDayHotel: (day: number, hotel: Poi | null) => void;
  setDayStartPoint: (day: number, startPoint: StartPoint) => void;
  getEffectiveHotel: (day: number) => Poi | null;
  getStartPoi: (day: number) => Poi | null;
  addStop: (day: number, poi: Poi, travelMinutes?: number) => void;
  addStopAtIndex: (day: number, poi: Poi, index: number) => void;
  removeStop: (day: number, index: number) => void;
  clearLastRemovedStop: () => void;
  reorderStops: (day: number, oldIndex: number, newIndex: number) => void;
  moveStopBetweenDays: (fromDay: number, fromIndex: number, toDay: number, toIndex: number) => void;
  updateStopTime: (day: number, index: number, field: 'arrival' | 'duration', value: number) => void;
  addDay: () => void;
  removeDay: (day: number) => void;
  setDays: (days: DayPlan[]) => void;
  setRoutes: (routes: RouteSegment[]) => void;
  getStopsForDay: (day: number) => Stop[];
  getTotalDays: () => number;
  resetEditor: () => void;
}

export const useItineraryStore = create<ItineraryState & ItineraryActions>((set, get) => ({
  city: persisted?.city ?? '',
  defaultHotel: persisted?.hotel ?? null,
  days: persisted?.days ?? [makeDefaultDay(1)],
  routes: [],
  lastRemovedStop: null,

  setCity: (city) => {
    set({ city });
  },

  setDefaultHotel: (hotel) => {
    set({ defaultHotel: hotel });
  },

  setDayHotel: (day, hotel) => {
    set((state) => {
      const dayIdx = state.days.findIndex(d => d.day === day);
      if (dayIdx === -1) return state;
      const newDays = [...state.days];
      newDays[dayIdx] = { ...newDays[dayIdx], hotel };
      return { days: newDays };
    });
  },

  setDayStartPoint: (day, startPoint) => {
    set((state) => {
      const dayIdx = state.days.findIndex(d => d.day === day);
      if (dayIdx === -1) return state;
      const newDays = [...state.days];
      newDays[dayIdx] = { ...newDays[dayIdx], startPoint };
      return { days: newDays };
    });
  },

  getEffectiveHotel: (day) => {
    const state = get();
    const dayPlan = state.days.find(d => d.day === day);
    return dayPlan?.hotel ?? state.defaultHotel;
  },

  getStartPoi: (day) => {
    const state = get();
    const dayPlan = state.days.find(d => d.day === day);
    if (!dayPlan) return null;
    if (dayPlan.startPoint.poi) return dayPlan.startPoint.poi;
    // Default: use effective hotel
    return dayPlan.hotel ?? state.defaultHotel;
  },

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

  addStopAtIndex: (day, poi, index) => {
    set((state) => {
      const dayIdx = state.days.findIndex(d => d.day === day);
      if (dayIdx === -1) return state;
      const newStop: Stop = {
        id: `${day}-${Date.now()}`,
        poi,
        arrival: 0,
        departure: 0,
        travelMinutes: 10,
      };
      const newStops = [...state.days[dayIdx].stops];
      newStops.splice(index, 0, newStop);
      const recalced = recalcTimes(newStops);
      const newDays = [...state.days];
      newDays[dayIdx] = { ...newDays[dayIdx], stops: recalced };
      return { days: newDays, lastRemovedStop: null };
    });
  },

  removeStop: (day, index) => {
    set((state) => {
      const dayIdx = state.days.findIndex(d => d.day === day);
      if (dayIdx === -1) return state;
      const removedPoi = state.days[dayIdx].stops[index]?.poi;
      const newStops = state.days[dayIdx].stops.filter((_, i) => i !== index);
      const recalced = recalcTimes(newStops);
      const newDays = [...state.days];
      newDays[dayIdx] = { ...newDays[dayIdx], stops: recalced };
      return {
        days: newDays,
        lastRemovedStop: removedPoi ? { day, poi: removedPoi, index } : null,
      };
    });
  },

  clearLastRemovedStop: () => set({ lastRemovedStop: null }),

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

  moveStopBetweenDays: (fromDay, fromIndex, toDay, toIndex) => {
    set((state) => {
      const fromDayIdx = state.days.findIndex(d => d.day === fromDay);
      const toDayIdx = state.days.findIndex(d => d.day === toDay);
      if (fromDayIdx === -1 || toDayIdx === -1) return state;

      const fromStops = [...state.days[fromDayIdx].stops];
      const [moved] = fromStops.splice(fromIndex, 1);
      const toStops = fromDayIdx === toDayIdx
        ? fromStops // same day — already spliced
        : [...state.days[toDayIdx].stops];
      toStops.splice(toIndex, 0, moved);

      const newDays = [...state.days];
      newDays[fromDayIdx] = { ...newDays[fromDayIdx], stops: recalcTimes(fromStops) };
      if (fromDayIdx !== toDayIdx) {
        newDays[toDayIdx] = { ...newDays[toDayIdx], stops: recalcTimes(toStops) };
      }
      return { days: newDays };
    });
  },

  updateStopTime: (day, index, field, value) => {
    set((state) => {
      const dayIdx = state.days.findIndex(d => d.day === day);
      if (dayIdx === -1) return state;
      const stops = [...state.days[dayIdx].stops];
      if (index >= stops.length) return state;

      if (field === 'arrival') {
        // Pin arrival time
        stops[index] = { ...stops[index], arrivalOverride: value };
        // Recalc from this index onward
        let current = value;
        for (let i = index; i < stops.length; i++) {
          const arrival = i === index ? value : Math.max(current, stops[i].poi.open_minutes ?? 0);
          const duration = stops[i].poi.visit_duration || 60;
          stops[i] = { ...stops[i], arrival, departure: arrival + duration, travelMinutes: i === index ? stops[i].travelMinutes : 10 };
          current = arrival + duration;
        }
      } else {
        // Update visit duration
        const updatedPoi = { ...stops[index].poi, visit_duration: value };
        stops[index] = { ...stops[index], poi: updatedPoi };
        // Recalc from this index
        const recalced = recalcTimes(stops.slice(index), stops[index].arrival);
        for (let i = 0; i < recalced.length; i++) {
          stops[index + i] = recalced[i];
        }
      }

      const newDays = [...state.days];
      newDays[dayIdx] = { ...newDays[dayIdx], stops };
      return { days: newDays };
    });
  },

  addDay: () => {
    set((state) => ({
      days: [...state.days, makeDefaultDay(state.days.length + 1)],
    }));
  },

  removeDay: (day) => {
    set((state) => ({
      days: state.days.filter(d => d.day !== day).map((d, i) => ({
        ...d,
        day: i + 1,
        startPoint: d.startPoint,
        hotel: d.hotel,
      })),
    }));
  },

  setDays: (days) => set({ days }),

  setRoutes: (routes) => set({ routes }),

  getStopsForDay: (day) => {
    const d = get().days.find(d => d.day === day);
    return d ? d.stops : [];
  },

  getTotalDays: () => get().days.length,

  resetEditor: () => {
    set({
      city: '',
      defaultHotel: null,
      days: [makeDefaultDay(1)],
      routes: [],
      lastRemovedStop: null,
    });
  },
}));

// Auto-persist on every state change
useItineraryStore.subscribe((state) => {
  saveToStorage({
    city: state.city,
    hotel: state.defaultHotel,
    days: state.days,
  });
});
