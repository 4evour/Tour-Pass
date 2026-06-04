import { Command } from './Command';
import type { Stop, DayPlan } from '../../types';
import type { ItineraryStore } from './AddStopCommand';

export class RemoveStopCommand implements Command {
  type = 'REMOVE_STOP';
  description: string;
  
  private removedStop: Stop | null = null;
  private removedIndex: number = -1;
  
  constructor(
    private store: ItineraryStore,
    private dayIndex: number,
    private stopIndex: number
  ) {
    const day = store.days[dayIndex];
    const stop = day?.stops[stopIndex];
    this.description = `从第${dayIndex + 1}天移除 ${stop?.poi.name || '未知景点'}`;
  }
  
  execute(): void {
    const day = this.store.days[this.dayIndex];
    if (!day) return;
    
    this.removedStop = day.stops[this.stopIndex];
    this.removedIndex = this.stopIndex;
    
    const newDays = [...this.store.days];
    const newStops = day.stops.filter((_, i) => i !== this.stopIndex);
    newDays[this.dayIndex] = { ...day, stops: newStops };
    
    this.store.setDays(newDays);
  }
  
  undo(): void {
    if (!this.removedStop || this.removedIndex === -1) return;
    
    const day = this.store.days[this.dayIndex];
    if (!day) return;
    
    const newDays = [...this.store.days];
    const newStops = [...day.stops];
    newStops.splice(this.removedIndex, 0, this.removedStop);
    newDays[this.dayIndex] = { ...day, stops: newStops };
    
    this.store.setDays(newDays);
    this.removedStop = null;
    this.removedIndex = -1;
  }
}
