import { useEffect } from 'react';
import { useItineraryStore } from '../stores/itineraryStore';
import type { RouteSegment, Poi } from '../types';

export function useRoute() {
  const days = useItineraryStore(s => s.days);
  const defaultHotel = useItineraryStore(s => s.defaultHotel);
  const getEffectiveHotel = useItineraryStore(s => s.getEffectiveHotel);
  const getStartPoi = useItineraryStore(s => s.getStartPoi);
  const setRoutes = useItineraryStore(s => s.setRoutes);

  useEffect(() => {
    const allStops = days.flatMap(d => d.stops);
    if (allStops.length < 1) {
      setRoutes([]);
      return;
    }

    // Build POI ID sequence per day: startPoi -> stops -> endHotel
    const poiIds: string[] = [];
    const poiLookup = new Map<string, Poi>();

    for (const day of days) {
      if (day.stops.length === 0) continue;

      const startPoi = getStartPoi(day.day);
      const endHotel = getEffectiveHotel(day.day);

      // Add start -> first stop
      if (startPoi) {
        poiIds.push(startPoi.id);
        poiLookup.set(startPoi.id, startPoi);
      }

      // Add all stops
      for (const stop of day.stops) {
        poiIds.push(stop.poi.id);
        poiLookup.set(stop.poi.id, stop.poi);
      }

      // Add last stop -> end hotel (for next day's start)
      if (endHotel) {
        poiIds.push(endHotel.id);
        poiLookup.set(endHotel.id, endHotel);
      }
    }

    if (poiIds.length < 2) {
      setRoutes([]);
      return;
    }

    // Deduplicate consecutive same IDs
    const deduped = [poiIds[0]];
    for (let i = 1; i < poiIds.length; i++) {
      if (poiIds[i] !== poiIds[i - 1]) deduped.push(poiIds[i]);
    }

    // Fetch batch route from backend
    const controller = new AbortController();
    fetch('/editor/batch-route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ poi_ids: deduped }),
      signal: controller.signal,
    })
      .then(r => r.json())
      .then(data => {
        if (data.segments) {
          setRoutes(data.segments as RouteSegment[]);
        }
      })
      .catch(() => {
        // Fallback: create simple straight-line segments
        const segments: RouteSegment[] = [];
        for (let i = 0; i < deduped.length - 1; i++) {
          const fromPoi = poiLookup.get(deduped[i]);
          const toPoi = poiLookup.get(deduped[i + 1]);
          if (fromPoi && toPoi) {
            segments.push({
              from: fromPoi.id,
              to: toPoi.id,
              travelMinutes: 10,
              coords: [[fromPoi.lat, fromPoi.lng], [toPoi.lat, toPoi.lng]],
            });
          }
        }
        setRoutes(segments);
      });

    return () => controller.abort();
  }, [days, defaultHotel, getEffectiveHotel, getStartPoi, setRoutes]);
}
