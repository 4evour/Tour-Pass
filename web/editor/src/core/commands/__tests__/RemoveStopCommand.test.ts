import { describe, it, expect, beforeEach } from 'vitest';
import { RemoveStopCommand } from '../RemoveStopCommand';
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

const createMockStore = (initialStops: Stop[] = []) => {
  const store = {
    days: [{ day: 1, stops: initialStops, hotel: null, startPoint: { type: 'hotel' as const, poi: null } }] as DayPlan[],
    setDays: (days: DayPlan[]) => {
      store.days = days;
    },
  };
  return store;
};

describe('RemoveStopCommand', () => {
  let store: ReturnType<typeof createMockStore>;
  
  beforeEach(() => {
    const stops: Stop[] = [
      { id: 'stop-1', poi: createMockPoi('poi-1', '橘子洲头'), arrival: 540, departure: 600, travelMinutes: 0 },
      { id: 'stop-2', poi: createMockPoi('poi-2', '岳麓山'), arrival: 600, departure: 660, travelMinutes: 30 }
    ];
    store = createMockStore(stops);
  });
  
  it('should remove stop at specified index', () => {
    const command = new RemoveStopCommand(store as any, 0, 0);
    
    command.execute();
    
    expect(store.days[0].stops).toHaveLength(1);
    expect(store.days[0].stops[0].id).toBe('stop-2');
  });
  
  it('should restore stop on undo', () => {
    const command = new RemoveStopCommand(store as any, 0, 0);
    
    command.execute();
    command.undo();
    
    expect(store.days[0].stops).toHaveLength(2);
    expect(store.days[0].stops[0].poi.name).toBe('橘子洲头');
  });
  
  it('should have correct description', () => {
    const command = new RemoveStopCommand(store as any, 0, 0);
    
    expect(command.description).toBe('从第1天移除 橘子洲头');
  });
});
