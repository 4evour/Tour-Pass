import React, { useState } from 'react';
import type { Hotel } from '../../core/services/hotelService';

interface HotelRecommendProps {
  hotels: Hotel[];
  onSelect: (hotel: Hotel) => void;
  isLoading: boolean;
}

export const HotelRecommend: React.FC<HotelRecommendProps> = ({ 
  hotels, 
  onSelect, 
  isLoading 
}) => {
  const [priceRange, setPriceRange] = useState<'budget' | 'comfort' | 'luxury'>('comfort');
  
  const priceLabels = {
    budget: '经济',
    comfort: '舒适',
    luxury: '豪华'
  };
  
  const priceFilters = {
    budget: (h: Hotel) => h.price < 300,
    comfort: (h: Hotel) => h.price >= 300 && h.price < 800,
    luxury: (h: Hotel) => h.price >= 800
  };
  
  const filteredHotels = hotels.filter(priceFilters[priceRange]);
  
  if (isLoading) {
    return (
      <div className="p-4 text-center text-gray-500">
        加载中...
      </div>
    );
  }
  
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {Object.entries(priceLabels).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setPriceRange(key as any)}
            className={`px-3 py-1.5 text-sm rounded ${
              priceRange === key
                ? 'bg-blue-500 text-white'
                : 'bg-gray-100 hover:bg-gray-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      
      <div className="space-y-3">
        {filteredHotels.map(hotel => (
          <div
            key={hotel.id}
            onClick={() => onSelect(hotel)}
            className="p-3 border rounded-lg cursor-pointer hover:border-blue-500 hover:bg-blue-50"
          >
            <div className="flex gap-3">
              {hotel.image && (
                <img 
                  src={hotel.image} 
                  alt={hotel.name}
                  className="w-20 h-20 object-cover rounded"
                />
              )}
              <div>
                <h4 className="font-medium">{hotel.name}</h4>
                <p className="text-sm text-gray-500">
                  {'⭐'.repeat(Math.round(hotel.rating))} {hotel.rating}
                </p>
                <p className="text-sm text-blue-600 font-medium">
                  ¥{hotel.price}/晚
                </p>
              </div>
            </div>
          </div>
        ))}
        
        {filteredHotels.length === 0 && (
          <p className="text-gray-500 text-center py-4">
            暂无符合条件的酒店
          </p>
        )}
      </div>
    </div>
  );
};
