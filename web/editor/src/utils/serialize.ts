import type { Poi, Stop, DayPlan } from '../types';

function minutesToTime(m: number): string {
  const h = Math.floor(m / 60);
  const min = m % 60;
  return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}

function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
}

/**
 * Serialize editor state to the format expected by POST /trips/save
 */
export function serializeForSave(city: string, days: DayPlan[]) {
  const daysData = days.map(day => ({
    day: day.day,
    total_travel_minutes: day.stops.reduce((s, st) => s + st.travelMinutes, 0),
    total_visit_minutes: day.stops.reduce((s, st) => s + (st.poi.visit_duration || 60), 0),
    stops: day.stops.map((stop, i) => ({
      slot: '',
      poi_id: stop.poi.id,
      poi_name: stop.poi.name,
      poi_type: stop.poi.type,
      area: stop.poi.area,
      lat: stop.poi.lat,
      lng: stop.poi.lng,
      start_time: minutesToTime(stop.arrival),
      end_time: minutesToTime(stop.departure),
      visit_duration_minutes: stop.poi.visit_duration || 60,
      travel_minutes_from_previous: stop.travelMinutes,
      recommendation: stop.poi.recommendation || '',
      score: 0,
      reason: '',
    })),
  }));

  const totalStops = days.reduce((s, d) => s + d.stops.length, 0);
  const response = {
    city,
    days: daysData,
    total_score: 0,
    alternatives: [],
    comparison: {
      total_stops: totalStops,
      total_travel_minutes: daysData.reduce((s, d) => s + d.total_travel_minutes, 0),
      total_visit_minutes: daysData.reduce((s, d) => s + d.total_visit_minutes, 0),
    },
  };

  const title = `${city} ${days.length}日游`;
  const request = {
    city,
    days: days.length,
    interests: [],
    pace: '标准',
  };

  return { title, request, response };
}

/**
 * Deserialize a saved trip's response_json into editor DayPlan[]
 */
export function deserializeTrip(tripData: any, allPois: Poi[]): { city: string; days: DayPlan[] } | null {
  try {
    let resp = tripData;
    if (typeof tripData === 'string') {
      resp = JSON.parse(tripData);
    }

    const city = resp.city || '';
    const poiMap = new Map(allPois.map(p => [p.id, p]));

    const days: DayPlan[] = (resp.days || []).map((dayJson: any) => {
      const stops: Stop[] = (dayJson.stops || []).map((stopJson: any, i: number) => {
        // Try to find the POI in our database
        let poi = poiMap.get(stopJson.poi_id);

        // Fallback: create a minimal POI from the stop data
        if (!poi) {
          poi = {
            id: stopJson.poi_id || `imported-${Date.now()}-${i}`,
            name: stopJson.poi_name || '未知景点',
            type: stopJson.poi_type || 'attraction',
            area: stopJson.area || '',
            lat: stopJson.lat || 0,
            lng: stopJson.lng || 0,
            popularity: 0,
            price_level: 0,
            description: '',
            meal_type: stopJson.meal_type || '',
            recommendation: stopJson.recommendation || '',
            visit_duration: stopJson.visit_duration_minutes || 60,
          };
        }

        const arrival = typeof stopJson.start_time === 'string'
          ? timeToMinutes(stopJson.start_time)
          : (stopJson.start_minutes || 0);
        const duration = stopJson.visit_duration_minutes || poi.visit_duration || 60;

        return {
          id: `${dayJson.day}-${Date.now()}-${i}`,
          poi,
          arrival,
          departure: arrival + duration,
          travelMinutes: stopJson.travel_minutes_from_previous || (i === 0 ? 0 : 10),
        };
      });

      return {
        day: dayJson.day,
        stops,
        hotel: null,
        startPoint: { type: 'hotel' as const, poi: null },
      };
    });

    return { city, days };
  } catch {
    return null;
  }
}
