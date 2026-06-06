import React, { useState, useEffect } from 'react';
import { useItineraryStore } from '../../stores/itineraryStore';
import { DayEditor } from '../Editor/DayEditor';
import { IntegratedMap } from '../Map/IntegratedMap';
import type { Poi } from '../../types';

export const PlanStep: React.FC = () => {
  const { cities, hotelsByCity, totalDays, wizardStep, setWizardStep, days } = useItineraryStore();
  const [currentDay, setCurrentDay] = useState(1);
  const [allPois, setAllPois] = useState<Poi[]>([]);
  
  // Load POIs for current city
  const currentCity = cities.length > 0 ? cities[0] : '';
  const currentHotel = hotelsByCity[currentCity];
  
  useEffect(() => {
    if (!currentCity) return;
    fetch(`/poi/search?city=${encodeURIComponent(currentCity)}&limit=200`)
      .then(r => r.json())
      .then(data => setAllPois(data.data || []))
      .catch(() => {});
  }, [currentCity]);

  return (
    <div className="flex flex-col h-[calc(100vh-120px)]">
      {/* Day tabs */}
      <div className="flex gap-1 px-4 py-2 bg-white border-b overflow-x-auto">
        {Array.from({ length: totalDays }, (_, i) => i + 1).map(day => (
          <button
            key={day}
            onClick={() => setCurrentDay(day)}
            className={`px-3 py-1.5 rounded text-sm whitespace-nowrap ${
              currentDay === day
                ? 'bg-blue-500 text-white'
                : 'bg-gray-100 hover:bg-gray-200'
            }`}
          >
            第{day}天
          </button>
        ))}
      </div>
      
      <div className="flex flex-1 overflow-hidden">
        {/* Left: POI sidebar */}
        <div className="w-72 border-r overflow-y-auto p-3">
          <h3 className="font-medium text-gray-700 mb-2">推荐景点</h3>
          <div className="space-y-1">
            {allPois
              .filter(p => p.type === 'attraction')
              .sort((a, b) => (b.popularity || 0) - (a.popularity || 0))
              .slice(0, 10)
              .map(poi => (
                <div key={poi.id} className="p-2 text-sm bg-gray-50 rounded hover:bg-gray-100">
                  <span className="font-medium">{poi.name}</span>
                  {poi.area && <span className="text-gray-400 ml-1">· {poi.area}</span>}
                </div>
              ))
            }
          </div>
        </div>
        
        {/* Center: Timeline editor */}
        <div className="flex-1 overflow-y-auto">
          <DayEditor dayIndex={currentDay - 1} />
        </div>
        
        {/* Right: Map */}
        <div className="w-96 border-l">
          <IntegratedMap allPois={allPois} />
        </div>
      </div>
      
      {/* Bottom nav */}
      <div className="flex gap-3 px-4 py-3 bg-white border-t">
        <button
          onClick={() => setWizardStep('hotels')}
          className="px-6 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
        >
          ← 上一步
        </button>
        <div className="flex-1" />
        <button
          onClick={() => setWizardStep('review')}
          className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
        >
          下一步：校验 →
        </button>
      </div>
    </div>
  );
};
