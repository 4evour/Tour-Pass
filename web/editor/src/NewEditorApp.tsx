import React from 'react';
import AiChat from './components/AiChat';
import { useEffect, useRef, useState } from 'react';
import { useItineraryStore } from './stores/itineraryStore';
import { WizardNav, DaysStep, CitiesStep, SegmentsStep, HotelsStep, PlanStep, ReviewStep } from './components/Wizard';
import { api } from './utils/api';
import { deserializeTrip, serializeForSave } from './utils/serialize';

export default function NewEditorApp() {
  const wizardStep = useItineraryStore(state => state.wizardStep);
  const cities = useItineraryStore(state => state.cities);
  const setCity = useItineraryStore(state => state.setCity);
  const setCities = useItineraryStore(state => state.setCities);
  const setDays = useItineraryStore(state => state.setDays);
  const setTotalDays = useItineraryStore(state => state.setTotalDays);
  const setWizardStep = useItineraryStore(state => state.setWizardStep);
  const days = useItineraryStore(state => state.days);
  const importedTripRef = useRef<string | null>(null);
  const [loadedTripId, setLoadedTripId] = useState<string | null>(null);
  const [loadedTripTitle, setLoadedTripTitle] = useState('');
  const [loadingTrip, setLoadingTrip] = useState(false);
  const [tripLoaded, setTripLoaded] = useState(false);
  const [savingTrip, setSavingTrip] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tripId = params.get('tripId');
    if (!tripId || importedTripRef.current === tripId) return;
    importedTripRef.current = tripId;
    setLoadedTripId(tripId);
    setLoadingTrip(true);
    setTripLoaded(false);
    setSaveMessage('');

    api(`/trips/${tripId}`)
      .then((trip: any) => {
        const respData = typeof trip.response_json === 'string'
          ? JSON.parse(trip.response_json)
          : trip.response_json;
        const requestData = typeof trip.request_json === 'string'
          ? JSON.parse(trip.request_json)
          : trip.request_json;
        const result = deserializeTrip(respData, []);
        if (!result || result.days.length === 0) {
          throw new Error('行程数据为空或格式不兼容');
        }
        const tripCity = result.city || requestData?.city || '';
        if (tripCity) {
          setCity(tripCity);
          setCities([tripCity]);
        }
        setDays(result.days);
        setTotalDays(result.days.length);
        setLoadedTripTitle(trip.title || `${tripCity || '旅行'} ${result.days.length}日游`);
        setTripLoaded(true);
        setWizardStep('plan');
      })
      .catch((error) => {
        console.error('Failed to import saved trip from URL:', error);
        setTripLoaded(false);
        setSaveMessage(`载入失败：${error.message}`);
      })
      .finally(() => {
        setLoadingTrip(false);
      });
  }, [setCity, setCities, setDays, setTotalDays, setWizardStep]);

  const handleSaveLoadedTrip = async () => {
    if (!loadedTripId || !tripLoaded || loadingTrip) return;
    setSavingTrip(true);
    setSaveMessage('');
    try {
      const { title, request, response } = serializeForSave(cities[0] || '', days);
      await api(`/trips/${loadedTripId}`, {
        method: 'PUT',
        body: {
          title: loadedTripTitle || title,
          request,
          response,
        },
      });
      setSaveMessage('已保存修改');
    } catch (error: any) {
      setSaveMessage(`保存失败：${error.message}`);
    } finally {
      setSavingTrip(false);
    }
  };

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
        <div className="flex items-center gap-3 min-w-0">
          <h1 className="text-lg font-bold">Tour Pass 行程编辑器</h1>
          {loadedTripId && (
            <span className="text-xs text-gray-500 truncate">
              {loadingTrip ? '正在载入行程...' : `正在编辑：${loadedTripTitle || '已保存行程'}`}
            </span>
          )}
        </div>
        {loadedTripId && (
          <div className="flex items-center gap-3">
            {saveMessage && <span className="text-xs text-gray-500">{saveMessage}</span>}
            <button
              type="button"
              onClick={handleSaveLoadedTrip}
              disabled={!tripLoaded || loadingTrip || savingTrip}
              className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {savingTrip ? '保存中...' : '保存修改'}
            </button>
          </div>
        )}
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
