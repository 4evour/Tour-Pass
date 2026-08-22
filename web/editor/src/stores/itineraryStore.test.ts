import { beforeEach, describe, expect, it } from 'vitest';
import { useItineraryStore } from './itineraryStore';
import type { DayPlan } from '../types';

function day(dayNumber: number): DayPlan {
  return {
    day: dayNumber,
    stops: [],
    hotel: null,
    startPoint: { type: 'hotel', poi: null },
  };
}

describe('itineraryStore day synchronization', () => {
  beforeEach(() => {
    useItineraryStore.setState({ totalDays: 3, days: [day(1), day(2), day(3)] });
  });

  it('removes extra day plans when totalDays is reduced', () => {
    useItineraryStore.getState().setTotalDays(1);
    useItineraryStore.getState().syncDaysFromTotal();

    expect(useItineraryStore.getState().days).toEqual([day(1)]);
  });
});
