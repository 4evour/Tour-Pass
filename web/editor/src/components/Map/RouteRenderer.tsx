import React from 'react';
import { Polyline } from 'react-leaflet';
import type { RouteSegment, DayPlan } from '../../types';

interface RouteRendererProps {
  routes: RouteSegment[];
  days: DayPlan[];
  currentDay: number;
  isDayMode: boolean;
}

const DAY_COLORS = ['#146b5d', '#c25b1e', '#2563eb', '#9333ea', '#dc2626', '#0d9488', '#d97706'];

export const RouteRenderer: React.FC<RouteRendererProps> = ({
  routes,
  days,
  currentDay,
  isDayMode,
}) => {
  return (
    <>
      {routes.map((route, index) => {
        const color = DAY_COLORS[index % DAY_COLORS.length];
        const weight = 3;
        const opacity = 0.7;
        
        return (
          <Polyline
            key={index}
            positions={route.coords}
            pathOptions={{
              color,
              weight,
              opacity,
            }}
          />
        );
      })}
    </>
  );
};
