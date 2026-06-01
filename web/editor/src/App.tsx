import { useState, useEffect, useCallback } from 'react';
import { DndContext, DragEndEvent, DragOverlay, DragStartEvent, pointerWithin } from '@dnd-kit/core';
import type { Poi } from './types';
import { useItineraryStore } from './stores/itineraryStore';
import { useRoute } from './hooks/useRoute';
import HotelPicker from './components/HotelPicker';
import MapView from './components/MapView';
import Sidebar from './components/Sidebar';
import Timeline from './components/Timeline';
import AiRecommend from './components/AiRecommend';
import ConflictAlert from './components/ConflictAlert';

export default function App() {
  const [city, setCity] = useState('');
  const [pois, setPois] = useState<Poi[]>([]);
  const [currentDay, setCurrentDay] = useState(1);
  const [activePoi, setActivePoi] = useState<Poi | null>(null);
  const { hotel, addStop } = useItineraryStore();

  useRoute();

  // Load city and POIs
  useEffect(() => {
    fetch('/cities')
      .then(r => r.json())
      .then(data => {
        const firstCity = data.cities?.[0]?.name || data[0]?.name || '';
        setCity(firstCity);
      })
      .catch(() => setCity('wuhan'));
  }, []);

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

    // Sidebar -> Timeline: add POI
    if (activeData?.variant === 'sidebar' && overData?.variant === 'timeline') {
      const poi = activeData.poi as Poi;
      const day = overData.day as number;
      addStop(day, poi);
      return;
    }

    // Sidebar -> Timeline droppable area
    if (activeData?.variant === 'sidebar' && String(over.id).startsWith('timeline-day-')) {
      const poi = activeData.poi as Poi;
      const day = parseInt(String(over.id).split('-').pop() || '1');
      addStop(day, poi);
    }
  }, [addStop]);

  return (
    <DndContext collisionDetection={pointerWithin} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="flex flex-col h-screen">
        {/* Top bar */}
        <div className="flex items-center gap-4 px-4 py-2 bg-white border-b shadow-sm z-10">
          <h1 className="text-lg font-bold text-primary-700">🗺 Tour Pass 编辑器</h1>
          <select
            value={city}
            onChange={e => setCity(e.target.value)}
            className="px-2 py-1 border rounded text-sm"
          >
            <option value="wuhan">武汉</option>
            <option value="changsha">长沙</option>
            <option value="beijing">北京</option>
            <option value="shanghai">上海</option>
            <option value="chengdu">成都</option>
          </select>
          <div className="flex-1" />
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
            <MapView allPois={pois} onAddPoi={handleAddFromMap} />
            <AiRecommend allPois={pois} onAdd={(poi) => addStop(currentDay, poi)} />
            <ConflictAlert />
          </div>

          {/* Right: Timeline */}
          <div className="w-72 flex-shrink-0">
            <Timeline currentDay={currentDay} onDayChange={setCurrentDay} />
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
    </DndContext>
  );
}

function getIcon(type: string): string {
  const icons: Record<string, string> = { attraction: '🏛', restaurant: '🍜', hotel: '🏨', nightlife: '🌙', transit: '🚌' };
  return icons[type] || '📍';
}
