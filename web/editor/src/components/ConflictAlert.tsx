import { useEffect, useState } from 'react';
import { useItineraryStore } from '../stores/itineraryStore';

interface Issue {
  type: string;
  poi: string;
  message: string;
}

export default function ConflictAlert() {
  const { days } = useItineraryStore();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [dismissed, setDismissed] = useState(false);

  const allStops = days.flatMap(d => d.stops);

  useEffect(() => {
    if (allStops.length === 0) {
      setIssues([]);
      return;
    }

    // Client-side quick checks
    const localIssues: Issue[] = [];
    for (const stop of allStops) {
      const closeMin = stop.poi.close_minutes ?? 24 * 60;
      if (stop.arrival > closeMin) {
        localIssues.push({ type: 'closed', poi: stop.poi.name, message: `${stop.poi.name} 到达时已关门` });
      }
      if (stop.departure > 21 * 60) {
        localIssues.push({ type: 'overtime', poi: stop.poi.name, message: `${stop.poi.name} 结束时间较晚（${formatMin(stop.departure)}）` });
      }
    }

    // Check for long gaps without meals
    for (let i = 0; i < allStops.length - 1; i++) {
      const gap = allStops[i + 1].arrival - allStops[i].departure;
      const hasMeal = allStops[i].poi.type === 'restaurant' || allStops[i + 1].poi.type === 'restaurant';
      if (gap > 240 && !hasMeal) {
        localIssues.push({
          type: 'no_meal',
          poi: allStops[i].poi.name,
          message: `${allStops[i].poi.name} 到 ${allStops[i + 1].poi.name} 之间有 ${Math.round(gap / 60)} 小时空闲，建议补充餐饮`,
        });
      }
    }

    setIssues(localIssues);
    setDismissed(false);
  }, [allStops.map(s => `${s.poi.id}:${s.arrival}`).join(',')]);

  if (dismissed || issues.length === 0) return null;

  return (
    <div className="absolute top-20 right-4 z-[1000] w-72 bg-amber-50 border border-amber-200 rounded-lg shadow-md p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-semibold text-amber-800">⚠️ 行程提示</span>
        <button onClick={() => setDismissed(true)} className="ml-auto text-gray-400 hover:text-gray-600 text-xs">✕</button>
      </div>
      <div className="space-y-1">
        {issues.map((issue, i) => (
          <div key={i} className="text-xs text-amber-700 flex items-start gap-1">
            <span className="flex-shrink-0">
              {issue.type === 'closed' ? '🚫' : issue.type === 'overtime' ? '⏰' : '🍽'}
            </span>
            <span>{issue.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatMin(m: number): string {
  const h = Math.floor(m / 60);
  const min = m % 60;
  return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}
