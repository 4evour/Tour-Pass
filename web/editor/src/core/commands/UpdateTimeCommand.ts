import { Command } from './Command';
import type { ItineraryStore } from './AddStopCommand';

export class UpdateTimeCommand implements Command {
  type = 'UPDATE_TIME';
  description: string;
  
  private oldValue: number;
  
  constructor(
    private store: ItineraryStore,
    private dayIndex: number,
    private stopIndex: number,
    private field: 'arrival' | 'departure' | 'travelMinutes',
    private newValue: number
  ) {
    const day = store.days[dayIndex];
    const stop = day?.stops[stopIndex];
    this.oldValue = stop?.[field] || 0;
    
    const fieldNames = {
      arrival: '到达时间',
      departure: '离开时间',
      travelMinutes: '通勤时间'
    };
    this.description = `更新 ${stop?.poi.name || '未知景点'} 的${fieldNames[field]}`;
  }
  
  execute(): void {
    const day = this.store.days[this.dayIndex];
    if (!day) return;
    
    const newDays = [...this.store.days];
    const newStops = [...day.stops];
    newStops[this.stopIndex] = {
      ...newStops[this.stopIndex],
      [this.field]: this.newValue
    };
    newDays[this.dayIndex] = { ...day, stops: newStops };
    
    this.store.setDays(newDays);
  }
  
  undo(): void {
    const day = this.store.days[this.dayIndex];
    if (!day) return;
    
    const newDays = [...this.store.days];
    const newStops = [...day.stops];
    newStops[this.stopIndex] = {
      ...newStops[this.stopIndex],
      [this.field]: this.oldValue
    };
    newDays[this.dayIndex] = { ...day, stops: newStops };
    
    this.store.setDays(newDays);
  }
}
