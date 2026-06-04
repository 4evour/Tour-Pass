import React, { useState } from 'react';
import {
  DndContext,
  DragEndEvent,
  DragStartEvent,
  DragOverlay,
  closestCorners,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { useItineraryStore } from '../../stores/itineraryStore';
import { useHistoryStore } from '../../stores/historyStore';
import { useEditorStore } from '../../stores/editorStore';
import { MoveBetweenDaysCommand } from '../../core/commands/MoveBetweenDaysCommand';
import { ReorderCommand } from '../../core/commands/ReorderCommand';
import { SortableStop } from './SortableStop';
import type { Poi, Stop } from '../../types';

interface MultiDayTimelineProps {
  allPois: Poi[];
}

export const MultiDayTimeline: React.FC<MultiDayTimelineProps> = ({ allPois }) => {
  const days = useItineraryStore(state => state.days);
  const setDays = useItineraryStore(state => state.setDays);
  const { execute } = useHistoryStore();
  const { markChanged, enterDayEditMode } = useEditorStore();
  
  const [activeStop, setActiveStop] = useState<Stop | null>(null);
  const [activeDay, setActiveDay] = useState<number | null>(null);
  
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );
  
  const handleDragStart = (event: DragStartEvent) => {
    const { active } = event;
    const dayIndex = active.data.current?.dayIndex;
    const stopIndex = active.data.current?.stopIndex;
    
    if (dayIndex !== undefined && stopIndex !== undefined) {
      setActiveStop(days[dayIndex].stops[stopIndex]);
      setActiveDay(dayIndex);
    }
  };
  
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    
    if (!over || !activeStop) {
      setActiveStop(null);
      setActiveDay(null);
      return;
    }
    
    const activeDayIndex = active.data.current?.dayIndex;
    const activeStopIndex = active.data.current?.stopIndex;
    const overDayIndex = over.data.current?.dayIndex;
    const overStopIndex = over.data.current?.stopIndex;
    
    if (activeDayIndex === undefined || activeStopIndex === undefined ||
        overDayIndex === undefined || overStopIndex === undefined) {
      setActiveStop(null);
      setActiveDay(null);
      return;
    }
    
    const store = { days, setDays };
    
    // 跨天移动
    if (activeDayIndex !== overDayIndex) {
      const command = new MoveBetweenDaysCommand(
        store,
        activeDayIndex,
        activeStopIndex,
        overDayIndex,
        overStopIndex
      );
      execute(command);
      markChanged(`stop-${activeStop.id}`, command.description);
    }
    // 同天重排序
    else if (activeStopIndex !== overStopIndex) {
      const command = new ReorderCommand(
        store,
        activeDayIndex,
        activeStopIndex,
        overStopIndex
      );
      execute(command);
      markChanged(`stop-${activeStop.id}`, command.description);
    }
    
    setActiveStop(null);
    setActiveDay(null);
  };
  
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="space-y-4">
        {days.map((day, dayIndex) => (
          <div
            key={day.day}
            className="border rounded-lg overflow-hidden"
          >
            <div
              className="flex items-center justify-between px-4 py-2 bg-gray-50 cursor-pointer hover:bg-gray-100"
              onClick={() => enterDayEditMode(dayIndex)}
            >
              <h3 className="font-medium text-gray-700">
                第{day.day}天
                <span className="ml-2 text-sm text-gray-500">
                  {day.stops.length} 个景点
                </span>
              </h3>
              <button
                className="text-sm text-blue-500 hover:text-blue-700"
                onClick={(e) => {
                  e.stopPropagation();
                  enterDayEditMode(dayIndex);
                }}
              >
                编辑
              </button>
            </div>
            
            <div className="p-3">
              <SortableContext
                items={day.stops.map((_, i) => `stop-${dayIndex}-${i}`)}
                strategy={verticalListSortingStrategy}
              >
                {day.stops.map((stop, stopIndex) => (
                  <SortableStop
                    key={stop.id}
                    stop={stop}
                    dayIndex={dayIndex}
                    stopIndex={stopIndex}
                  />
                ))}
              </SortableContext>
              
              {day.stops.length === 0 && (
                <p className="text-gray-400 text-center py-4 text-sm">
                  还没有添加景点
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
      
      <DragOverlay>
        {activeStop && (
          <div className="p-3 bg-white border-2 border-blue-500 rounded-lg shadow-lg">
            <span className="font-medium">{activeStop.poi.name}</span>
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
};
