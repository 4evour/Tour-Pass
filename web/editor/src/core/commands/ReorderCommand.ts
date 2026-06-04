import { Command } from './Command';
import type { ItineraryStore } from './AddStopCommand';

export class ReorderCommand implements Command {
  type = 'REORDER';
  description: string;
  
  constructor(
    private store: ItineraryStore,
    private dayIndex: number,
    private oldIndex: number,
    private newIndex: number
  ) {
    const day = store.days[dayIndex];
    const stop = day?.stops[oldIndex];
    this.description = `第${dayIndex + 1}天：移动 ${stop?.poi.name || '未知景点'} 到新位置`;
  }
  
  execute(): void {
    const day = this.store.days[this.dayIndex];
    if (!day) return;
    
    const newDays = [...this.store.days];
    const newStops = [...day.stops];
    const [removed] = newStops.splice(this.oldIndex, 1);
    newStops.splice(this.newIndex, 0, removed);
    newDays[this.dayIndex] = { ...day, stops: newStops };
    
    this.store.setDays(newDays);
  }
  
  undo(): void {
    const day = this.store.days[this.dayIndex];
    if (!day) return;
    
    const newDays = [...this.store.days];
    const newStops = [...day.stops];
    const [removed] = newStops.splice(this.newIndex, 1);
    newStops.splice(this.oldIndex, 0, removed);
    newDays[this.dayIndex] = { ...day, stops: newStops };
    
    this.store.setDays(newDays);
  }
}
