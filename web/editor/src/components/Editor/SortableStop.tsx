import React from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { Stop } from '../../types';

interface SortableStopProps {
  stop: Stop;
  dayIndex: number;
  stopIndex: number;
  onRemove: (dayIndex: number, stopIndex: number) => void;
}

export const SortableStop: React.FC<SortableStopProps> = ({ stop, dayIndex, stopIndex, onRemove }) => {
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
      className={`p-3 mb-2 bg-white border rounded-lg hover:border-blue-300 group ${
        isDragging ? 'border-blue-500 shadow-lg' : ''
      }`}
    >
      <div className="flex items-center justify-between">
        {/* 拖拽手柄 */}
        <div {...attributes} {...listeners} className="flex items-center gap-2 flex-1 cursor-grab min-w-0">
          <span className="w-6 h-6 flex items-center justify-center bg-blue-100 text-blue-600 rounded-full text-sm font-medium flex-shrink-0">
            {stopIndex + 1}
          </span>
          <span className="font-medium truncate">{stop.poi.name}</span>
        </div>

        <div className="flex items-center gap-2 ml-2">
          <span className="text-xs text-gray-400 flex-shrink-0">
            {stop.arrival > 0 ? formatTime(stop.arrival) : '--:--'}
          </span>
          {/* 删除按钮 */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemove(dayIndex, stopIndex);
            }}
            className="text-red-400 hover:text-red-600 hover:bg-red-50 rounded p-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
            title="删除此景点"
          >
            ✕
          </button>
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
