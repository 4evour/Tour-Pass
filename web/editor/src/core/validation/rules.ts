import type { DayPlan } from '../../types';

export interface Issue {
  type: string;
  message: string;
  severity: 'error' | 'warning';
  stopIndex?: number;
}

export function checkTimeConflicts(day: DayPlan): Issue[] {
  const issues: Issue[] = [];
  
  for (let i = 0; i < day.stops.length - 1; i++) {
    const current = day.stops[i];
    const next = day.stops[i + 1];
    
    if (current.departure > next.arrival) {
      issues.push({
        type: 'time-conflict',
        message: `时间冲突：${current.poi.name}和${next.poi.name}时间重叠`,
        severity: 'error',
        stopIndex: i
      });
    }
  }
  
  return issues;
}

export function checkTotalDuration(day: DayPlan): Issue[] {
  const issues: Issue[] = [];
  
  if (day.stops.length === 0) return issues;
  
  const firstStop = day.stops[0];
  const lastStop = day.stops[day.stops.length - 1];
  const totalMinutes = lastStop.departure - firstStop.arrival;
  const totalHours = totalMinutes / 60;
  
  if (totalHours > 12) {
    issues.push({
      type: 'total-duration',
      message: `行程过紧：总耗时${totalHours.toFixed(1)}小时，建议减少景点`,
      severity: 'warning'
    });
  }
  
  return issues;
}

export function checkTravelTime(day: DayPlan): Issue[] {
  const issues: Issue[] = [];
  
  for (let i = 1; i < day.stops.length; i++) {
    const current = day.stops[i];
    const previous = day.stops[i - 1];
    
    const availableTime = current.arrival - previous.departure;
    const requiredTime = current.travelMinutes;
    
    if (availableTime < requiredTime) {
      issues.push({
        type: 'travel-time',
        message: `通勤时间不足：从${previous.poi.name}到${current.poi.name}需要${requiredTime}分钟`,
        severity: 'error',
        stopIndex: i
      });
    }
  }
  
  return issues;
}

export function validateDay(day: DayPlan): Issue[] {
  return [
    ...checkTimeConflicts(day),
    ...checkTotalDuration(day),
    ...checkTravelTime(day)
  ];
}
