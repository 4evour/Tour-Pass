import React, { useMemo } from 'react';
import type { Poi, DayPlan } from '../../types';

interface AreaRecommendation {
  name: string;
  center: { lat: number; lng: number };
  score: number;
  reasons: string[];
  nearbyPois: Poi[];
}

interface AreaRecommenderProps {
  days: DayPlan[];
  allPois: Poi[];
  onAreaSelect: (area: AreaRecommendation) => void;
}

export const AreaRecommender: React.FC<AreaRecommenderProps> = ({
  days,
  allPois,
  onAreaSelect,
}) => {
  const recommendations = useMemo(() => {
    return calculateAreaRecommendations(days, allPois);
  }, [days, allPois]);
  
  if (recommendations.length === 0) {
    return (
      <div className="p-4 text-center text-gray-500">
        暂无区域推荐，请先添加景点
      </div>
    );
  }
  
  return (
    <div className="space-y-3">
      <h4 className="font-medium text-gray-700">推荐入住区域</h4>
      
      <div className="space-y-2">
        {recommendations.map((area, index) => (
          <div
            key={index}
            className="p-3 border rounded-lg cursor-pointer hover:border-blue-500 hover:bg-blue-50"
            onClick={() => onAreaSelect(area)}
          >
            <div className="flex items-center justify-between">
              <h5 className="font-medium">{area.name}</h5>
              <span className="text-sm text-blue-600 font-medium">
                {Math.round(area.score)}分
              </span>
            </div>
            
            <div className="mt-2 flex flex-wrap gap-1">
              {area.reasons.map((reason, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded"
                >
                  {reason}
                </span>
              ))}
            </div>
            
            <div className="mt-2 text-sm text-gray-500">
              附近景点：{area.nearbyPois.slice(0, 3).map(p => p.name).join('、')}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

function calculateAreaRecommendations(
  days: DayPlan[],
  allPois: Poi[]
): AreaRecommendation[] {
  // 收集所有景点
  const visitedPois = days.flatMap(d => d.stops.map(s => s.poi));
  
  if (visitedPois.length === 0) {
    return [];
  }
  
  // 按区域分组
  const areaMap = new Map<string, Poi[]>();
  for (const poi of visitedPois) {
    const area = poi.area || '未知区域';
    if (!areaMap.has(area)) {
      areaMap.set(area, []);
    }
    areaMap.get(area)!.push(poi);
  }
  
  // 计算每个区域的推荐分数
  const recommendations: AreaRecommendation[] = [];
  
  for (const [areaName, pois] of areaMap) {
    const center = calculateCenter(pois);
    const score = calculateAreaScore(pois, visitedPois);
    const reasons = generateReasons(pois, visitedPois);
    
    recommendations.push({
      name: areaName,
      center,
      score,
      reasons,
      nearbyPois: pois,
    });
  }
  
  // 按分数排序
  return recommendations.sort((a, b) => b.score - a.score);
}

function calculateCenter(pois: Poi[]): { lat: number; lng: number } {
  const avgLat = pois.reduce((sum, p) => sum + p.lat, 0) / pois.length;
  const avgLng = pois.reduce((sum, p) => sum + p.lng, 0) / pois.length;
  return { lat: avgLat, lng: avgLng };
}

function calculateAreaScore(areaPois: Poi[], allPois: Poi[]): number {
  let score = 0;
  
  // 景点数量得分
  score += areaPois.length * 20;
  
  // 景点密度得分
  const density = areaPois.length / allPois.length;
  score += density * 50;
  
  // 热门景点得分
  const popularPois = areaPois.filter(p => p.popularity > 0.7);
  score += popularPois.length * 15;
  
  return Math.min(score, 100);
}

function generateReasons(areaPois: Poi[], allPois: Poi[]): string[] {
  const reasons: string[] = [];
  
  if (areaPois.length >= 3) {
    reasons.push('景点密集');
  }
  
  const popularPois = areaPois.filter(p => p.popularity > 0.7);
  if (popularPois.length > 0) {
    reasons.push('包含热门景点');
  }
  
  const restaurants = areaPois.filter(p => p.type === 'restaurant');
  if (restaurants.length > 0) {
    reasons.push('餐饮便利');
  }
  
  const hotels = areaPois.filter(p => p.type === 'hotel');
  if (hotels.length > 0) {
    reasons.push('住宿选择多');
  }
  
  return reasons;
}
