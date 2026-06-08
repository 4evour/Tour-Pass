import { useState, useEffect, useCallback } from 'react';
import { DndContext, DragEndEvent, DragOverlay, DragStartEvent, closestCorners } from '@dnd-kit/core';
import type { Poi } from './types';
import { useItineraryStore } from './stores/itineraryStore';
import { useRoute } from './hooks/useRoute';
import { CITY_EMOJI_MAP, DROPDOWN_FALLBACK_CITIES } from './constants/cities';
import HotelPicker from './components/HotelPicker';
import MapView from './components/MapView';
import Sidebar from './components/Sidebar';
import Timeline from './components/Timeline';
import AiRecommend from './components/AiRecommend';
import ConflictAlert from './components/ConflictAlert';
import AiChat from './components/AiChat';
import EditorToolbar from './components/EditorToolbar';

export default function App() {
  const [pois, setPois] = useState<Poi[]>([]);
  const [currentDay, setCurrentDay] = useState(1);
  const [activePoi, setActivePoi] = useState<Poi | null>(null);
  const [cityOptions, setCityOptions] = useState<{ value: string; label: string }[]>(DROPDOWN_FALLBACK_CITIES);
  const { city, defaultHotel, setCity, addStop, moveStopBetweenDays, resetEditor } = useItineraryStore();

  useRoute();

  // Load city list from backend and keep local options in sync
  useEffect(() => {
    let cancelled = false;

    fetch('/cities')
      .then(r => r.json())
      .then(data => {
        if (cancelled) return;
        const apiCities: { name: string }[] = data.cities || [];
        const options = apiCities.map(item => ({
          value: item.name,
          label: `${CITY_EMOJI_MAP[item.name] ? CITY_EMOJI_MAP[item.name] + ' ' : ''}${item.name}`,
        }));
        setCityOptions(options.length > 0 ? options : DROPDOWN_FALLBACK_CITIES);

        if (!city) {
          const fallbackFromApi: string = data.default || apiCities[0]?.name || '';
          if (fallbackFromApi) setCity(fallbackFromApi);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCityOptions(DROPDOWN_FALLBACK_CITIES);
          if (!city) setCity('武汉');
        }
      });

    return () => { cancelled = true; };
  }, []);

  // Load POIs when city changes
  useEffect(() => {
    if (!city) return;
    fetch(`/poi/search?city=${encodeURIComponent(city)}&limit=500`)
      .then(r => r.json())
      .then(data => setPois(data.data || []))
      .catch(() => {});
  }, [city]);

  const handleAddFromMap = useCallback((poi: Poi) => {
    addStop(currentDay, poi);
  }, [currentDay, addStop]);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const data = event.active.data.current;
    if (data?.poi) setActivePoi(data.poi);
  }, []);

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    setActivePoi(null);
    const { active, over } = event;
    if (!over) return;

    const activeData = active.data.current;
    const overData = over.data.current;

    // Sidebar -> Timeline: add POI to day
    if (activeData?.variant === 'sidebar') {
      let targetDay: number | null = null;
      if (overData?.variant === 'timeline') {
        targetDay = overData.day as number;
      } else if (String(over.id).startsWith('timeline-day-')) {
        targetDay = parseInt(String(over.id).split('-').pop() || '1');
      }
      if (targetDay) {
        addStop(targetDay, activeData.poi as Poi);
      }
      return;
    }

    // Timeline -> Timeline: reorder within day or cross-day move
    if (activeData?.variant === 'timeline') {
      const fromDay = activeData.day as number;
      const fromIndex = activeData.index as number;

      if (overData?.variant === 'timeline') {
        const toDay = overData.day as number;
        const toIndex = overData.index as number;
        if (fromDay === toDay && fromIndex === toIndex) return;
        if (fromDay === toDay) {
          useItineraryStore.getState().reorderStops(fromDay, fromIndex, toIndex);
        } else {
          moveStopBetweenDays(fromDay, fromIndex, toDay, toIndex);
          setCurrentDay(toDay);
        }
      } else if (String(over.id).startsWith('timeline-day-')) {
        // Dropped on a day container (not a specific stop)
        const toDay = parseInt(String(over.id).split('-').pop() || '1');
        if (fromDay !== toDay) {
          const toStops = useItineraryStore.getState().getStopsForDay(toDay);
          moveStopBetweenDays(fromDay, fromIndex, toDay, toStops.length);
          setCurrentDay(toDay);
        }
      }
    }
  }, [addStop, moveStopBetweenDays]);

  const handleCityChange = useCallback((newCity: string) => {
    setCity(newCity);
  }, [setCity]);

  return (
    <DndContext collisionDetection={closestCorners} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="flex flex-col h-screen">
        {/* Top bar */}
        <div className="flex items-center gap-4 px-4 py-2 bg-white border-b shadow-sm z-10">
          <h1 className="text-lg font-bold text-primary-700">🗺 Tour Pass 编辑器</h1>
          <select
            value={city}
            onChange={e => handleCityChange(e.target.value)}
            className="px-2 py-1 border rounded text-sm"
          >
            {cityOptions.map(c => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          <button
            onClick={resetEditor}
            className="px-2 py-1 text-xs text-gray-500 hover:text-red-600 border rounded"
            title="清除所有数据，重新开始"
          >
            🗑 重置
          </button>
          <div className="flex-1" />
          <span className="text-xs text-gray-400">
            {defaultHotel ? `🏨 ${defaultHotel.name}` : '未选酒店'}
          </span>
          <EditorToolbar allPois={pois} />
          <a href="/" className="text-sm text-gray-500 hover:text-primary-600">← 返回首页</a>
        </div>

        {/* Hotel picker */}
        <HotelPicker city={city} />

        {/* Main content: 3-column layout */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: POI sidebar */}
          <div className="w-64 flex-shrink-0">
            <Sidebar pois={pois} />
          </div>

          {/* Center: Map */}
          <div className="flex-1 relative">
            <MapView allPois={pois} onAddPoi={handleAddFromMap} currentDay={currentDay} onDayChange={setCurrentDay} />
            <AiRecommend allPois={pois} onAdd={(poi) => addStop(currentDay, poi)} />
            <ConflictAlert />
          </div>

          {/* Right: Timeline */}
          <div className="w-72 flex-shrink-0">
            <Timeline currentDay={currentDay} onDayChange={setCurrentDay} allPois={pois} />
          </div>
        </div>
      </div>

      {/* Drag overlay */}
      <DragOverlay>
        {activePoi && (
          <div className="px-3 py-2 bg-white rounded-lg border-2 border-primary-500 shadow-lg text-sm font-medium">
            {getIcon(activePoi.type)} {activePoi.name}
          </div>
        )}
      </DragOverlay>

      {/* AI Chat */}
      <AiChat city={city} />
    </DndContext>
  );
}

function getIcon(type: string): string {
  const icons: Record<string, string> = { attraction: '🏛', restaurant: '🍜', hotel: '🏨', nightlife: '🌙', transit: '🚌' };
  return icons[type] || '📍';
}
