import type { Stop } from '../types';

const DEFAULT_START = 9 * 60; // 09:00

/**
 * 重算 stops 的 arrival/departure 时间
 * 从给定的 startMinutes 开始，依次累加通勤时间和游览时长
 */
export function recalcTimes(stops: Stop[], startMinutes = DEFAULT_START): Stop[] {
  let current = startMinutes;
  return stops.map((stop, i) => {
    const travel = i === 0 ? 0 : (stop.travelMinutes || 10);
    current += travel;
    // 如果用户手动固定了到达时间，优先使用
    const arrival = stop.arrivalOverride ?? Math.max(current, stop.poi.open_minutes ?? 0);
    const duration = stop.poi.visit_duration || 60;
    const departure = arrival + duration;
    current = departure;
    return { ...stop, arrival, departure, travelMinutes: travel };
  });
}
