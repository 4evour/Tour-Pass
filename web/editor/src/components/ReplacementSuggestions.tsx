import { useState, useEffect } from 'react';
import type { Poi } from '../types';
import { useItineraryStore } from '../stores/itineraryStore';

interface Suggestion {
  poi: Poi;
  score: number;
  reason: string;
}

export default function ReplacementSuggestions({ currentDay, allPois }: { currentDay: number; allPois: Poi[] }) {
  const { lastRemovedStop, addStopAtIndex, clearLastRemovedStop, getStopsForDay } = useItineraryStore();
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!lastRemovedStop || lastRemovedStop.day !== currentDay) {
      setSuggestions([]);
      return;
    }

    const stops = getStopsForDay(currentDay);
    // Get the POI before the removed position
    const prevIndex = Math.max(0, lastRemovedStop.index - 1);
    const prevPoi = stops[prevIndex]?.poi;
    const usedPoiIds = stops.map(s => s.poi.id);

    setLoading(true);
    fetch('/editor/ai-suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        city: useItineraryStore.getState().city,
        current_poi_id: prevPoi?.id || '',
        current_time: stops[prevIndex]?.departure || 9 * 60,
        used_poi_ids: usedPoiIds,
        limit: 3,
      }),
    })
      .then(r => r.json())
      .then(data => {
        const items = (data.suggestions || []).map((s: any) => {
          const poi = allPois.find(p => p.id === s.poi_id);
          return poi ? { poi, score: s.score, reason: s.reason } : null;
        }).filter(Boolean);
        setSuggestions(items);
      })
      .catch(() => setSuggestions([]))
      .finally(() => setLoading(false));
  }, [lastRemovedStop, currentDay, allPois, getStopsForDay]);

  if (!lastRemovedStop || lastRemovedStop.day !== currentDay || suggestions.length === 0) {
    return null;
  }

  const handleAccept = (poi: Poi) => {
    addStopAtIndex(currentDay, poi, lastRemovedStop.index);
    setSuggestions([]);
  };

  const handleDismiss = () => {
    clearLastRemovedStop();
    setSuggestions([]);
  };

  return (
    <div className="mt-2 border-2 border-dashed border-amber-300 rounded-lg p-2 bg-amber-50">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-amber-800">💡 推荐替代景点</span>
        <button onClick={handleDismiss} className="text-xs text-gray-400 hover:text-gray-600">忽略全部</button>
      </div>
      {loading ? (
        <div className="text-xs text-gray-400 py-1">搜索推荐中...</div>
      ) : (
        <div className="space-y-1">
          {suggestions.map(s => (
            <div key={s.poi.id} className="flex items-center gap-2 px-2 py-1.5 bg-white rounded border hover:border-primary-400">
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate">{s.poi.name}</div>
                <div className="text-xs text-gray-400 truncate">{s.reason}</div>
              </div>
              <button
                onClick={() => handleAccept(s.poi)}
                className="flex-shrink-0 px-2 py-0.5 bg-primary-500 text-white rounded text-xs hover:bg-primary-600"
              >
                采纳
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
