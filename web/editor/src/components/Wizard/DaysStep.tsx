import React from 'react';
import { useItineraryStore } from '../../stores/itineraryStore';

export const DaysStep: React.FC = () => {
  const { totalDays, setTotalDays, setWizardStep } = useItineraryStore();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-8">
      <h2 className="text-2xl font-bold mb-2">设置旅行天数</h2>
      <p className="text-gray-500 mb-8">选择你的旅行总天数</p>
      
      <div className="flex items-center gap-6 mb-8">
        <button
          onClick={() => setTotalDays(Math.max(1, totalDays - 1))}
          className="w-12 h-12 rounded-full bg-gray-200 hover:bg-gray-300 text-xl font-bold"
        >
          -
        </button>
        <div className="text-center">
          <span className="text-6xl font-bold text-blue-600">{totalDays}</span>
          <span className="text-2xl text-gray-500 ml-2">天</span>
        </div>
        <button
          onClick={() => setTotalDays(Math.min(14, totalDays + 1))}
          className="w-12 h-12 rounded-full bg-gray-200 hover:bg-gray-300 text-xl font-bold"
        >
          +
        </button>
      </div>
      
      <div className="flex gap-2 mb-8">
        {[1, 2, 3, 5, 7].map(d => (
          <button
            key={d}
            onClick={() => setTotalDays(d)}
            className={`px-4 py-2 rounded-lg text-sm ${
              totalDays === d ? 'bg-blue-500 text-white' : 'bg-gray-100 hover:bg-gray-200'
            }`}
          >
            {d}天
          </button>
        ))}
      </div>
      
      <button
        onClick={() => setWizardStep('cities')}
        className="px-8 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-lg"
      >
        下一步：选择城市 →
      </button>
    </div>
  );
};
