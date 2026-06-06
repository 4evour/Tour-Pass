import React, { useState, useEffect } from 'react';
import { useItineraryStore } from '../../stores/itineraryStore';
import type { Poi } from '../../types';

export const HotelsStep: React.FC = () => {
  const { cities, hotelsByCity, setHotelForCity, setWizardStep } = useItineraryStore();
  const [currentCityIdx, setCurrentCityIdx] = useState(0);
  const [hotels, setHotels] = useState<Poi[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('');
  
  const currentCity = cities[currentCityIdx];
  const currentHotel = hotelsByCity[currentCity];

  useEffect(() => {
    if (!currentCity) return;
    setLoading(true);
    fetch(`/poi/search?type=hotel&city=${encodeURIComponent(currentCity)}&limit=100`)
      .then(r => r.json())
      .then(data => {
        setHotels(data.data || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [currentCity]);

  const filteredHotels = hotels.filter(h => 
    !filter || h.name.toLowerCase().includes(filter.toLowerCase()) || 
    (h.area || '').toLowerCase().includes(filter.toLowerCase())
  );

  // Sort by popularity (recommendation)
  const sortedHotels = [...filteredHotels].sort((a, b) => (b.popularity || 0) - (a.popularity || 0));

  const allCitiesHaveHotels = cities.every(c => hotelsByCity[c]);

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold mb-2">选择酒店</h2>
      <p className="text-gray-500 mb-4">为每个城市选择住宿酒店</p>
      
      {/* City tabs */}
      {cities.length > 1 && (
        <div className="flex gap-2 mb-4">
          {cities.map((city, idx) => (
            <button
              key={city}
              onClick={() => setCurrentCityIdx(idx)}
              className={`px-4 py-2 rounded-lg text-sm flex items-center gap-2 ${
                idx === currentCityIdx
                  ? 'bg-blue-500 text-white'
                  : hotelsByCity[city]
                    ? 'bg-green-100 text-green-700'
                    : 'bg-gray-100 text-gray-500'
              }`}
            >
              {city}
              {hotelsByCity[city] && <span>✓</span>}
            </button>
          ))}
        </div>
      )}
      
      <div className="flex gap-4">
        {/* Hotel list */}
        <div className="flex-1">
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="搜索酒店..."
            className="w-full px-3 py-2 border rounded mb-3"
          />
          
          {currentHotel && (
            <div className="p-3 mb-3 bg-green-50 border border-green-200 rounded-lg">
              <p className="text-sm text-green-700">
                ✅ 已选：<strong>{currentHotel.name}</strong>
                {currentHotel.area && ` (${currentHotel.area})`}
                {currentHotel.popularity > 0 && ` · ⭐ ${currentHotel.popularity.toFixed(1)}`}
              </p>
            </div>
          )}
          
          {loading ? (
            <div className="text-center py-8 text-gray-400">加载中...</div>
          ) : (
            <div className="space-y-2 max-h-[50vh] overflow-y-auto">
              {sortedHotels.map((hotel, idx) => {
                const isSelected = currentHotel?.id === hotel.id;
                const isRecommended = idx < 3; // Top 3 are recommended
                return (
                  <button
                    key={hotel.id}
                    onClick={() => setHotelForCity(currentCity, hotel)}
                    className={`w-full text-left p-3 rounded-lg border transition-all ${
                      isSelected
                        ? 'border-blue-500 bg-blue-50 shadow-md'
                        : isRecommended
                          ? 'border-yellow-300 bg-yellow-50 hover:border-yellow-400'
                          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="font-medium">{hotel.name}</span>
                        {isRecommended && (
                          <span className="ml-2 px-1.5 py-0.5 bg-yellow-200 text-yellow-800 text-xs rounded">
                            推荐
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-gray-500">
                        {hotel.area && `${hotel.area} · `}
                        ⭐ {(hotel.popularity || 0).toFixed(1)}
                      </div>
                    </div>
                  </button>
                );
              })}
              {sortedHotels.length === 0 && !loading && (
                <div className="text-center py-8 text-gray-400">暂无酒店数据</div>
              )}
            </div>
          )}
        </div>
        
        {/* Map placeholder - will be enhanced with Leaflet */}
        <div className="w-80 bg-gray-100 rounded-lg flex items-center justify-center">
          <div className="text-center text-gray-400">
            <p className="text-lg mb-2">🗺️</p>
            <p className="text-sm">酒店地图</p>
            <p className="text-xs">推荐酒店将高亮显示</p>
          </div>
        </div>
      </div>
      
      <div className="flex gap-3 mt-6">
        <button
          onClick={() => setWizardStep(cities.length > 1 ? 'segments' : 'cities')}
          className="px-6 py-3 bg-gray-200 rounded-lg hover:bg-gray-300"
        >
          ← 上一步
        </button>
        <button
          onClick={() => setWizardStep('plan')}
          disabled={!allCitiesHaveHotels}
          className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          下一步：行程编排 →
        </button>
      </div>
    </div>
  );
};
