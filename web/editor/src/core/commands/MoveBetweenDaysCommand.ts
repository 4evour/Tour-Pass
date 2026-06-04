import { Command } from './Command';
import type { Stop } from '../../types';
import type { ItineraryStore } from './AddStopCommand';

export class MoveBetweenDaysCommand implements Command {
  type = 'MOVE_BETWEEN_DAYS';
  description: string;
  
  private movedStop: Stop | null = null;
  
  constructor(
    private store: ItineraryStore,
    private fromDayIndex: number,
    private fromStopIndex: number,
    private toDayIndex: number,
    private toStopIndex: number
  ) {
    const fromDay = store.days[fromDayIndex];
    const stop = fromDay?.stops[fromStopIndex];
    this.description = `移动 ${stop?.poi.name || '未知景点'} 从第${fromDayIndex + 1}天到第${toDayIndex + 1}天`;
  }
  
  execute(): void {
    const fromDay = this.store.days[this.fromDayIndex];
    const toDay = this.store.days[this.toDayIndex];
    if (!fromDay || !toDay) return;
    
    this.movedStop = fromDay.stops[this.fromStopIndex];
    
    const newDays = [...this.store.days];
    const newFromStops = fromDay.stops.filter((_, i) => i !== this.fromStopIndex);
    const newToStops = [...toDay.stops];
    newToStops.splice(this.toStopIndex, 0, this.movedStop);
    
    newDays[this.fromDayIndex] = { ...fromDay, stops: newFromStops };
    newDays[this.toDayIndex] = { ...toDay, stops: newToStops };
    
    this.store.setDays(newDays);
  }
  
  undo(): void {
    if (!this.movedStop) return;
    
    const fromDay = this.store.days[this.fromDayIndex];
    const toDay = this.store.days[this.toDayIndex];
    if (!fromDay || !toDay) return;
    
    const newDays = [...this.store.days];
    const newToStops = toDay.stops.filter(s => s.id !== this.movedStop!.id);
    const newFromStops = [...fromDay.stops];
    newFromStops.splice(this.fromStopIndex, 0, this.movedStop);
    
    newDays[this.fromDayIndex] = { ...fromDay, stops: newFromStops };
    newDays[this.toDayIndex] = { ...toDay, stops: newToStops };
    
    this.store.setDays(newDays);
    this.movedStop = null;
  }
}
