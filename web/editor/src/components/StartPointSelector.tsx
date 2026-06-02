import { useState } from 'react';
import type { Poi, StartPointType } from '../types';
import { useItineraryStore } from '../stores/itineraryStore';

const START_TYPES: { type: StartPointType; label: string; icon: string }[] = [
  { type: 'hotel', label: '酒店', icon: '🏨' },
  { type: 'station', label: '火车站', icon: '🚉' },
  { type: 'airport', label: '机场', icon: '✈️' },
  { type: 'custom', label: '自定义', icon: '📍' },
];

export default function StartPointSelector({ day }: { day: number }) {
  const { days, setDayStartPoint, getStartPoi } = useItineraryStore();
  const dayPlan = days.find(d => d.day === day);
  const startPoint = dayPlan?.startPoint ?? { type: 'hotel' as StartPointType, poi: null };
  const startPoi = getStartPoi(day);
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Poi[]>([]);

  const handleTypeChange = (type: StartPointType) => {
    if (type === 'hotel') {
      setDayStartPoint(day, { type, poi: null });
    } else if (type === 'station' || type === 'airport') {
      setShowSearch(true);
      setSearchQuery('');
    } else {
      setShowSearch(true);
      setSearchQuery('');
    }
  };

  const handleSearch = async (q: string) => {
    setSearchQuery(q);
    if (q.length < 1) { setSearchResults([]); return; }
    try {
      const city = useItineraryStore.getState().city;
      const typeFilter = startPoint.type === 'station' ? '&type=transit' : startPoint.type === 'airport' ? '&type=transit' : '';
      const res = await fetch(`/poi/search?city=${encodeURIComponent(city)}&limit=10${typeFilter}&q=${encodeURIComponent(q)}`);
      const data = await res.json();
      setSearchResults(data.data || []);
    } catch { setSearchResults([]); }
  };

  const selectPoi = (poi: Poi) => {
    setDayStartPoint(day, { type: startPoint.type, poi });
    setShowSearch(false);
    setSearchResults([]);
  };

  return (
    <div className="px-3 py-1.5 border-b bg-gray-50 text-xs">
      <div className="flex items-center gap-1">
        <span className="text-gray-500">🏁 起点：</span>
        {START_TYPES.map(t => (
          <button
            key={t.type}
            onClick={() => handleTypeChange(t.type)}
            className={`px-1.5 py-0.5 rounded text-xs ${startPoint.type === t.type ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'}`}
          >
            {t.icon}
          </button>
        ))}
        <span className="ml-1 text-gray-600 truncate max-w-[120px]">
          {startPoi?.name || '未设置'}
        </span>
      </div>
      {showSearch && (
        <div className="mt-1">
          <input
            value={searchQuery}
            onChange={e => handleSearch(e.target.value)}
            placeholder="搜索起点位置..."
            className="w-full px-2 py-1 border rounded text-xs"
            autoFocus
          />
          {searchResults.length > 0 && (
            <div className="mt-1 border rounded bg-white max-h-32 overflow-y-auto">
              {searchResults.map(p => (
                <button
                  key={p.id}
                  onClick={() => selectPoi(p)}
                  className="w-full text-left px-2 py-1 hover:bg-primary-50 text-xs"
                >
                  {p.name} <span className="text-gray-400">{p.area}</span>
                </button>
              ))}
            </div>
          )}
          <button onClick={() => setShowSearch(false)} className="mt-1 text-gray-400 hover:text-gray-600">取消</button>
        </div>
      )}
    </div>
  );
}
