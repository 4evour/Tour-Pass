import React, { useState, useEffect } from 'react';
import { EditorLayout } from './components/Layout/EditorLayout';
import { DayEditor } from './components/Editor/DayEditor';
import { IntegratedMap } from './components/Map/IntegratedMap';
import { HotelManager } from './components/Hotel/HotelManager';
import { useEditorStore } from './stores/editorStore';
import { useItineraryStore } from './stores/itineraryStore';
import { useMapSync } from './hooks/useMapSync';
import { useValidation } from './hooks/useValidation';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import type { Poi } from './types';

export default function NewEditorApp() {
  useKeyboardShortcuts();
  
  const { mode, currentDay } = useEditorStore();
  const { visibleStops, mapCenter } = useMapSync();
  const { issues } = useValidation();
  const city = useItineraryStore(state => state.city);
  
  const [allPois, setAllPois] = useState<Poi[]>([]);
  const [showHotelPanel, setShowHotelPanel] = useState(false);
  
  useEffect(() => {
    fetch('/pois')
      .then(r => r.json())
      .then(data => setAllPois(data))
      .catch(() => {});
  }, []);
  
  const sidebarContent = (
    <div className="p-4">
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setShowHotelPanel(false)}
          className={`px-3 py-1.5 text-sm rounded ${
            !showHotelPanel ? 'bg-blue-500 text-white' : 'bg-gray-100'
          }`}
        >
          行程
        </button>
        <button
          onClick={() => setShowHotelPanel(true)}
          className={`px-3 py-1.5 text-sm rounded ${
            showHotelPanel ? 'bg-blue-500 text-white' : 'bg-gray-100'
          }`}
        >
          酒店
        </button>
      </div>
      
      {showHotelPanel ? (
        <HotelManager city={city} />
      ) : mode === 'day' && currentDay !== null ? (
        <DayEditor dayIndex={currentDay} />
      ) : (
        <div>
          <h2 className="text-lg font-semibold mb-4">行程概览</h2>
          <p className="text-gray-500">
            点击某天进入编辑模式
          </p>
        </div>
      )}
    </div>
  );
  
  const mapContent = (
    <IntegratedMap allPois={allPois} />
  );
  
  return (
    <EditorLayout
      sidebar={sidebarContent}
      map={mapContent}
      validationIssues={issues}
    >
      <div />
    </EditorLayout>
  );
}
