import { useState, useEffect } from 'react';
import type { Poi } from '../types';
import { useItineraryStore } from '../stores/itineraryStore';

export default function HotelPicker({ city }: { city: string }) {
  const { hotel, setHotel } = useItineraryStore();
  const [mode, setMode] = useState<'choose' | 'search' | 'list'>('choose');
  const [hotels, setHotels] = useState<Poi[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (mode === 'list') {
      setLoading(true);
      fetch(`/poi/search?city=${encodeURIComponent(city)}&type=hotel&limit=20`)
        .then(r => r.json())
        .then(data => setHotels(data.data || []))
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [mode, city]);

  if (hotel) {
    return (
      <div className="flex items-center gap-3 px-4 py-2 bg-primary-50 border-b border-primary-200">
        <span className="text-sm text-primary-700">🏨 酒店：</span>
        <span className="font-medium text-primary-900">{hotel.name}</span>
        <span className="text-xs text-primary-600">{hotel.area}</span>
        <button onClick={() => setHotel(null as any)} className="ml-auto text-xs text-red-500 hover:underline">更换</button>
      </div>
    );
  }

  if (mode === 'choose') {
    return (
      <div className="flex items-center gap-4 px-4 py-3 bg-amber-50 border-b border-amber-200">
        <span className="text-sm font-medium text-amber-800">请先选择酒店作为行程起点：</span>
        <button onClick={() => setMode('search')} className="px-3 py-1.5 bg-primary-500 text-white rounded-lg text-sm hover:bg-primary-600">已定酒店</button>
        <button onClick={() => setMode('list')} className="px-3 py-1.5 bg-white border border-gray-300 rounded-lg text-sm hover:bg-gray-50">推荐酒店</button>
      </div>
    );
  }

  if (mode === 'search') {
    return (
      <div className="flex items-center gap-2 px-4 py-2 bg-white border-b">
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="输入酒店名称搜索..."
          className="flex-1 px-3 py-1.5 border rounded-lg text-sm"
        />
        <button onClick={() => setMode('list')} className="text-xs text-gray-500 hover:underline">从列表选</button>
        <button onClick={() => setMode('choose')} className="text-xs text-gray-500 hover:underline">返回</button>
      </div>
    );
  }

  return (
    <div className="px-4 py-2 bg-white border-b">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-medium">选择酒店：</span>
        <button onClick={() => setMode('choose')} className="text-xs text-gray-500 hover:underline">返回</button>
      </div>
      {loading ? (
        <div className="text-sm text-gray-500 py-2">加载中...</div>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {hotels.map(h => (
            <button
              key={h.id}
              onClick={() => setHotel(h)}
              className="flex-shrink-0 px-3 py-2 border rounded-lg hover:border-primary-500 hover:bg-primary-50 text-left"
            >
              <div className="text-sm font-medium">{h.name}</div>
              <div className="text-xs text-gray-500">{h.area} · {'⭐'.repeat(Math.min(5, Math.round(h.popularity / 2)))}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
