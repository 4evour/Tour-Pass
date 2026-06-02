import { useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import type { Poi, Stop } from '../types';
import { useItineraryStore } from '../stores/itineraryStore';

const TYPE_COLORS: Record<string, string> = {
  attraction: '#3b82f6',
  restaurant: '#f97316',
  hotel: '#22c55e',
  nightlife: '#a855f7',
  transit: '#6b7280',
};

const TYPE_ICONS: Record<string, string> = {
  attraction: '🏛',
  restaurant: '🍜',
  hotel: '🏨',
  nightlife: '🌙',
  transit: '🚌',
};

function makeIcon(type: string, label: string) {
  const color = TYPE_COLORS[type] || '#6b7280';
  const icon = TYPE_ICONS[type] || '📍';
  return L.divIcon({
    className: 'custom-marker',
    html: `<div style="background:${color};color:#fff;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;border:2px solid #fff;box-shadow:0 2px 4px rgba(0,0,0,.3);cursor:pointer;">${icon}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -16],
  });
}

function makeNumberedIcon(num: number) {
  return L.divIcon({
    className: 'numbered-marker',
    html: `<div style="background:#146b5d;color:#fff;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.4);">${num}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -16],
  });
}

function FitBounds({ pois }: { pois: Poi[] }) {
  const map = useMap();
  useEffect(() => {
    if (pois.length > 0) {
      const bounds = L.latLngBounds(pois.map(p => [p.lat, p.lng] as [number, number]));
      map.fitBounds(bounds, { padding: [40, 40] });
    }
  }, [pois.length]);
  return null;
}

interface MapViewProps {
  allPois: Poi[];
  onAddPoi: (poi: Poi) => void;
}

export default function MapView({ allPois, onAddPoi }: MapViewProps) {
  const defaultHotel = useItineraryStore(s => s.defaultHotel);
  const days = useItineraryStore(s => s.days);
  const routes = useItineraryStore(s => s.routes);
  const getEffectiveHotel = useItineraryStore(s => s.getEffectiveHotel);

  const allStops = useMemo(() => days.flatMap(d => d.stops), [days]);
  const stopIds = useMemo(() => new Set(allStops.map(s => s.poi.id)), [allStops]);

  // Collect all unique hotels across days
  const hotelMarkers = useMemo(() => {
    const seen = new Set<string>();
    const markers: { poi: Poi; days: number[] }[] = [];
    for (const d of days) {
      const h = d.hotel ?? defaultHotel;
      if (h && !seen.has(h.id)) {
        seen.add(h.id);
        markers.push({ poi: h, days: [d.day] });
      } else if (h) {
        const existing = markers.find(m => m.poi.id === h.id);
        if (existing) existing.days.push(d.day);
      }
    }
    return markers;
  }, [days, defaultHotel]);

  const routeCoords = useMemo(() => {
    return routes.flatMap(r => r.coords.length > 0 ? r.coords : []);
  }, [routes]);

  const defaultCenter: [number, number] = allPois.length > 0
    ? [allPois[0].lat, allPois[0].lng]
    : [30.57, 114.27];

  return (
    <MapContainer center={defaultCenter} zoom={13} className="w-full h-full" zoomControl={false}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds pois={defaultHotel ? [defaultHotel, ...allPois.slice(0, 5)] : allPois.slice(0, 5)} />

      {/* Hotel markers (unique across all days) */}
      {hotelMarkers.map(({ poi, days: hotelDays }) => (
        <Marker key={`hotel-${poi.id}`} position={[poi.lat, poi.lng]} icon={makeIcon('hotel', '🏨')}>
          <Popup>
            <b>🏨 {poi.name}</b><br />
            <span style={{ fontSize: 11 }}>{poi.area}</span><br />
            <span style={{ fontSize: 11, color: '#65706d' }}>Day {hotelDays.join(', ')} 住宿</span>
          </Popup>
        </Marker>
      ))}

      {/* All POI markers (non-itinerary, non-hotel) */}
      {allPois.filter(p => !stopIds.has(p.id) && p.type !== 'hotel').map(poi => (
        <Marker key={poi.id} position={[poi.lat, poi.lng]} icon={makeIcon(poi.type, poi.name)}>
          <Popup>
            <div style={{ minWidth: 160 }}>
              <b>{TYPE_ICONS[poi.type]} {poi.name}</b><br />
              <span style={{ fontSize: 11, color: '#65706d' }}>{poi.area}</span><br />
              <button
                onClick={() => onAddPoi(poi)}
                style={{ marginTop: 6, padding: '4px 10px', border: '1px solid #146b5d', borderRadius: 4, background: '#146b5d', color: '#fff', fontSize: 11, cursor: 'pointer' }}
              >
                + 添加到行程
              </button>
            </div>
          </Popup>
        </Marker>
      ))}

      {/* Numbered itinerary markers */}
      {allStops.map((stop, i) => (
        <Marker key={stop.id} position={[stop.poi.lat, stop.poi.lng]} icon={makeNumberedIcon(i + 1)}>
          <Popup>
            <b>{i + 1}. {stop.poi.name}</b><br />
            <span style={{ fontSize: 11 }}>{formatMin(stop.arrival)} - {formatMin(stop.departure)}</span>
          </Popup>
        </Marker>
      ))}

      {/* Route polyline */}
      {routeCoords.length > 1 && (
        <Polyline positions={routeCoords} color="#146b5d" weight={3} opacity={0.7} dashArray="8 4" />
      )}

      {/* Simple connecting lines between stops if no route coords */}
      {routeCoords.length === 0 && allStops.length > 1 && (
        <Polyline
          positions={allStops.map(s => [s.poi.lat, s.poi.lng] as [number, number])}
          color="#146b5d"
          weight={3}
          opacity={0.7}
          dashArray="8 4"
        />
      )}
    </MapContainer>
  );
}

function formatMin(m: number): string {
  const h = Math.floor(m / 60);
  const min = m % 60;
  return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}
