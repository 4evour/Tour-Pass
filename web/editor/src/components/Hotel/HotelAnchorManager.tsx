import React, { useState } from 'react';
import { useItineraryStore } from '../../stores/itineraryStore';
import type { Poi } from '../../types';

interface HotelAnchorManagerProps {
  dayIndex: number;
  onHotelSelect: (hotel: Poi | null) => void;
}

export const HotelAnchorManager: React.FC<HotelAnchorManagerProps> = ({
  dayIndex,
  onHotelSelect,
}) => {
  const days = useItineraryStore(state => state.days);
  const defaultHotel = useItineraryStore(state => state.defaultHotel);
  const setDefaultHotel = useItineraryStore(state => state.setDefaultHotel);
  const setDayHotel = useItineraryStore(state => state.setDayHotel);
  
  const day = days[dayIndex];
  if (!day) return null;
  
  const effectiveHotel = day.hotel || defaultHotel;
  const isOverridden = day.hotel !== null;
  
  const handleSetGlobalHotel = () => {
    if (day.hotel) {
      setDefaultHotel(day.hotel);
    }
  };
  
  const handleClearDayHotel = () => {
    setDayHotel(dayIndex, null);
    onHotelSelect(null);
  };
  
  const handleSetDayHotel = (hotel: Poi) => {
    setDayHotel(dayIndex, hotel);
    onHotelSelect(hotel);
  };
  
  return (
    <div className="space-y-3">
      <h4 className="font-medium text-gray-700">酒店锚点</h4>
      
      {effectiveHotel ? (
        <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-green-800">{effectiveHotel.name}</p>
              <p className="text-sm text-green-600">
                {isOverridden ? '当天覆盖' : '全局默认'}
              </p>
            </div>
            <div className="flex gap-2">
              {isOverridden && (
                <button
                  onClick={handleClearDayHotel}
                  className="text-sm text-gray-500 hover:text-gray-700"
                >
                  恢复默认
                </button>
              )}
              {isOverridden && day.hotel && (
                <button
                  onClick={handleSetGlobalHotel}
                  className="text-sm text-blue-500 hover:text-blue-700"
                >
                  设为默认
                </button>
              )}
            </div>
          </div>
          
          <div className="mt-2 text-sm text-green-600">
            <p>每天行程：酒店 → 景点 → ... → 酒店</p>
          </div>
        </div>
      ) : (
        <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
          <p className="text-yellow-700">未设置酒店</p>
          <p className="text-sm text-yellow-600 mt-1">
            设置酒店后，每天行程将从酒店出发并返回酒店
          </p>
        </div>
      )}
    </div>
  );
};
