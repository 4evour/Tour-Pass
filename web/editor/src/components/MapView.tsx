import { useEffect, useMemo, useCallback, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import type { Poi } from '../types';
import { useItineraryStore } from '../stores/itineraryStore';

const DAY_COLORS = ['#146b5d', '#c25b1e', '#2563eb', '#9333ea', '#dc2626', '#0d9488', '#d97706'];

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

// Emoji icon for POI type
function makeIcon(type: string) {
  const color = TYPE_COLORS[type] || '#6b7280';
  const icon = TYPE_ICONS[type] || '📍';
  return L.divIcon({
    className: 'custom-marker',
    html: `<div style="background:${color};color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.3);cursor:pointer;">${icon}</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -14],
  });
}

// Numbered marker for current day (prominent, with name label)
function makeCurrentDayIcon(num: number, color: string, name: string) {
  const displayName = name.length > 6 ? name.substring(0, 6) + '..' : name;
  return L.divIcon({
    className: 'current-day-marker',
    html: `<div style="display:flex;flex-direction:column;align-items:center;pointer-events:auto;">
      <div style="background:${color};color:#fff;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.4);z-index:10;">${num}</div>
      <div style="background:rgba(255,255,255,0.95);color:#17211f;font-size:10px;padding:1px 4px;border-radius:3px;margin-top:2px;white-space:nowrap;box-shadow:0 1px 2px rgba(0,0,0,.15);font-weight:500;">${displayName}</div>
    </div>`,
    iconSize: [60, 44],
    iconAnchor: [14, 28],
    popupAnchor: [0, -30],
  });
}

// Small translucent marker for other days
function makeOtherDayIcon(num: number, color: string) {
  return L.divIcon({
    className: 'other-day-marker',
    html: `<div style="background:${color};color:#fff;width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;border:1.5px solid #fff;opacity:0.5;box-shadow:0 1px 3px rgba(0,0,0,.2);">${num}</div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -12],
  });
}

function FitBounds({ pois, day }: { pois: Poi[]; day: number }) {
  const map = useMap();
  const prevDay = useRef(day);
  const initialized = useRef(false);

  useEffect(() => {
    const dayChanged = day !== prevDay.current;
    prevDay.current = day;

    // Fit on: initial load, or when day changes
    // Do NOT fit on stop reorder within the same day
    if (!initialized.current || dayChanged) {
      initialized.current = true;
      if (pois.length > 0) {
        const bounds = L.latLngBounds(pois.map(p => [p.lat, p.lng] as [number, number]));
        map.fitBounds(bounds, { padding: [40, 40] });
      }
    }
  }, [day]); // Only depend on day, not on pois

  return null;
}

interface MapViewProps {
  allPois: Poi[];
  onAddPoi: (poi: Poi) => void;
  currentDay: number;
  onDayChange: (day: number) => void;
}

