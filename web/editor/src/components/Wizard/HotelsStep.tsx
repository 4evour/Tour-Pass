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
    <div className="flex flex-col h-[calc(100vh-80px)]">
      {/* Header */}
      <div className="px-6 py-3 bg-white border-b">
        <h2 className="text-xl font-bold">选择酒店</h2>
        <p className="text-gray-500 text-sm">为每个城市选择住宿酒店</p>
      </div>

      {/* City tabs */}
      {cities.length > 1 && (
        <div className="flex gap-2 px-6 py-2 bg-gray-50 border-b overflow-x-auto">
          {cities.map((city, idx) => (
            <button
              key={city}
              onClick={() => setCurrentCityIdx(idx)}
              className={`px-3 py-1.5 rounded text-sm flex items-center gap-1.5 whitespace-nowrap ${
                idx === currentCityIdx
                  ? 'bg-blue-500 text-white'
                  : hotelsByCity[city]
                    ? 'bg-green-100 text-green-700'
                    : 'bg-white text-gray-500 border'
              }`}
            >
              {city}
              {hotelsByCity[city] && <span>✓</span>}
            </button>
          ))}
        </div>
      )}

      {/* Main: Map + Hotel list overlay */}
      <div className="flex-1 relative overflow-hidden">
        {/* Full-width map */}
        <div className="absolute inset-0">
          {sortedHotels.some(h => h.lat && h.lng) ? (
            <MapContainer
              center={(() => {
                const first = sortedHotels.find(h => h.lat && h.lng);
                return first ? [first.lat, first.lng] : [30.57, 114.27];
              })()}
              zoom={13}
              className="w-full h-full"
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
            <div className="w-full h-full flex items-center justify-center bg-gray-100">
              <div className="text-center text-gray-400">
                <p className="text-4xl mb-2">🗺</p>
                <p>无酒店坐标数据</p>
              </div>
            </div>
          )}
        </div>

        {/* Hotel list overlay - left side */}
        <div className="absolute left-4 top-4 bottom-4 w-80 bg-white rounded-xl shadow-lg border flex flex-col z-[1000]">
          {/* Search */}
          <div className="p-3 border-b">
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="搜索酒店..."
              className="w-full px-3 py-2 border rounded-lg text-sm"
            />
          </div>

          {/* Selected hotel */}
          {currentHotel && (
            <div className="px-3 py-2 bg-green-50 border-b">
              <p className="text-xs text-green-600">✅ 已选</p>
              <p className="text-sm font-medium text-green-800 truncate">{currentHotel.name}</p>
            </div>
          )}

          {/* Hotel list */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="text-center py-8 text-gray-400 text-sm">加载中...</div>
            ) : sortedHotels.length === 0 ? (
              <div className="text-center py-8 text-gray-400 text-sm">暂无酒店数据</div>
            ) : (
              sortedHotels.map((hotel, idx) => {
                const isSelected = currentHotel?.id === hotel.id;
                const isRecommended = idx < 3;
                return (
                  <button
                    key={hotel.id}
                    onClick={() => setHotelForCity(currentCity, hotel)}
                    className={`w-full text-left px-3 py-2.5 border-b transition-colors ${
                      isSelected
                        ? 'bg-blue-50 border-l-4 border-l-blue-500'
                        : 'hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-medium truncate">{hotel.name}</span>
                          {isRecommended && (
                            <span className="px-1.5 py-0.5 bg-yellow-100 text-yellow-700 text-[10px] rounded flex-shrink-0">推荐</span>
                          )}
                        </div>
                        <div className="text-xs text-gray-400 mt-0.5">
                          {hotel.area && hotel.area + ' · '}⭐ {(hotel.popularity || 0).toFixed(1)}
                        </div>
                      </div>
                      {isSelected && <span className="text-blue-500 text-lg flex-shrink-0">✓</span>}
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Stats */}
          <div className="px-3 py-2 bg-gray-50 border-t text-xs text-gray-400">
            共 {sortedHotels.length} 家酒店 {currentCity && '(· ' + currentCity + ')'}
          </div>
        </div>
      </div>

      {/* Bottom nav */}
      <div className="flex gap-3 px-6 py-3 bg-white border-t">
        <button
          onClick={() => setWizardStep(cities.length > 1 ? 'segments' : 'cities')}
          className="px-5 py-2.5 bg-gray-200 rounded-lg hover:bg-gray-300 text-sm"
        >
          ← 上一步
        </button>
        <div className="flex-1" />
        <button
          onClick={() => setWizardStep('plan')}
          disabled={!allCitiesHaveHotels}
          className="px-5 py-2.5 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm"
        >
          下一步：行程编排 →
        </button>
      </div>
    </div>
  );
};