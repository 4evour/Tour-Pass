import { describe, it, expect, beforeEach } from 'vitest';
import { UpdateTimeCommand } from '../UpdateTimeCommand';
import type { Poi, Stop, DayPlan } from '../../../types';

const createMockPoi = (id: string, name: string): Poi => ({
  id,
  name,
  type: 'attraction',
  area: 'test',
  lat: 28.2,
  lng: 112.9,
  popularity: 0.8,
  price_level: 1,
  description: '',
  meal_type: '',
  recommendation: ''
});

const createMockStore = () => {
  const store = {
    days: [{ day: 1, stops: [
      { id: 'stop-1', poi: createMockPoi('poi-1', '橘子洲头'), arrival: 540, departure: 600, travelMinutes: 0 }
    ], hotel: null, startPoint: { type: 'hotel' as const, poi: null } }] as DayPlan[],
    updateDay: (dayIndex: number, updates: Partial<DayPlan>) => {
      Object.assign(store.days[dayIndex], updates);
    }
  };
  return store;
};

describe('UpdateTimeCommand', () => {
  let store: ReturnType<typeof createMockStore>;
  
  beforeEach(() => {
    store = createMockStore();
  });
  
  it('should update arrival time', () => {
    const command = new UpdateTimeCommand(store as any, 0, 0, 'arrival', 480);
    
    command.execute();
    
    expect(store.days[0].stops[0].arrival).toBe(480);
  });
  
  it('should restore on undo', () => {
    const command = new UpdateTimeCommand(store as any, 0, 0, 'arrival', 480);
    
    command.execute();
    command.undo();
    
    expect(store.days[0].stops[0].arrival).toBe(540);
  });
  
  it('should have correct description', () => {
    const command = new UpdateTimeCommand(store as any, 0, 0, 'arrival', 480);
    
    expect(command.description).toBe('更新 橘子洲头 的到达时间');
  });
});
