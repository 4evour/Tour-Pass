import React from 'react';
import { useItineraryStore } from '../../stores/itineraryStore';
import { ValidationPanel } from '../Validation/ValidationPanel';
import { PDFExporter } from '../Analytics/PDFExporter';
import { validateDay } from '../../core/validation/rules';

export const ReviewStep: React.FC = () => {
  const { days, cities, citySegments, hotelsByCity, totalDays, city, defaultHotel, setWizardStep } = useItineraryStore();
  
  // Run validation on all days
  const allIssues = days.flatMap(day => validateDay(day));
  const errors = allIssues.filter(i => i.severity === 'error');
  const warnings = allIssues.filter(i => i.severity === 'warning');
  
  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h2 className="text-2xl font-bold mb-2">行程校验</h2>
      <p className="text-gray-500 mb-6">检查行程安排是否合理</p>
      
      {/* Summary */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="p-4 bg-blue-50 rounded-lg text-center">
          <div className="text-2xl font-bold text-blue-600">{totalDays}</div>
          <div className="text-sm text-blue-500">天</div>
        </div>
        <div className="p-4 bg-green-50 rounded-lg text-center">
          <div className="text-2xl font-bold text-green-600">{cities.length}</div>
          <div className="text-sm text-green-500">个城市</div>
        </div>
        <div className="p-4 bg-purple-50 rounded-lg text-center">
          <div className="text-2xl font-bold text-purple-600">
            {days.reduce((sum, d) => sum + d.stops.length, 0)}
          </div>
          <div className="text-sm text-purple-500">个景点</div>
        </div>
      </div>
      
      {/* Route overview */}
      <div className="mb-6 p-4 bg-gray-50 rounded-lg">
        <h3 className="font-medium mb-2">行程路线</h3>
        <p className="text-sm text-gray-600">
          {cities.map((city, i) => (
            <span key={city}>
              {i > 0 && ' → '}
              <strong>{city}</strong>
              {hotelsByCity[city] && ` (${hotelsByCity[city].name})`}
            </span>
          ))}
        </p>
        {citySegments.length > 0 && (
          <div className="mt-2 text-sm text-gray-500">
            {citySegments.map(seg => (
              <div key={seg.id}>
                {seg.fromCity} → {seg.toCity}: {seg.departTime} - {seg.arriveTime} ({seg.transport})
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* Validation results */}
      <ValidationPanel issues={allIssues} />
      
      {/* Day summary */}
      <div className="mt-6 space-y-3">
        {days.map(day => (
          <div key={day.day} className="p-3 bg-white border rounded-lg">
            <div className="flex items-center justify-between">
              <span className="font-medium">第 {day.day} 天</span>
              <span className="text-sm text-gray-500">{day.stops.length} 个景点</span>
            </div>
            {day.stops.length > 0 && (
              <div className="text-sm text-gray-500 mt-1">
                {day.stops.map((stop, i) => (
                  <span key={stop.id}>
                    {i > 0 && ' → '}
                    {stop.poi.name}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      
      <div className="flex gap-3 mt-6">
        <button
          onClick={() => setWizardStep('plan')}
          className="px-6 py-3 bg-gray-200 rounded-lg hover:bg-gray-300"
        >
          ← 返回编排
        </button>
        <div className="flex-1" />
        <PDFExporter days={days} city={city} defaultHotel={defaultHotel} />
      </div>
    </div>
  );
};
