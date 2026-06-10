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

export function checkOpeningHours(day: DayPlan): Issue[] {
  const issues: Issue[] = [];

  for (let i = 0; i < day.stops.length; i++) {
    const stop = day.stops[i];
    const poi = stop.poi;

    // 只对有 arrive/depart 和 open/close 时间的 stop 做检查
    if (stop.arrival <= 0 || stop.departure <= 0) continue;
    if (!poi.open_minutes && !poi.close_minutes) continue;

    if (poi.open_minutes && stop.arrival < poi.open_minutes) {
      issues.push({
        type: 'opening-hours',
        message: `${poi.name} 到达太早：${fmtTime(stop.arrival)}，景点 ${fmtTime(poi.open_minutes)} 才开门`,
        severity: 'warning',
        stopIndex: i
      });
    }

    if (poi.close_minutes && stop.departure > poi.close_minutes) {
      issues.push({
        type: 'closing-hours',
        message: `${poi.name} 离开太晚：${fmtTime(stop.departure)}，景点 ${fmtTime(poi.close_minutes)} 已关门`,
        severity: 'error',
        stopIndex: i
      });
    }
  }

  return issues;
}

// 检查空白天
export function checkEmptyDay(day: DayPlan): Issue[] {
  if (day.stops.length === 0) {
    return [{
      type: 'empty-day',
      message: `第${day.day}天没有任何景点，建议添加或删除这天`,
      severity: 'warning'
    }];
  }
  return [];
}

function fmtTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}

export function validateDay(day: DayPlan): Issue[] {
  return [
    ...checkTimeConflicts(day),
    ...checkTotalDuration(day),
    ...checkTravelTime(day),
    ...checkOpeningHours(day),
    ...checkEmptyDay(day),
  ];
}
