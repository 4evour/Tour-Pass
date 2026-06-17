import { describe, it, expect, beforeEach } from 'vitest';
import { ReorderCommand } from '../ReorderCommand';
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

describe('ReorderCommand', () => {
  let store: ReturnType<typeof createMockStore>;
  
  beforeEach(() => {
    const stops: Stop[] = [
      { id: 'stop-1', poi: createMockPoi('poi-1', '橘子洲头'), arrival: 540, departure: 600, travelMinutes: 0 },
      { id: 'stop-2', poi: createMockPoi('poi-2', '岳麓山'), arrival: 600, departure: 660, travelMinutes: 30 },
      { id: 'stop-3', poi: createMockPoi('poi-3', '太平街'), arrival: 660, departure: 720, travelMinutes: 20 }
    ];
    store = createMockStore(stops);
  });
  
  it('should move stop from old index to new index', () => {
    const command = new ReorderCommand(store as any, 0, 0, 2);
    
    command.execute();
    
    expect(store.days[0].stops[0].poi.name).toBe('岳麓山');
    expect(store.days[0].stops[1].poi.name).toBe('太平街');
    expect(store.days[0].stops[2].poi.name).toBe('橘子洲头');
  });
  
  it('should restore original order on undo', () => {
    const command = new ReorderCommand(store as any, 0, 0, 2);
    
    command.execute();
    command.undo();
    
    expect(store.days[0].stops[0].poi.name).toBe('橘子洲头');
    expect(store.days[0].stops[1].poi.name).toBe('岳麓山');
    expect(store.days[0].stops[2].poi.name).toBe('太平街');
  });
  
  it('should have correct description', () => {
    const command = new ReorderCommand(store as any, 0, 0, 2);
    
    expect(command.description).toBe('第1天：移动 橘子洲头 到新位置');
  });
});
