import React, { useCallback } from 'react';
import MapView from '../MapView';
import { useEditorStore } from '../../stores/editorStore';
import { useItineraryStore } from '../../stores/itineraryStore';
import { useHistoryStore } from '../../stores/historyStore';
import { AddStopCommand } from '../../core/commands/AddStopCommand';
import type { Poi } from '../../types';

interface IntegratedMapProps {
  allPois: Poi[];
  hoveredPoiId?: string | null;
  currentDay?: number; // 1-indexed，优先使用 prop，否则从 editorStore 读取
  onDayChange?: (day: number) => void; // 当地图切换天数时回调
}

export const IntegratedMap: React.FC<IntegratedMapProps> = ({ allPois, hoveredPoiId, currentDay: propCurrentDay, onDayChange }) => {
  const { mode, currentDay: storeCurrentDay, enterDayEditMode, markChanged } = useEditorStore();
  const days = useItineraryStore(state => state.days);
  const setDays = useItineraryStore(state => state.setDays);
  const { execute } = useHistoryStore();
  
  const effectiveDay = propCurrentDay ?? (storeCurrentDay != null ? storeCurrentDay + 1 : 1); // 统一为 1-indexed

  const handleAddPoi = useCallback((poi: Poi) => {
    const dayIndex = effectiveDay - 1; // 转为 0-indexed
    const day = days[dayIndex];
    if (!day) return;

    const store = { days, setDays };
    const command = new AddStopCommand(store, dayIndex, poi, day.stops.length);
    execute(command);
    markChanged(`stop-${Date.now()}`, command.description);
  }, [effectiveDay, days, setDays, execute, markChanged]);

  const handleDayChange = useCallback((day: number) => {
    if (onDayChange) {
      onDayChange(day);
    } else if (mode === 'global') {
      enterDayEditMode(day);
    }
  }, [mode, enterDayEditMode, onDayChange]);
  
  return (
    <MapView
      allPois={allPois}
      hoveredPoiId={hoveredPoiId}
      onAddPoi={handleAddPoi}
      currentDay={effectiveDay}
      onDayChange={handleDayChange}
    />
  );
};