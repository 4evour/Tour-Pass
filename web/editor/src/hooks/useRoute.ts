import { useEffect } from 'react';
import { useItineraryStore } from '../stores/itineraryStore';
import type { RouteSegment } from '../types';

export function useRoute() {
  const { days, hotel, setRoutes } = useItineraryStore();

  useEffect(() => {
    const allStops = days.flatMap(d => d.stops);
    if (!hotel || allStops.length < 1) {
      setRoutes([]);
      return;
    }

    // Build POI ID sequence: hotel -> stops -> hotel
    const poiIds = [hotel.id, ...allStops.map(s => s.poi.id), hotel.id];

    // Fetch batch route from backend
    const controller = new AbortController();
    fetch('/editor/batch-route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ poi_ids: poiIds }),
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
        for (let i = 0; i < poiIds.length - 1; i++) {
          const fromPoi = i === 0 ? hotel : allStops[i - 1]?.poi;
          const toPoi = i < allStops.length ? allStops[i]?.poi : hotel;
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
  }, [days, hotel, setRoutes]);
}
