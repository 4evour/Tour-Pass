import { useState, useEffect } from 'react';
import StreamingItinerary from './StreamingItinerary';

interface HotItem {
  id: string;
  city: string;
  days: number;
  preference: string;
  itinerary: Record<string, unknown>;
  hit_count: number;
}

interface Props {
  onSelect?: (itinerary: Record<string, unknown>) => void;
}

const PREFERENCE_LABELS: Record<string, string> = {
  balanced: '🎯 综合体验',
  culture: '🏛️ 历史文化',
  food: '🍜 美食之旅',
  nature: '🌿 自然风光',
};

export default function HotItineraries({ onSelect }: Props) {
  const [items, setItems] = useState<HotItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCity, setSelectedCity] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (selectedCity) params.set('city', selectedCity);
    params.set('limit', '20');

    fetch(`/agent/hot?${params}`)
      .then(r => r.json())
      .then(data => {
        setItems(data.items || []);
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [selectedCity]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-400">
        <span className="animate-pulse">加载热门行程中...</span>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <div className="text-4xl mb-3">🗺️</div>
        <div>暂无热门行程</div>
        <div className="text-xs mt-1">使用 AI 规划师生成行程后会自动缓存</div>
      </div>
    );
  }

  // Group by city
  const cities = [...new Set(items.map(i => i.city))];

  return (
    <div className="space-y-4">
      {/* City filter */}
      <div className="flex gap-2 overflow-x-auto pb-2">
        <button
          onClick={() => setSelectedCity('')}
          className={`px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors ${
            !selectedCity ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          全部城市
        </button>
        {cities.map(city => (
          <button
            key={city}
            onClick={() => setSelectedCity(city)}
            className={`px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors ${
              selectedCity === city
                ? 'bg-primary-500 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {city}
          </button>
        ))}
      </div>

      {/* Itinerary cards */}
      <div className="grid gap-3">
        {items.map(item => (
          <div
            key={item.id}
            className="border rounded-xl overflow-hidden hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
          >
            <div className="px-4 py-3 flex items-center justify-between">
              <div>
                <div className="font-medium text-sm">
                  {item.city} · {item.days}天
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {PREFERENCE_LABELS[item.preference] || item.preference}
                  {item.hit_count > 0 && (
                    <span className="ml-2 text-primary-500">🔥 {item.hit_count}次使用</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {onSelect && (
                  <button
                    onClick={e => {
                      e.stopPropagation();
                      onSelect(item.itinerary);
                    }}
                    className="px-3 py-1.5 bg-primary-500 text-white rounded-lg text-xs hover:bg-primary-600 transition-colors"
                  >
                    使用此行程
                  </button>
                )}
                <span className="text-gray-400 text-xs">
                  {expandedId === item.id ? '▲' : '▼'}
                </span>
              </div>
            </div>

            {expandedId === item.id && (
              <div className="px-4 pb-4 border-t pt-3">
                <StreamingItinerary itinerary={item.itinerary} compact />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
