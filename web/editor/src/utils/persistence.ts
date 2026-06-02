import type { ItineraryState, DayPlan, Poi } from '../types';

const STORAGE_KEY = 'tp_editor_state';

// Debounce timer
let saveTimer: ReturnType<typeof setTimeout> | null = null;

interface PersistedState {
  city: string;
  hotel: Poi | null;
  days: DayPlan[];
  // routes are NOT persisted (recalculated by useRoute)
}

export function saveToStorage(state: PersistedState): void {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try {
      const data = JSON.stringify({
        city: state.city,
        hotel: state.hotel,
        days: state.days,
        savedAt: Date.now(),
      });
      localStorage.setItem(STORAGE_KEY, data);
    } catch {
      // localStorage full or disabled — silently ignore
    }
  }, 300);
}

export function loadFromStorage(): PersistedState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data.city || !Array.isArray(data.days)) return null;
    // Validate each day has the expected shape
    for (const day of data.days) {
      if (typeof day.day !== 'number' || !Array.isArray(day.stops)) return null;
    }
    return {
      city: data.city,
      hotel: data.hotel ?? null,
      days: data.days,
    };
  } catch {
    return null;
  }
}

export function clearStorage(): void {
  localStorage.removeItem(STORAGE_KEY);
}
