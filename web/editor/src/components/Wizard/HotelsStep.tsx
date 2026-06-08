import React, { useState, useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useItineraryStore } from '../../stores/itineraryStore';
import type { Poi } from '../../types';

/** Hotel map marker with visible name label */
function makeHotelIcon(selected: boolean, name?: string) {
  const bg = selected ? '#2563eb' : '#22c55e';
  const scale = selected ? 'transform:scale(1.25);z-index:1000;' : '';
  const shortName = name ? (name.length > 10 ? name.substring(0, 10) + '..' : name) : '';
  const labelHtml = shortName
    ? `<div style="background:#1a1a2e;color:#ffe066;font-size:11px;font-weight:600;padding:2px 6px;border-radius:4px;margin-top:3px;white-space:nowrap;max-width:120px;overflow:hidden;text-overflow:ellipsis;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.4);letter-spacing:0.3px;">${shortName}</div>`
    : '';
  return L.divIcon({
    className: 'hotel-marker',
    html: `<div style="display:flex;flex-direction:column;align-items:center;cursor:pointer;">` +
      `<div style="background:${bg};color:#fff;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:15px;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35);${scale}">🏨</div>` +
      `${labelHtml}</div>`,
    iconSize: [90, 44],
    iconAnchor: [14, 14],
    popupAnchor: [0, -18],
  });
}

/** Auto-fit map to show all hotels or selected hotel */
function HotelMapFitBounds({ hotels, selected }: { hotels: Poi[]; selected?: Poi | null }) {
  const map = useMap();
  useEffect(() => {
    const target = selected && selected.lat && selected.lng ? [selected] : hotels.filter(h => h.lat && h.lng);
    if (target.length === 0) return;
    if (target.length === 1) {
      map.setView([target[0].lat, target[0].lng], 14, { animate: true });
    } else {
      const bounds = L.latLngBounds(target.map(p => [p.lat, p.lng] as [number, number]));
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15, animate: true });
    }
  }, [hotels, selected, map]);
  return null;
}

