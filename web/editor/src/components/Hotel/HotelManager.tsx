import React, { useState, useEffect } from 'react';
import { HotelRecommend } from './HotelRecommend';
import { HotelService, type Hotel } from '../../core/services/hotelService';
import { useItineraryStore } from '../../stores/itineraryStore';

interface HotelManagerProps {
  city: string;
}

export const HotelManager: React.FC<HotelManagerProps> = ({ city }) => {
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const defaultHotel = useItineraryStore(state => state.defaultHotel);
  const setDefaultHotel = useItineraryStore(state => state.setDefaultHotel);
  
  const hotelService = new HotelService();
  
  useEffect(() => {
    if (!city) return;
    
    setIsLoading(true);
    setError(null);
    
    hotelService.searchHotels(city)
      .then(data => {
        setHotels(data);
        setIsLoading(false);
      })
      .catch(err => {
        setError('加载酒店失败');
        setIsLoading(false);
      });
  }, [city]);
  
  const handleSelectHotel = (hotel: Hotel) => {
    const poi = {
      id: hotel.id,
      name: hotel.name,
      type: 'hotel' as const,
      area: '',
      lat: hotel.coordinates.latitude,
      lng: hotel.coordinates.longitude,
      popularity: hotel.rating,
      price_level: hotel.price < 300 ? 1 : hotel.price < 800 ? 2 : 3,
      description: '',
      meal_type: '',
      recommendation: ''
    };
    setDefaultHotel(poi);
  };
  
  return (
    <div className="space-y-4">
      <h3 className="font-medium text-gray-700">酒店推荐</h3>
      
      {defaultHotel && (
        <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-700">
            当前酒店：{defaultHotel.name}
          </p>
        </div>
      )}
      
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}
      
      <HotelRecommend
        hotels={hotels}
        onSelect={handleSelectHotel}
        isLoading={isLoading}
      />
    </div>
  );
};
