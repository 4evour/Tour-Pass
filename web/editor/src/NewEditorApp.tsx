import React from 'react';
import AiChat from './components/AiChat';
import { useEffect, useRef } from 'react';
import { useItineraryStore } from './stores/itineraryStore';
import { WizardNav, DaysStep, CitiesStep, SegmentsStep, HotelsStep, PlanStep, ReviewStep } from './components/Wizard';
import { api } from './utils/api';
import { deserializeTrip } from './utils/serialize';

export default function NewEditorApp() {
  const wizardStep = useItineraryStore(state => state.wizardStep);
  const cities = useItineraryStore(state => state.cities);
  const setCity = useItineraryStore(state => state.setCity);
  const setCities = useItineraryStore(state => state.setCities);
  const setDays = useItineraryStore(state => state.setDays);
  const setTotalDays = useItineraryStore(state => state.setTotalDays);
  const setWizardStep = useItineraryStore(state => state.setWizardStep);
  const importedTripRef = useRef<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tripId = params.get('tripId');
    if (!tripId || importedTripRef.current === tripId) return;
    importedTripRef.current = tripId;

    api(`/trips/${tripId}`)
      .then((trip: any) => {
        const respData = typeof trip.response_json === 'string'
          ? JSON.parse(trip.response_json)
          : trip.response_json;
        const result = deserializeTrip(respData, []);
        if (!result || result.days.length === 0) return;
        if (result.city) {
          setCity(result.city);
          setCities([result.city]);
        }
        setDays(result.days);
        setTotalDays(result.days.length);
        setWizardStep('plan');
      })
      .catch((error) => {
        console.error('Failed to import saved trip from URL:', error);
      });
  }, [setCity, setCities, setDays, setTotalDays, setWizardStep]);

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

      {/* AI Chat floating panel */}
      <AiChat city={cities[0] || ''} />
    </div>
  );
}
