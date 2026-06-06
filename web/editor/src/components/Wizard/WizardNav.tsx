import React from 'react';
import { useItineraryStore } from '../../stores/itineraryStore';
import type { WizardStep } from '../../types';

const STEPS: { key: WizardStep; label: string; icon: string }[] = [
  { key: 'days', label: '天数', icon: '📅' },
  { key: 'cities', label: '城市', icon: '🏙️' },
  { key: 'segments', label: '跨城', icon: '🚄' },
  { key: 'hotels', label: '酒店', icon: '🏨' },
  { key: 'plan', label: '编排', icon: '🗺️' },
  { key: 'review', label: '校验', icon: '✅' },
];

export const WizardNav: React.FC = () => {
  const { wizardStep, setWizardStep, cities } = useItineraryStore();
  const currentIdx = STEPS.findIndex(s => s.key === wizardStep);
  
  // Skip segments step if only one city
  const visibleSteps = cities.length <= 1 
    ? STEPS.filter(s => s.key !== 'segments')
    : STEPS;

  return (
    <div className="flex items-center gap-1 px-4 py-2 bg-white border-b sticky top-0 z-10">
      {visibleSteps.map((step, idx) => {
        const isActive = step.key === wizardStep;
        const isPast = visibleSteps.findIndex(s => s.key === wizardStep) > idx;
        return (
          <button
            key={step.key}
            onClick={() => setWizardStep(step.key)}
            className={`flex items-center gap-1 px-3 py-1.5 rounded text-sm transition-colors ${
              isActive 
                ? 'bg-blue-500 text-white' 
                : isPast 
                  ? 'bg-green-100 text-green-700 hover:bg-green-200' 
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
            }`}
          >
            <span>{step.icon}</span>
            <span>{step.label}</span>
          </button>
        );
      })}
    </div>
  );
};
