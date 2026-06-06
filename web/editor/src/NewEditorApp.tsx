import React from 'react';
import { useItineraryStore } from './stores/itineraryStore';
import { WizardNav, DaysStep, CitiesStep, SegmentsStep, HotelsStep, PlanStep, ReviewStep } from './components/Wizard';

export default function NewEditorApp() {
  const wizardStep = useItineraryStore(state => state.wizardStep);
  const cities = useItineraryStore(state => state.cities);

  const renderStep = () => {
    switch (wizardStep) {
      case 'days':
        return <DaysStep />;
      case 'cities':
        return <CitiesStep />;
      case 'segments':
        return cities.length > 1 ? <SegmentsStep /> : <HotelsStep />;
      case 'hotels':
        return <HotelsStep />;
      case 'plan':
        return <PlanStep />;
      case 'review':
        return <ReviewStep />;
      default:
        return <DaysStep />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <a href="/" className="text-gray-500 hover:text-gray-700 text-sm">
            ← 返回首页
          </a>
          <h1 className="text-lg font-bold">Tour Pass 行程编辑器</h1>
        </div>
      </header>
      
      {/* Wizard navigation */}
      <WizardNav />
      
      {/* Step content */}
      <main>
        {renderStep()}
      </main>
    </div>
  );
}