export default function MapView({ allPois, onAddPoi, currentDay, onDayChange }: MapViewProps) {
  const defaultHotel = useItineraryStore(s => s.defaultHotel);
  const days = useItineraryStore(s => s.days);
  const routes = useItineraryStore(s => s.routes);
  const getEffectiveHotel = useItineraryStore(s => s.getEffectiveHotel);

  const allStops = useMemo(() => days.flatMap(d => d.stops), [days]);
  const stopIds = useMemo(() => new Set(allStops.map(s => s.poi.id)), [allStops]);

  const currentDayPlan = days.find(d => d.day === currentDay);
  const currentStops = currentDayPlan?.stops || [];

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

  // Per-day route coordinates (only current day highlighted)
  const currentDayRoutes = useMemo(() => {
    if (currentStops.length < 2) return [];
    const currentStopIds = new Set(currentStops.map(s => s.poi.id));
    const segments: [number, number][][] = [];
    let currentSegment: [number, number][] = [];

    for (const route of routes) {
      if (currentStopIds.has(route.from) || currentStopIds.has(route.to)) {
        if (route.coords.length > 0) {
          currentSegment.push(...route.coords);
        }
      }
    }
    if (currentSegment.length > 1) segments.push(currentSegment);
    return segments;
  }, [routes, currentStops]);

  // FitBounds to current day's stops + hotel
  const boundsPois = useMemo(() => {
    const pois: Poi[] = [];
    const hotel = getEffectiveHotel(currentDay);
    if (hotel) pois.push(hotel);
    for (const s of currentStops) pois.push(s.poi);
    return pois.length > 0 ? pois : allPois.slice(0, 5);
  }, [currentDay, currentStops, getEffectiveHotel, allPois]);

  const handleMarkerClick = useCallback((day: number) => {
    if (day !== currentDay) onDayChange(day);
  }, [currentDay, onDayChange]);

  const defaultCenter: [number, number] = allPois.length > 0
    ? [allPois[0].lat, allPois[0].lng]
    : [30.57, 114.27];

  return (
    <MapContainer center={defaultCenter} zoom={13} className="w-full h-full" zoomControl={false}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds pois={boundsPois} day={currentDay} />

      {/* Hotel markers */}
      {hotelMarkers.map(({ poi, days: hotelDays }) => (
        <Marker key={`hotel-${poi.id}`} position={[poi.lat, poi.lng]} icon={makeIcon('hotel')}>
          <Popup>
            <b>🏨 {poi.name}</b><br />
            <span style={{ fontSize: 11 }}>{poi.area}</span><br />
            <span style={{ fontSize: 11, color: '#65706d' }}>Day {hotelDays.join(', ')} 住宿</span>
          </Popup>
        </Marker>
      ))}

      {/* All POI markers (non-itinerary, non-hotel) */}
      {allPois.filter(p => !stopIds.has(p.id) && p.type !== 'hotel').map(poi => (
        <Marker key={poi.id} position={[poi.lat, poi.lng]} icon={makeIcon(poi.type)}>
          <Popup>
            <div style={{ minWidth: 160 }}>
              <b>{TYPE_ICONS[poi.type]} {poi.name}</b><br />
              <span style={{ fontSize: 11, color: '#65706d' }}>{poi.area}</span><br />
              <button
                onClick={() => onAddPoi(poi)}
                style={{ marginTop: 6, padding: '4px 10px', border: '1px solid #146b5d', borderRadius: 4, background: '#146b5d', color: '#fff', fontSize: 11, cursor: 'pointer' }}
              >
                + 添加到 Day {currentDay}
              </button>
            </div>
          </Popup>
        </Marker>
      ))}

      {/* Other days' stops (small, translucent, clickable to switch day) */}
      {days.filter(d => d.day !== currentDay).map(d => {
        const color = DAY_COLORS[(d.day - 1) % DAY_COLORS.length];
        return d.stops.map((stop, i) => (
          <Marker
            key={stop.id}
            position={[stop.poi.lat, stop.poi.lng]}
            icon={makeOtherDayIcon(i + 1, color)}
            eventHandlers={{ click: () => handleMarkerClick(d.day) }}
          >
            <Popup>
              <b style={{ color }}>Day {d.day} · {i + 1}. {stop.poi.name}</b><br />
              <span style={{ fontSize: 11 }}>{formatMin(stop.arrival)} - {formatMin(stop.departure)}</span><br />
              <button
                onClick={() => handleMarkerClick(d.day)}
                style={{ marginTop: 4, padding: '2px 8px', border: `1px solid ${color}`, borderRadius: 3, background: color, color: '#fff', fontSize: 10, cursor: 'pointer' }}
              >
                切换到 Day {d.day}
              </button>
            </Popup>
          </Marker>
        ));
      })}

      {/* Current day's stops (prominent, with name labels) */}
      {currentStops.map((stop, i) => {
        const color = DAY_COLORS[(currentDay - 1) % DAY_COLORS.length];
        return (
          <Marker
            key={`cur-${stop.id}`}
            position={[stop.poi.lat, stop.poi.lng]}
            icon={makeCurrentDayIcon(i + 1, color, stop.poi.name)}
          >
            <Popup>
              <b style={{ color }}>Day {currentDay} · {i + 1}. {stop.poi.name}</b><br />
              <span style={{ fontSize: 11 }}>{formatMin(stop.arrival)} - {formatMin(stop.departure)}</span><br />
              <span style={{ fontSize: 11, color: '#65706d' }}>{stop.poi.area}</span>
            </Popup>
          </Marker>
        );
      })}

      {/* Current day route (highlighted) */}
      {currentDayRoutes.map((coords, i) => (
        <Polyline
          key={`route-cur-${i}`}
          positions={coords}
          color={DAY_COLORS[(currentDay - 1) % DAY_COLORS.length]}
          weight={4}
          opacity={0.8}
        />
      ))}

      {/* Fallback: straight lines between current day's stops */}
      {currentDayRoutes.length === 0 && currentStops.length > 1 && (
        <Polyline
          positions={currentStops.map(s => [s.poi.lat, s.poi.lng] as [number, number])}
          color={DAY_COLORS[(currentDay - 1) % DAY_COLORS.length]}
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
