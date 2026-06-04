import React from 'react';
import type { DayPlan, Stop } from '../../types';

interface TimelineViewProps {
  day: DayPlan;
  onStopClick: (stop: Stop, index: number) => void;
}

export const TimelineView: React.FC<TimelineViewProps> = ({ day, onStopClick }) => {
  return (
    <div className="relative">
      {/* 时间轴线 */}
      <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-gray-200" />
      
      <div className="space-y-4">
        {day.stops.map((stop, index) => (
          <TimelineItem
            key={stop.id}
            stop={stop}
            index={index}
            isLast={index === day.stops.length - 1}
            onClick={() => onStopClick(stop, index)}
          />
        ))}
      </div>
      
      {day.stops.length === 0 && (
        <div className="text-center py-8 text-gray-400">
          还没有添加景点
        </div>
      )}
    </div>
  );
};

interface TimelineItemProps {
  stop: Stop;
  index: number;
  isLast: boolean;
  onClick: () => void;
}

const TimelineItem: React.FC<TimelineItemProps> = ({ stop, index, isLast, onClick }) => {
  const duration = stop.poi.visit_duration || 60;
  
  return (
    <div
      className="relative flex items-start gap-4 cursor-pointer hover:bg-gray-50 p-2 rounded-lg"
      onClick={onClick}
    >
      {/* 时间轴圆点 */}
      <div className="relative z-10 flex-shrink-0">
        <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
          <span className="text-blue-600 font-bold">{index + 1}</span>
        </div>
      </div>
      
      {/* 内容 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <h4 className="font-medium text-gray-900 truncate">{stop.poi.name}</h4>
          <span className="text-sm text-gray-500">{duration}分钟</span>
        </div>
        
        <div className="mt-1 flex items-center gap-2 text-sm text-gray-500">
          {stop.arrival > 0 && (
            <span>{formatTime(stop.arrival)}</span>
          )}
          {stop.arrival > 0 && stop.departure > 0 && (
            <span>→ {formatTime(stop.departure)}</span>
          )}
        </div>
        
        {stop.poi.area && (
          <p className="mt-1 text-sm text-gray-400">{stop.poi.area}</p>
        )}
        
        {stop.travelMinutes > 0 && !isLast && (
          <div className="mt-2 flex items-center gap-1 text-xs text-gray-400">
            <span>🚗</span>
            <span>步行 {stop.travelMinutes} 分钟到下一站</span>
          </div>
        )}
      </div>
    </div>
  );
};

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}
