import { describe, it, expect, beforeEach } from 'vitest';
import { AddStopCommand } from '../AddStopCommand';
import type { Poi, Stop, DayPlan } from '../../../types';

const createMockStore = () => {
  const store = {
    days: [{ day: 1, stops: [] as Stop[], hotel: null, startPoint: { type: 'hotel' as const, poi: null } }] as DayPlan[],
    updateDay: (dayIndex: number, updates: Partial<DayPlan>) => {
      Object.assign(store.days[dayIndex], updates);
    }
  };
  return store;
};

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

describe('AddStopCommand', () => {
  let store: ReturnType<typeof createMockStore>;
  
  beforeEach(() => {
    store = createMockStore();
  });
  
  it('should add stop to specified day and index', () => {
    const poi = createMockPoi('poi-1', 'Test POI');
    const command = new AddStopCommand(store as any, 0, poi, 0);
    
    command.execute();
    
    expect(store.days[0].stops).toHaveLength(1);
    expect(store.days[0].stops[0].poi.id).toBe('poi-1');
  });
  
  it('should remove stop on undo', () => {
    const poi = createMockPoi('poi-1', 'Test POI');
    const command = new AddStopCommand(store as any, 0, poi, 0);
    
    command.execute();
    command.undo();
    
    expect(store.days[0].stops).toHaveLength(0);
  });
  
  it('should have correct description', () => {
    const poi = createMockPoi('poi-1', '橘子洲头');
    const command = new AddStopCommand(store as any, 0, poi, 0);
    
    expect(command.description).toBe('添加 橘子洲头 到第1天');
  });
  
  it('should add stop at specific index', () => {
    const poi1 = createMockPoi('poi-1', '景点A');
    const poi2 = createMockPoi('poi-2', '景点B');
    const poi3 = createMockPoi('poi-3', '景点C');
    
    const cmd1 = new AddStopCommand(store as any, 0, poi1, 0);
    const cmd2 = new AddStopCommand(store as any, 0, poi2, 1);
    const cmd3 = new AddStopCommand(store as any, 0, poi3, 1);
    
    cmd1.execute();
    cmd2.execute();
    cmd3.execute();
    
    expect(store.days[0].stops).toHaveLength(3);
    expect(store.days[0].stops[0].poi.name).toBe('景点A');
    expect(store.days[0].stops[1].poi.name).toBe('景点C');
    expect(store.days[0].stops[2].poi.name).toBe('景点B');
  });
});
