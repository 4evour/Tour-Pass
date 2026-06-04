import React, { useState, useEffect } from 'react';
import { HotelService, type Hotel, type HotelDetail } from '../../core/services/hotelService';

interface HotelDetailCardProps {
  hotelId: string;
  onSelect: (hotel: Hotel) => void;
  onClose: () => void;
}

export const HotelDetailCard: React.FC<HotelDetailCardProps> = ({
  hotelId,
  onSelect,
  onClose,
}) => {
  const [detail, setDetail] = useState<HotelDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const hotelService = new HotelService();
  
  useEffect(() => {
    setIsLoading(true);
    setError(null);
    
    hotelService.getHotelDetails(hotelId)
      .then(data => {
        setDetail(data);
        setIsLoading(false);
      })
      .catch(err => {
        setError('加载酒店详情失败');
        setIsLoading(false);
      });
  }, [hotelId]);
  
  if (isLoading) {
    return (
      <div className="p-4 text-center text-gray-500">
        加载中...
      </div>
    );
  }
  
  if (error || !detail) {
    return (
      <div className="p-4 text-center text-red-500">
        {error || '酒店信息加载失败'}
      </div>
    );
  }
  
  return (
    <div className="border rounded-lg overflow-hidden">
      {/* 图片 */}
      {detail.image && (
        <img
          src={detail.image}
          alt={detail.name}
          className="w-full h-48 object-cover"
        />
      )}
      
      <div className="p-4 space-y-3">
        {/* 名称和评分 */}
        <div>
          <h3 className="text-lg font-bold">{detail.name}</h3>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-yellow-500">
              {'⭐'.repeat(Math.round(detail.rating))}
            </span>
            <span className="text-gray-600">{detail.rating}</span>
            {detail.reviews > 0 && (
              <span className="text-gray-400">({detail.reviews}条评论)</span>
            )}
          </div>
        </div>
        
        {/* 价格 */}
        <div className="flex items-center justify-between">
          <span className="text-2xl font-bold text-blue-600">
            ¥{detail.price}
          </span>
          <span className="text-gray-500">/晚</span>
        </div>
        
        {/* 描述 */}
        {detail.description && (
          <p className="text-gray-600 text-sm">{detail.description}</p>
        )}
        
        {/* 设施 */}
        {detail.amenities && detail.amenities.length > 0 && (
          <div>
            <h4 className="font-medium text-gray-700 mb-2">酒店设施</h4>
            <div className="flex flex-wrap gap-2">
              {detail.amenities.map((amenity, i) => (
                <span
                  key={i}
                  className="px-2 py-1 bg-gray-100 text-gray-600 text-sm rounded"
                >
                  {amenity}
                </span>
              ))}
            </div>
          </div>
        )}
        
        {/* 操作按钮 */}
        <div className="flex gap-2 pt-2">
          <button
            onClick={() => onSelect(detail)}
            className="flex-1 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            选择此酒店
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
};
