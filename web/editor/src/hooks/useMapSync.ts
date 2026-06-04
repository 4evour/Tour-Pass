import { useMemo } from 'react';
import { useEditorStore } from '../stores/editorStore';
import { useItineraryStore } from '../stores/itineraryStore';

export function useMapSync() {
  const { mode, currentDay } = useEditorStore();
  const { days } = useItineraryStore();
  
  const visibleStops = useMemo(() => {
    if (mode === 'day' && currentDay !== null) {
      const day = days[currentDay];
      return day ? day.stops : [];
    }
    return days.flatMap(d => d.stops);
  }, [mode, currentDay, days]);
  
  const mapCenter = useMemo(() => {
    if (visibleStops.length === 0) {
      return { lat: 28.2282, lng: 112.9388 };
    }
    
    const avgLat = visibleStops.reduce((sum, s) => sum + s.poi.lat, 0) / visibleStops.length;
    const avgLng = visibleStops.reduce((sum, s) => sum + s.poi.lng, 0) / visibleStops.length;
    
    return { lat: avgLat, lng: avgLng };
  }, [visibleStops]);
  
  return {
    visibleStops,
    mapCenter,
    isDayMode: mode === 'day',
    currentDay
  };
}
