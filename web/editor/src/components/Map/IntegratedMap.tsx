import React, { useCallback } from 'react';
import MapView from '../MapView';
import { useEditorStore } from '../../stores/editorStore';
import { useItineraryStore } from '../../stores/itineraryStore';
import { useHistoryStore } from '../../stores/historyStore';
import { AddStopCommand } from '../../core/commands/AddStopCommand';
import type { Poi } from '../../types';

interface IntegratedMapProps {
  allPois: Poi[];
}

export const IntegratedMap: React.FC<IntegratedMapProps> = ({ allPois }) => {
  const { mode, currentDay, enterDayEditMode, markChanged } = useEditorStore();
  const days = useItineraryStore(state => state.days);
  const setDays = useItineraryStore(state => state.setDays);
  const { execute } = useHistoryStore();
  
  const handleAddPoi = useCallback((poi: Poi) => {
    const dayIndex = currentDay ?? 0;
    const day = days[dayIndex];
    if (!day) return;
    
    const store = { days, setDays };
    const command = new AddStopCommand(store, dayIndex, poi, day.stops.length);
    execute(command);
    markChanged(`stop-${Date.now()}`, command.description);
  }, [currentDay, days, setDays, execute, markChanged]);
  
  const handleDayChange = useCallback((day: number) => {
    if (mode === 'global') {
      enterDayEditMode(day);
    }
  }, [mode, enterDayEditMode]);
  
  return (
    <MapView
      allPois={allPois}
      onAddPoi={handleAddPoi}
      currentDay={currentDay ?? 0}
      onDayChange={handleDayChange}
    />
  );
};
