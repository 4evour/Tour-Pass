import React, { useState } from 'react';
import type { DayPlan, Stop } from '../../types';

interface BudgetTrackerProps {
  day: DayPlan;
  onBudgetUpdate: (stopId: string, cost: number) => void;
}

interface CostItem {
  stopId: string;
  name: string;
  category: string;
  amount: number;
}

export const BudgetTracker: React.FC<BudgetTrackerProps> = ({ day, onBudgetUpdate }) => {
  const [costs, setCosts] = useState<CostItem[]>([]);
  
  const totalBudget = costs.reduce((sum, c) => sum + c.amount, 0);
  const categoryTotals = calculateCategoryTotals(costs);
  
  const handleAddCost = (stop: Stop) => {
    const amount = prompt(`请输入${stop.poi.name}的费用（元）：`);
    if (amount && !isNaN(Number(amount))) {
      const newCost: CostItem = {
        stopId: stop.id,
        name: stop.poi.name,
        category: stop.poi.type,
        amount: Number(amount),
      };
      setCosts([...costs, newCost]);
      onBudgetUpdate(stop.id, Number(amount));
    }
  };
  
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="font-medium text-gray-700">预算追踪</h4>
        <span className="text-2xl font-bold text-green-600">¥{totalBudget}</span>
      </div>
      
      {/* 分类统计 */}
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(categoryTotals).map(([category, total]) => (
          <div key={category} className="p-2 bg-gray-50 rounded">
            <div className="text-sm text-gray-500">{getCategoryName(category)}</div>
            <div className="font-medium">¥{total}</div>
          </div>
        ))}
      </div>
      
      {/* 费用列表 */}
      <div className="space-y-2">
        {day.stops.map((stop) => {
          const cost = costs.find(c => c.stopId === stop.id);
          return (
            <div
              key={stop.id}
              className="flex items-center justify-between p-2 border rounded"
            >
              <span className="text-sm">{stop.poi.name}</span>
              {cost ? (
                <span className="text-green-600 font-medium">¥{cost.amount}</span>
              ) : (
                <button
                  onClick={() => handleAddCost(stop)}
                  className="text-sm text-blue-500 hover:text-blue-700"
                >
                  添加费用
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

function calculateCategoryTotals(costs: CostItem[]): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const cost of costs) {
    totals[cost.category] = (totals[cost.category] || 0) + cost.amount;
  }
  return totals;
}

function getCategoryName(category: string): string {
  const names: Record<string, string> = {
    attraction: '景点',
    restaurant: '餐饮',
    hotel: '住宿',
    nightlife: '娱乐',
    transit: '交通',
  };
  return names[category] || category;
}
