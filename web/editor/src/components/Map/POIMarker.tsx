import React from 'react';
import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import type { Stop } from '../../types';

interface POIMarkerProps {
  stop: Stop;
  index: number;
  dayIndex: number;
  isCurrentDay: boolean;
  color: string;
}

export const POIMarker: React.FC<POIMarkerProps> = ({
  stop,
  index,
  dayIndex,
  isCurrentDay,
  color,
}) => {
  const icon = createPOIIcon(index, stop.poi.name, color, isCurrentDay);
  
  return (
    <Marker
      position={[stop.poi.lat, stop.poi.lng]}
      icon={icon}
    >
      <Popup>
        <div className="p-2">
          <h3 className="font-bold text-lg">{stop.poi.name}</h3>
          <p className="text-gray-600">{stop.poi.area}</p>
          {stop.poi.description && (
            <p className="text-sm mt-2">{stop.poi.description}</p>
          )}
          <div className="mt-2 text-sm">
            <p>第{dayIndex + 1}天 · 第{index + 1}站</p>
            {stop.arrival > 0 && (
              <p>到达时间：{formatTime(stop.arrival)}</p>
            )}
            <p>游览时长：{stop.poi.visit_duration || 60}分钟</p>
          </div>
        </div>
      </Popup>
    </Marker>
  );
};

function createPOIIcon(
  index: number,
  name: string,
  color: string,
  isCurrentDay: boolean
): L.DivIcon {
  const displayName = name.length > 8 ? name.substring(0, 8) + '..' : name;
  
  if (isCurrentDay) {
    return L.divIcon({
      className: 'poi-marker-current',
      html: `
        <div style="display:flex;flex-direction:column;align-items:center;pointer-events:auto;">
          <div style="
            background:${color};
            color:#fff;
            width:32px;
            height:32px;
            border-radius:50%;
            display:flex;
            align-items:center;
            justify-content:center;
            font-size:14px;
            font-weight:700;
            border:3px solid #fff;
            box-shadow:0 2px 8px rgba(0,0,0,0.4);
            z-index:10;
          ">${index + 1}</div>
          <div style="
            background:rgba(255,255,255,0.95);
            color:#17211f;
            font-size:11px;
            padding:2px 6px;
            border-radius:4px;
            margin-top:4px;
            white-space:nowrap;
            box-shadow:0 1px 3px rgba(0,0,0,0.2);
            font-weight:600;
            max-width:100px;
            overflow:hidden;
            text-overflow:ellipsis;
          ">${displayName}</div>
        </div>
      `,
      iconSize: [80, 50],
      iconAnchor: [16, 35],
      popupAnchor: [0, -35],
    });
  }
  
  return L.divIcon({
    className: 'poi-marker-other',
    html: `
      <div style="
        background:${color};
        color:#fff;
        width:24px;
        height:24px;
        border-radius:50%;
        display:flex;
        align-items:center;
        justify-content:center;
        font-size:11px;
        font-weight:600;
        border:2px solid #fff;
        opacity:0.6;
        box-shadow:0 1px 3px rgba(0,0,0,0.2);
      ">${index + 1}</div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -14],
  });
}

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}
