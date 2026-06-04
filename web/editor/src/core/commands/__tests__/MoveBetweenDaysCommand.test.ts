import { describe, it, expect, beforeEach } from 'vitest';
import { MoveBetweenDaysCommand } from '../MoveBetweenDaysCommand';
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
    days: [
      { day: 1, stops: [
        { id: 'stop-1', poi: createMockPoi('poi-1', '橘子洲头'), arrival: 540, departure: 600, travelMinutes: 0 },
        { id: 'stop-2', poi: createMockPoi('poi-2', '岳麓山'), arrival: 600, departure: 660, travelMinutes: 30 }
      ], hotel: null, startPoint: { type: 'hotel' as const, poi: null } },
      { day: 2, stops: [
        { id: 'stop-3', poi: createMockPoi('poi-3', '太平街'), arrival: 540, departure: 600, travelMinutes: 0 }
      ], hotel: null, startPoint: { type: 'hotel' as const, poi: null } }
    ] as DayPlan[],
    updateDay: (dayIndex: number, updates: Partial<DayPlan>) => {
      Object.assign(store.days[dayIndex], updates);
    }
  };
  return store;
};

describe('MoveBetweenDaysCommand', () => {
  let store: ReturnType<typeof createMockStore>;
  
  beforeEach(() => {
    store = createMockStore();
  });
  
  it('should move stop from day 1 to day 2', () => {
    const command = new MoveBetweenDaysCommand(store as any, 0, 0, 1, 1);
    
    command.execute();
    
    expect(store.days[0].stops).toHaveLength(1);
    expect(store.days[1].stops).toHaveLength(2);
    expect(store.days[1].stops[1].poi.name).toBe('橘子洲头');
  });
  
  it('should restore on undo', () => {
    const command = new MoveBetweenDaysCommand(store as any, 0, 0, 1, 1);
    
    command.execute();
    command.undo();
    
    expect(store.days[0].stops).toHaveLength(2);
    expect(store.days[1].stops).toHaveLength(1);
    expect(store.days[0].stops[0].poi.name).toBe('橘子洲头');
  });
  
  it('should have correct description', () => {
    const command = new MoveBetweenDaysCommand(store as any, 0, 0, 1, 1);
    
    expect(command.description).toBe('移动 橘子洲头 从第1天到第2天');
  });
});
