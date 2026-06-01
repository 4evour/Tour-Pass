import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import PoiCard from './PoiCard';
import { useItineraryStore } from '../stores/itineraryStore';

interface TimelineProps {
  currentDay: number;
  onDayChange: (day: number) => void;
}

export default function Timeline({ currentDay, onDayChange }: TimelineProps) {
  const { days, hotel, addDay, removeDay, removeStop } = useItineraryStore();
  const currentDayPlan = days.find(d => d.day === currentDay);
  const stops = currentDayPlan?.stops || [];

  const { setNodeRef, isOver } = useDroppable({
    id: `timeline-day-${currentDay}`,
    data: { variant: 'timeline', day: currentDay },
  });

  const totalTravel = stops.reduce((s, st) => s + st.travelMinutes, 0);
  const totalVisit = stops.reduce((s, st) => s + (st.poi.visit_duration || 60), 0);

  const handleOptimize = async () => {
    if (stops.length < 2) return;
    try {
      const res = await fetch('/editor/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stops: stops.map(s => ({
            poi_name: s.poi.name,
            arrival: s.arrival,
            departure: s.departure,
            close_minutes: s.poi.close_minutes ?? 24 * 60,
          })),
        }),
      });
      const data = await res.json();
      if (data.valid) {
        alert('行程检查通过，无冲突！');
      } else {
        alert('发现 ' + data.issues.length + ' 个问题，请查看冲突提示。');
      }
    } catch {
      alert('检查失败，请稍后重试。');
    }
  };

  return (
    <div className="flex flex-col h-full bg-white border-l">
      {/* Day tabs */}
      <div className="flex items-center gap-1 px-3 py-2 border-b bg-gray-50">
        {days.map(d => (
          <button
            key={d.day}
            onClick={() => onDayChange(d.day)}
            className={`px-3 py-1 rounded-lg text-sm font-medium ${d.day === currentDay ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'}`}
          >
            Day {d.day}
          </button>
        ))}
        <button onClick={addDay} className="px-2 py-1 rounded-lg text-sm text-gray-500 hover:bg-gray-200">+</button>
        {days.length > 1 && (
          <button onClick={() => removeDay(currentDay)} className="ml-auto text-xs text-red-400 hover:text-red-600">删除当天</button>
        )}
      </div>

      {/* Stats */}
      {stops.length > 0 && (
        <div className="flex items-center gap-3 px-3 py-1.5 border-b text-xs text-gray-500">
          <span>🚶 通勤 {totalTravel} 分</span>
          <span>⏱ 游览 {totalVisit} 分</span>
          <span>📍 {stops.length} 站</span>
          <button onClick={handleOptimize} className="ml-auto px-2 py-0.5 bg-primary-500 text-white rounded text-xs hover:bg-primary-600">检查行程</button>
        </div>
      )}

      {/* Hotel start */}
      {hotel && (
        <div className="px-3 py-2 border-b bg-primary-50 text-xs text-primary-700">
          🏨 起点：{hotel.name}
        </div>
      )}

      {/* Sortable stops */}
      <div
        ref={setNodeRef}
        className={`flex-1 overflow-y-auto p-2 space-y-1 ${isOver ? 'bg-primary-50' : ''}`}
      >
        <SortableContext items={stops.map(s => s.id)} strategy={verticalListSortingStrategy}>
          {stops.map((stop, i) => (
            <PoiCard
              key={stop.id}
              poi={stop.poi}
              variant="timeline"
              stop={stop}
              index={i}
              onRemove={() => removeStop(currentDay, i)}
            />
          ))}
        </SortableContext>

        {stops.length === 0 && (
          <div className="text-center py-8 text-gray-400 text-sm">
            <div className="text-2xl mb-2">📋</div>
            从左侧拖拽 POI 到这里
            <br />
            或点击地图上的标记添加
          </div>
        )}
      </div>

      {/* Hotel end */}
      {hotel && stops.length > 0 && (
        <div className="px-3 py-2 border-t bg-primary-50 text-xs text-primary-700">
          🏨 终点：{hotel.name}
        </div>
      )}
    </div>
  );
}
