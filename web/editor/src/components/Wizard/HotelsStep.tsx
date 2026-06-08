import React, { useState, useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useItineraryStore } from '../../stores/itineraryStore';
import type { Poi } from '../../types';

function makeHotelIcon(selected: boolean, name?: string) {
  const bg = selected ? '#2563eb' : '#22c55e';
  const scale = selected ? 'transform:scale(1.2);' : '';
  const shortName = name ? (name.length > 8 ? name.substring(0, 8) + '..' : name) : '';
  const labelHtml = shortName
    ? `<div style="background:rgba(0,0,0,0.75);color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;margin-top:2px;white-space:nowrap;max-width:100px;overflow:hidden;text-overflow:ellipsis;text-align:center;">${shortName}</div>`
    : '';
  return L.divIcon({
    className: 'hotel-marker',
    html: `<div style="display:flex;flex-direction:column;align-items:center;"><div style="background:${bg};color:#fff;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.3);cursor:pointer;${scale}">🏨</div>${labelHtml}</div>`,
    iconSize: [80, 40],
    iconAnchor: [13, 13],
    popupAnchor: [0, -20],
  });
}
function HotelMapFitBounds({ hotels, selected }: { hotels: Poi[]; selected?: Poi | null }) {
  const map = useMap();
  useEffect(() => {
    const pois = selected ? [selected] : hotels;
    const valid = pois.filter(p => p.lat && p.lng);
    if (valid.length > 0) {
      if (valid.length === 1) {
        map.setView([valid[0].lat, valid[0].lng], 14);
      } else {
        const bounds = L.latLngBounds(valid.map(p => [p.lat, p.lng] as [number, number]));
        map.fitBounds(bounds, { padding: [40, 40] });
      }
    }
  }, [hotels, selected, map]);
  return null;
}

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
        
                {/* Hotel map */}
        <div className="w-[480px] rounded-lg overflow-hidden border border-gray-200" style={{ minHeight: 500 }}>
          {sortedHotels.some(h => h.lat && h.lng) ? (
            <MapContainer
              center={(() => {
                const first = sortedHotels.find(h => h.lat && h.lng);
                return first ? [first.lat, first.lng] as [number, number] : [30.57, 114.27];
              })()}
              zoom={13}
              className="w-full h-full"
              style={{ minHeight: 500 }}
              zoomControl={false}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.amap.com/">高德地图</a>'
                url="https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
              />
              <HotelMapFitBounds hotels={sortedHotels} selected={currentHotel} />
              {sortedHotels.filter(h => h.lat && h.lng).map(hotel => (
                <Marker
                  key={hotel.id}
                  position={[hotel.lat, hotel.lng]}
                  icon={makeHotelIcon(currentHotel?.id === hotel.id, hotel.name)}
                >
                  <Popup>
                    <b>🏨 {hotel.name}</b><br />
                    <span style={{ fontSize: 11 }}>{hotel.area}</span><br />
                    <span style={{ fontSize: 11, color: '#65706d' }}>热度 {(hotel.popularity || 0).toFixed(1)}</span>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          ) : (
            <div className="w-full h-[500px] flex items-center justify-center bg-gray-50">
              <div className="text-center text-gray-400">
                <p className="text-lg mb-2">🗺️</p>
                <p className="text-sm">无酒店坐标数据</p>
              </div>
            </div>
          )}
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
