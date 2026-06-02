import { useEffect, useState } from 'react';
import type { Poi } from '../types';
import { useItineraryStore } from '../stores/itineraryStore';

interface Recommendation {
  poi: Poi;
  score: number;
  reason: string;
}

interface AiRecommendProps {
  allPois: Poi[];
  onAdd: (poi: Poi) => void;
}

export default function AiRecommend({ allPois, onAdd }: AiRecommendProps) {
  const { days, defaultHotel } = useItineraryStore();
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const currentDay = days[days.length - 1];
  const lastStop = currentDay?.stops[currentDay.stops.length - 1];

  useEffect(() => {
    if (!lastStop || dismissed) {
      setRecommendations([]);
      return;
    }

    setLoading(true);
    fetch('/editor/ai-suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_poi_id: lastStop.poi.id,
        current_time: lastStop.departure,
        used_poi_ids: days.flatMap(d => d.stops.map(s => s.poi.id)),
        interests: [],
        limit: 3,
      }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.recommendations) {
          setRecommendations(data.recommendations);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [lastStop?.poi.id, lastStop?.departure, dismissed]);

  if (dismissed || recommendations.length === 0) return null;

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-[1000] bg-white rounded-xl shadow-lg border border-primary-200 p-3 max-w-lg">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-semibold text-primary-700">✨ AI 推荐</span>
        {loading && <span className="text-xs text-gray-400">计算中...</span>}
        <button onClick={() => setDismissed(true)} className="ml-auto text-gray-400 hover:text-gray-600 text-xs">✕</button>
      </div>
      <div className="flex gap-2">
        {recommendations.map(rec => (
          <button
            key={rec.poi.id}
            onClick={() => { onAdd(rec.poi); setRecommendations([]); }}
            className="flex-1 px-3 py-2 border rounded-lg hover:border-primary-500 hover:bg-primary-50 text-left transition-colors"
          >
            <div className="text-sm font-medium truncate">{rec.poi.name}</div>
            <div className="text-xs text-gray-500 truncate">{rec.poi.area}</div>
            <div className="text-xs text-primary-600 mt-1">{rec.reason}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
