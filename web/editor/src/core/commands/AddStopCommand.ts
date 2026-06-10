import { Command } from './Command';
import type { Poi, Stop, DayPlan } from '../../types';
import { recalcTimes } from '../../utils/recalcTimes';

export interface ItineraryStore {
  days: DayPlan[];
  setDays: (days: DayPlan[]) => void;
}

export class AddStopCommand implements Command {
  type = 'ADD_STOP';
  description: string;
  
  private addedStop: Stop | null = null;
  
  constructor(
    private store: ItineraryStore,
    private dayIndex: number,
    private poi: Poi,
    private stopIndex: number
  ) {
    this.description = `添加 ${poi.name} 到第${dayIndex + 1}天`;
  }
  
  execute(): void {
    const day = this.store.days[this.dayIndex];
    if (!day) return;

    const newStop: Stop = {
      id: `stop-${Date.now()}`,
      poi: this.poi,
      arrival: 0,
      departure: 0,
      travelMinutes: 10
    };

    this.addedStop = newStop;

    const newDays = [...this.store.days];
    const newStops = [...day.stops];
    newStops.splice(this.stopIndex, 0, newStop);
    // 重算所有 stop 的时间
    const recalced = recalcTimes(newStops);
    newDays[this.dayIndex] = { ...day, stops: recalced };

    this.store.setDays(newDays);
  }

  undo(): void {
    if (!this.addedStop) return;

    const day = this.store.days[this.dayIndex];
    if (!day) return;

    const newDays = [...this.store.days];
    const newStops = day.stops.filter(s => s.id !== this.addedStop!.id);
    // 重算剩余 stop 的时间
    const recalced = recalcTimes(newStops);
    newDays[this.dayIndex] = { ...day, stops: recalced };

    this.store.setDays(newDays);
    this.addedStop = null;
  }
}
