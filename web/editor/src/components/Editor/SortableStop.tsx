import React from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { Stop } from '../../types';

interface SortableStopProps {
  stop: Stop;
  dayIndex: number;
  stopIndex: number;
}

export const SortableStop: React.FC<SortableStopProps> = ({ stop, dayIndex, stopIndex }) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: `stop-${dayIndex}-${stopIndex}`,
    data: {
      dayIndex,
      stopIndex,
    },
  });
  
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={`p-3 mb-2 bg-white border rounded-lg cursor-grab hover:border-blue-300 ${
        isDragging ? 'border-blue-500 shadow-lg' : ''
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-6 h-6 flex items-center justify-center bg-blue-100 text-blue-600 rounded-full text-sm font-medium">
            {stopIndex + 1}
          </span>
          <span className="font-medium">{stop.poi.name}</span>
        </div>
        
        <div className="flex items-center gap-2 text-sm text-gray-500">
          {stop.arrival > 0 && (
            <span>{formatTime(stop.arrival)}</span>
          )}
          <span className="text-gray-300">|</span>
          <span>{stop.poi.visit_duration || 60}分钟</span>
        </div>
      </div>
    </div>
  );
};

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}
