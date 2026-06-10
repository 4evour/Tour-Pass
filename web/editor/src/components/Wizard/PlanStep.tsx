import React, { useState, useEffect, useMemo } from 'react';
import { useItineraryStore } from '../../stores/itineraryStore';
import { useEditorStore } from '../../stores/editorStore';
import { DayEditor } from '../Editor/DayEditor';
import { IntegratedMap } from '../Map/IntegratedMap';
import type { Poi, PoiTypeFilter } from '../../types';

const TYPE_LABELS: Record<string, string> = {
  attraction: '🏛 景点',
  restaurant: '🍜 餐厅',
  nightlife: '🌙 夜生活',
  hotel: '🏨 酒店',
  transit: '🚇 交通',
};

export const PlanStep: React.FC = () => {
  const { cities, hotelsByCity, totalDays, wizardStep, setWizardStep, days, addStop, syncDaysFromTotal } = useItineraryStore();
  const { enterDayEditMode } = useEditorStore();
  const [currentDay, setCurrentDayState] = useState(1);
  const [allPois, setAllPois] = useState<Poi[]>([]);
  const [typeFilter, setTypeFilter] = useState<PoiTypeFilter>('all');
  const [searchText, setSearchText] = useState('');
  const [hoveredPoiId, setHoveredPoiId] = useState<string | null>(null);

  const currentCity = cities.length > 0 ? cities[0] : '';

  // 挂载时同步 totalDays → days 数组，确保每个 day 都有对应的 DayPlan 条目
  useEffect(() => {
    syncDaysFromTotal();
  }, [syncDaysFromTotal]);

  const setCurrentDay = (day: number) => {
    setCurrentDayState(day);
    // 同步到 editorStore，让 IntegratedMap 知道当前是第几天
    enterDayEditMode(day - 1); // editorStore 用 0-indexed
  };

  useEffect(() => {
    if (!currentCity) return;
    fetch(`/poi/browse?city=${encodeURIComponent(currentCity)}&limit=500`)
      .then(r => r.json())
      .then(data => setAllPois(data.data || []))
      .catch(() => {});
  }, [currentCity]);

  const filteredPois = useMemo(() => {
    let list = allPois;
    if (typeFilter !== 'all') list = list.filter(p => p.type === typeFilter);
    if (searchText) {
      const q = searchText.toLowerCase();
      list = list.filter(p => p.name.toLowerCase().includes(q) || (p.area || '').toLowerCase().includes(q));
    }
    return list.sort((a, b) => (b.popularity || 0) - (a.popularity || 0));
  }, [allPois, typeFilter, searchText]);

  const handleAddPoi = (poi: Poi) => {
    addStop(currentDay, poi);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-120px)]">
      {/* Day tabs */}
      <div className="flex gap-1 px-4 py-2 bg-white border-b overflow-x-auto">
        {Array.from({ length: totalDays }, (_, i) => i + 1).map(day => (
          <button
            key={day}
            onClick={() => setCurrentDay(day)}
            className={`px-3 py-1.5 rounded text-sm whitespace-nowrap ${
              currentDay === day ? 'bg-blue-500 text-white' : 'bg-gray-100 hover:bg-gray-200'
            }`}
          >
            第{day}天
          </button>
        ))}
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: POI sidebar */}
        <div className="w-56 border-r flex flex-col">
          <div className="p-3 border-b">
            <input
              type="text"
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              placeholder="搜索景点..."
              className="w-full px-2 py-1.5 border rounded text-sm"
            />
            <div className="flex gap-1 mt-2 flex-wrap">
              {(['all', 'attraction', 'restaurant', 'nightlife'] as PoiTypeFilter[]).map(t => (
                <button
                  key={t}
                  onClick={() => setTypeFilter(t)}
                  className={`px-2 py-0.5 rounded text-xs ${
                    typeFilter === t ? 'bg-blue-500 text-white' : 'bg-gray-100 hover:bg-gray-200'
                  }`}
                >
                  {t === 'all' ? '全部' : TYPE_LABELS[t] || t}
                </button>
              ))}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {filteredPois.slice(0, 100).map(poi => (
              <button
                key={poi.id}
                onClick={() => handleAddPoi(poi)}
                onMouseEnter={() => setHoveredPoiId(poi.id)}
                onMouseLeave={() => setHoveredPoiId(null)}
                className="w-full text-left p-2 text-sm bg-gray-50 rounded hover:bg-blue-50 hover:border-blue-300 border border-transparent transition-colors flex items-center justify-between group"
              >
                <div className="min-w-0">
                  <span className="font-medium truncate block">{poi.name}</span>
                  {poi.area && <span className="text-gray-400 text-xs">· {poi.area}</span>}
                </div>
                <span className="text-blue-500 text-xs opacity-0 group-hover:opacity-100 flex-shrink-0 ml-1">+ 添加</span>
              </button>
            ))}
            {filteredPois.length === 0 && (
              <div className="text-center text-gray-400 text-sm py-4">暂无数据</div>
            )}
          </div>
        </div>

        {/* Center: Timeline editor */}
        <div className="w-72 overflow-y-auto border-r">
          <DayEditor dayIndex={currentDay - 1} />
        </div>

        {/* Right: Map */}
        <div className="flex-1 border-l min-w-0">
          <IntegratedMap allPois={allPois} hoveredPoiId={hoveredPoiId} currentDay={currentDay} onDayChange={setCurrentDay} />
        </div>
      </div>

      {/* Bottom nav */}
      <div className="flex gap-3 px-4 py-3 bg-white border-t">
        <button onClick={() => setWizardStep('hotels')} className="px-6 py-2 bg-gray-200 rounded-lg hover:bg-gray-300">
          ← 上一步
        </button>
        <div className="flex-1" />
        <button onClick={() => setWizardStep('review')} className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">
          下一步：校验 →
        </button>
      </div>
    </div>
  );
};