export const HotelsStep: React.FC = () => {
  const { cities, hotelsByCity, setHotelForCity, setWizardStep } = useItineraryStore();
  const [currentCityIdx, setCurrentCityIdx] = useState(0);
  const [hotels, setHotels] = useState<Poi[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');

  const currentCity = cities[currentCityIdx];
  const currentHotel = currentCity ? hotelsByCity[currentCity] : null;

  // Fetch hotels for the current city
  useEffect(() => {
    if (!currentCity) return;
    setLoading(true);
    setError('');
    setHotels([]);
    fetch(`/poi/search?type=hotel&city=${encodeURIComponent(currentCity)}&limit=100`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        const list: Poi[] = (data.data || []).filter((h: Poi) => h.lat && h.lng);
        setHotels(list);
        setLoading(false);
      })
      .catch(err => {
        setError('加载酒店失败: ' + err.message);
        setLoading(false);
      });
  }, [currentCity]);

  const filteredHotels = useMemo(() => {
    let list = hotels;
    if (filter) {
      const q = filter.toLowerCase();
      list = list.filter(h =>
        h.name.toLowerCase().includes(q) ||
        (h.area || '').toLowerCase().includes(q)
      );
    }
    return [...list].sort((a, b) => (b.popularity || 0) - (a.popularity || 0));
  }, [hotels, filter]);

  const selectHotel = (hotel: Poi) => {
    if (currentCity) setHotelForCity(currentCity, hotel);
  };

  const allCitiesHaveHotels = cities.every(c => hotelsByCity[c]);

  return (
    <div className="flex flex-col h-[calc(100vh-80px)]">
      {/* Header */}
      <div className="px-6 py-3 bg-white border-b flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">🏨 选择酒店</h2>
          <p className="text-gray-500 text-sm">为每个城市选择住宿酒店 · 点击地图标记或列表选择</p>
        </div>
        <div className="text-sm text-gray-400">
          {hotels.length > 0 && `${filteredHotels.length} 家酒店`}
        </div>
      </div>

      {/* City tabs */}
      {cities.length > 1 && (
        <div className="flex gap-2 px-6 py-2 bg-gray-50 border-b overflow-x-auto">
          {cities.map((city, idx) => (
            <button
              key={city}
              onClick={() => setCurrentCityIdx(idx)}
              className={`px-3 py-1.5 rounded text-sm flex items-center gap-1.5 whitespace-nowrap transition-colors ${
                idx === currentCityIdx
                  ? 'bg-blue-500 text-white shadow-sm'
                  : hotelsByCity[city]
                    ? 'bg-green-100 text-green-700'
                    : 'bg-white text-gray-500 border hover:bg-gray-50'
              }`}
            >
              {city}
              {hotelsByCity[city] && <span>✓</span>}
            </button>
          ))}
        </div>
      )}

      {/* Main: full-width map with floating hotel list panel */}
      <div className="flex-1 relative overflow-hidden">
        {/* Map background */}
        <div className="absolute inset-0">
          {filteredHotels.some(h => h.lat && h.lng) ? (
            <MapContainer
              center={(() => {
                const first = filteredHotels.find(h => h.lat && h.lng);
                return first ? [first.lat, first.lng] : [35, 105];
              })()}
              zoom={13}
              className="w-full h-full"
              zoomControl={true}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.amap.com/">高德地图</a>'
                url="https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
              />
              <HotelMapFitBounds hotels={filteredHotels} selected={currentHotel} />
              {filteredHotels.filter(h => h.lat && h.lng).map(hotel => (
                <Marker
                  key={hotel.id}
                  position={[hotel.lat, hotel.lng]}
                  icon={makeHotelIcon(currentHotel?.id === hotel.id, hotel.name)}
                  eventHandlers={{
                    click: () => selectHotel(hotel),
                  }}
                >
                  <Popup>
                    <div style={{ minWidth: 180 }}>
                      <b>🏨 {hotel.name}</b><br />
                      <span style={{ fontSize: 11 }}>{hotel.area}</span><br />
                      <span style={{ fontSize: 11, color: '#65706d' }}>热度 {(hotel.popularity || 0).toFixed(1)}</span><br />
                      <button
                        onClick={(e) => { e.stopPropagation(); selectHotel(hotel); }}
                        style={{
                          marginTop: 6, padding: '6px 14px', border: 'none', borderRadius: 6,
                          background: currentHotel?.id === hotel.id ? '#2563eb' : '#22c55e',
                          color: '#fff', fontSize: 12, cursor: 'pointer', width: '100%',
                          fontWeight: 600,
                        }}
                      >
                        {currentHotel?.id === hotel.id ? '✅ 已选择' : '👆 点击选择此酒店'}
                      </button>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          ) : loading ? (
            <div className="w-full h-full flex items-center justify-center bg-gray-100">
              <div className="text-center text-gray-400">
                <div className="animate-spin w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full mx-auto mb-2"></div>
                <p>正在加载 {currentCity} 的酒店...</p>
              </div>
            </div>
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-gray-100">
              <div className="text-center text-gray-400">
                <p className="text-4xl mb-2">🏨</p>
                <p>{error || '暂无酒店坐标数据'}</p>
              </div>
            </div>
          )}
        </div>

        {/* Floating hotel list panel (left) */}
        <div className="absolute left-4 top-4 bottom-4 w-80 bg-white/95 backdrop-blur-sm rounded-xl shadow-2xl border flex flex-col z-[1000]">
          {/* Search */}
          <div className="p-3 border-b">
            <input
              type="text"
              value={filter}
              onChange={e => setFilter(e.target.value)}
              placeholder="🔍 搜索酒店名称或区域..."
              className="w-full px-3 py-2 border rounded-lg text-sm bg-gray-50 focus:bg-white focus:border-blue-300 outline-none"
            />
          </div>

          {/* Selected hotel indicator */}
          {currentHotel && (
            <div className="px-3 py-2 bg-blue-50 border-b flex items-center gap-2">
              <span className="text-blue-600 text-lg">✅</span>
              <div className="min-w-0 flex-1">
                <p className="text-xs text-blue-500">已选酒店</p>
                <p className="text-sm font-medium text-blue-800 truncate">{currentHotel.name}</p>
              </div>
            </div>
          )}

          {/* Hotel list */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="text-center py-8 text-gray-400 text-sm">
                <div className="animate-pulse">加载中...</div>
              </div>
            ) : error ? (
              <div className="text-center py-8 text-red-400 text-sm px-4">{error}</div>
            ) : filteredHotels.length === 0 ? (
              <div className="text-center py-8 text-gray-400 text-sm">暂无酒店数据</div>
            ) : (
              filteredHotels.map((hotel, idx) => {
                const isSelected = currentHotel?.id === hotel.id;
                const isRecommended = idx < 3;
                return (
                  <button
                    key={hotel.id}
                    onClick={() => selectHotel(hotel)}
                    className={`w-full text-left px-3 py-2.5 border-b transition-all ${
                      isSelected
                        ? 'bg-blue-50 border-l-4 border-l-blue-500'
                        : 'hover:bg-gray-50 border-l-4 border-l-transparent'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-medium truncate">{hotel.name}</span>
                          {isRecommended && (
                            <span className="px-1.5 py-0.5 bg-yellow-100 text-yellow-700 text-[10px] rounded flex-shrink-0 font-medium">推荐</span>
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

          {/* Stats footer */}
          <div className="px-3 py-2 bg-gray-50 border-t text-xs text-gray-400 flex justify-between">
            <span>📍 {currentCity}</span>
            <span>{filteredHotels.length} 家酒店</span>
          </div>
        </div>
      </div>

      {/* Bottom navigation */}
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
