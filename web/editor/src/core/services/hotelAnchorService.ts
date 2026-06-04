import type { Poi, DayPlan } from '../../types';

export interface HotelAnchor {
  hotel: Poi;
  isGlobal: boolean;
  dayIndex?: number;
}

export class HotelAnchorService {
  /**
   * 获取某天的有效酒店
   * 优先使用单日酒店，否则使用全局酒店
   */
  getEffectiveHotel(
    day: DayPlan,
    defaultHotel: Poi | null
  ): Poi | null {
    return day.hotel || defaultHotel;
  }
  
  /**
   * 计算包含酒店的完整路线
   * 酒店 → 景点1 → 景点2 → ... → 酒店
   */
  calculateRouteWithHotel(
    day: DayPlan,
    defaultHotel: Poi | null
  ): Poi[] {
    const hotel = this.getEffectiveHotel(day, defaultHotel);
    if (!hotel) {
      return day.stops.map(s => s.poi);
    }
    
    const route: Poi[] = [hotel];
    
    for (const stop of day.stops) {
      route.push(stop.poi);
    }
    
    route.push(hotel);
    
    return route;
  }
  
  /**
   * 计算包含酒店的通勤时间
   */
  calculateTravelTimeWithHotel(
    day: DayPlan,
    defaultHotel: Poi | null,
    getDistance: (from: Poi, to: Poi) => number
  ): number[] {
    const hotel = this.getEffectiveHotel(day, defaultHotel);
    if (!hotel) {
      return day.stops.map(s => s.travelMinutes);
    }
    
    const travelTimes: number[] = [];
    
    // 酒店到第一个景点
    if (day.stops.length > 0) {
      travelTimes.push(getDistance(hotel, day.stops[0].poi));
    }
    
    // 景点之间的通勤时间
    for (let i = 0; i < day.stops.length - 1; i++) {
      travelTimes.push(getDistance(day.stops[i].poi, day.stops[i + 1].poi));
    }
    
    // 最后一个景点到酒店
    if (day.stops.length > 0) {
      travelTimes.push(getDistance(day.stops[day.stops.length - 1].poi, hotel));
    }
    
    return travelTimes;
  }
  
  /**
   * 检查酒店是否在合理距离内
   */
  isHotelInRange(
    hotel: Poi,
    stops: Array<{ poi: Poi }>,
    maxDistanceKm: number = 10
  ): boolean {
    if (stops.length === 0) return true;
    
    const distances = stops.map(s => this.calculateDistance(hotel, s.poi));
    const maxDistance = Math.max(...distances);
    
    return maxDistance <= maxDistanceKm;
  }
  
  /**
   * 计算两点之间的距离（公里）
   */
  private calculateDistance(from: Poi, to: Poi): number {
    const R = 6371; // 地球半径（公里）
    const dLat = this.toRad(to.lat - from.lat);
    const dLon = this.toRad(to.lng - from.lng);
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(this.toRad(from.lat)) *
        Math.cos(this.toRad(to.lat)) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
  }
  
  private toRad(deg: number): number {
    return deg * (Math.PI / 180);
  }
}

export const hotelAnchorService = new HotelAnchorService();
