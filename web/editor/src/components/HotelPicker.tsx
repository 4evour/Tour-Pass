import { useState, useEffect } from 'react';
import type { Poi } from '../types';
import { useItineraryStore } from '../stores/itineraryStore';

interface HotelPickerProps {
  city: string;
  day?: number; // if set, picks hotel for that specific day
  compact?: boolean; // for per-day inline display
  onClose?: () => void;
}

export default function HotelPicker({ city, day, compact, onClose }: HotelPickerProps) {
  const { defaultHotel, setDefaultHotel, setDayHotel, getEffectiveHotel } = useItineraryStore();
  const [mode, setMode] = useState<'choose' | 'search' | 'list'>('choose');
  const [hotels, setHotels] = useState<Poi[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);

  const isPerDay = day !== undefined;
  const currentHotel = isPerDay ? getEffectiveHotel(day) : defaultHotel;
  const isOverridden = isPerDay && useItineraryStore(s => s.days.find(d => d.day === day)?.hotel != null);

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

  const selectHotel = (h: Poi) => {
    if (isPerDay) {
      setDayHotel(day, h);
    } else {
      setDefaultHotel(h);
    }
    onClose?.();
  };

  const clearHotel = () => {
    if (isPerDay) {
      setDayHotel(day, null); // revert to default
    }
    onClose?.();
  };

  // Compact mode: for per-day inline in Timeline
  if (compact) {
    if (currentHotel && !mode) {
      return (
        <div className="flex items-center gap-1 text-xs">
          <span className={isOverridden ? 'text-amber-700 font-medium' : 'text-gray-500'}>
            🏨 {currentHotel.name}
            {isOverridden && ' ✏️'}
          </span>
          <button onClick={() => setMode('list')} className="text-primary-600 hover:underline">更换</button>
          {isOverridden && <button onClick={clearHotel} className="text-gray-400 hover:text-red-500">恢复默认</button>}
        </div>
      );
    }
    return (
      <div className="mt-1">
        {mode === 'list' && (
          <div className="border rounded-lg p-2 bg-white shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium">选择第 {day} 天酒店：</span>
              <button onClick={() => { setMode('choose' as any); onClose?.(); }} className="text-xs text-gray-400">✕</button>
            </div>
            {loading ? (
              <div className="text-xs text-gray-400 py-1">加载中...</div>
            ) : (
              <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
                {hotels.map(h => (
                  <button
                    key={h.id}
                    onClick={() => selectHotel(h)}
                    className="text-left px-2 py-1 rounded hover:bg-primary-50 text-xs"
                  >
                    {h.name} <span className="text-gray-400">{h.area}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // Full mode: for default hotel at top bar
  if (currentHotel) {
    return (
      <div className="flex items-center gap-3 px-4 py-2 bg-primary-50 border-b border-primary-200">
        <span className="text-sm text-primary-700">🏨 默认酒店：</span>
        <span className="font-medium text-primary-900">{currentHotel.name}</span>
        <span className="text-xs text-primary-600">{currentHotel.area}</span>
        <button onClick={() => { setDefaultHotel(null as any); }} className="ml-auto text-xs text-red-500 hover:underline">更换</button>
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
    // Search mode: filter from loaded POIs
    return (
      <div className="flex items-center gap-2 px-4 py-2 bg-white border-b">
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="输入酒店名称搜索..."
          className="flex-1 px-3 py-1.5 border rounded-lg text-sm"
          onKeyDown={e => {
            if (e.key === 'Enter' && query.trim()) {
              // Search in hotels list
              setMode('list');
            }
          }}
        />
        <button onClick={() => setMode('list')} className="text-xs text-gray-500 hover:underline">从列表选</button>
        <button onClick={() => setMode('choose')} className="text-xs text-gray-500 hover:underline">返回</button>
      </div>
    );
  }

  return (
    <div className="px-4 py-2 bg-white border-b">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-medium">选择默认酒店：</span>
        <button onClick={() => setMode('choose')} className="text-xs text-gray-500 hover:underline">返回</button>
      </div>
      {loading ? (
        <div className="text-sm text-gray-500 py-2">加载中...</div>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {hotels.map(h => (
            <button
              key={h.id}
              onClick={() => selectHotel(h)}
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
