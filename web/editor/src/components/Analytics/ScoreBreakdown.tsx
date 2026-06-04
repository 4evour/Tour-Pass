import React from 'react';
import type { DayPlan } from '../../types';

interface ScoreBreakdownProps {
  day: DayPlan;
}

export const ScoreBreakdown: React.FC<ScoreBreakdownProps> = ({ day }) => {
  const totalScore = calculateTotalScore(day);
  const dimensions = calculateDimensions(day);
  
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="font-medium text-gray-700">行程评分</h4>
        <span className="text-2xl font-bold text-blue-600">{totalScore}</span>
      </div>
      
      <div className="space-y-3">
        {dimensions.map((dim, i) => (
          <div key={i}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-gray-600">{dim.label}</span>
              <span className="text-sm font-medium">{dim.score}</span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${dim.score}%`,
                  backgroundColor: dim.color,
                }}
              />
            </div>
          </div>
        ))}
      </div>
      
      <div className="p-3 bg-blue-50 rounded-lg">
        <p className="text-sm text-blue-700">{generateSummary(day, totalScore)}</p>
      </div>
    </div>
  );
};

interface Dimension {
  label: string;
  score: number;
  color: string;
}

function calculateTotalScore(day: DayPlan): number {
  if (day.stops.length === 0) return 0;
  
  const popularity = day.stops.reduce((sum, s) => sum + (s.poi.popularity || 0), 0) / day.stops.length;
  const variety = calculateVariety(day);
  const efficiency = calculateEfficiency(day);
  
  return Math.round((popularity * 40 + variety * 30 + efficiency * 30));
}

function calculateDimensions(day: DayPlan): Dimension[] {
  return [
    {
      label: '景点热度',
      score: Math.round(day.stops.reduce((sum, s) => sum + (s.poi.popularity || 0), 0) / Math.max(day.stops.length, 1) * 100),
      color: '#3b82f6',
    },
    {
      label: '行程多样性',
      score: Math.round(calculateVariety(day) * 100),
      color: '#10b981',
    },
    {
      label: '时间效率',
      score: Math.round(calculateEfficiency(day) * 100),
      color: '#f59e0b',
    },
    {
      label: '区域覆盖',
      score: Math.round(calculateAreaCoverage(day) * 100),
      color: '#8b5cf6',
    },
  ];
}

function calculateVariety(day: DayPlan): number {
  const types = new Set(day.stops.map(s => s.poi.type));
  return Math.min(types.size / 3, 1);
}

function calculateEfficiency(day: DayPlan): number {
  if (day.stops.length < 2) return 1;
  
  const totalTravel = day.stops.reduce((sum, s) => sum + s.travelMinutes, 0);
  const totalVisit = day.stops.reduce((sum, s) => sum + (s.poi.visit_duration || 60), 0);
  
  return Math.min(totalVisit / (totalTravel + totalVisit), 1);
}

function calculateAreaCoverage(day: DayPlan): number {
  const areas = new Set(day.stops.map(s => s.poi.area));
  return Math.min(areas.size / 3, 1);
}

function generateSummary(day: DayPlan, score: number): string {
  if (score >= 80) return '行程安排非常合理，景点热度高且分布均匀！';
  if (score >= 60) return '行程安排较好，可以考虑增加一些热门景点。';
  if (score >= 40) return '行程安排一般，建议优化景点选择和时间分配。';
  return '行程安排有待优化，建议重新规划。';
}
