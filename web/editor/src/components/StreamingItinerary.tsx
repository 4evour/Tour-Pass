import { useMemo } from 'react';

interface Stop {
  slot?: string;
  poi_name?: string;
  poi_type?: string;
  area?: string;
  start_minutes?: number;
  end_minutes?: number;
  reason?: string;
}

interface DayPlan {
  day: number;
  stops?: Stop[];
  summary?: string;
}

interface Itinerary {
  city?: string;
  days?: DayPlan[];
  hotel?: { name?: string; area?: string } | null;
  summary?: string;
  variant_name?: string;
  travel_tips?: string[];
  alternatives?: string[];
}

interface Props {
  itinerary: Itinerary;
  compact?: boolean;
}

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}

const SLOT_ICONS: Record<string, string> = {
  '上午': '🌅',
  '中午': '🍜',
  '下午': '☀️',
  '傍晚': '🌆',
  '晚上': '🌙',
};

export default function StreamingItinerary({ itinerary, compact = false }: Props) {
  const content = useMemo(() => {
    if (!itinerary?.days?.length) return null;
    return itinerary;
  }, [itinerary]);

  if (!content) return null;

  return (
    <div className={`${compact ? 'text-xs' : 'text-sm'} space-y-3`}>
      {/* Hotel */}
      {content.hotel && (
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 rounded-lg border border-amber-200">
          <span>🏨</span>
          <div>
            <div className="font-medium text-amber-800">{content.hotel.name}</div>
            {content.hotel.area && (
              <div className="text-amber-600 text-xs">{content.hotel.area}</div>
            )}
          </div>
        </div>
      )}

      {/* Daily plans */}
      {(content.days || []).map((day) => (
        <div key={day.day} className="border rounded-lg overflow-hidden">
          <div className="px-3 py-2 bg-primary-50 border-b">
            <span className="font-semibold text-primary-800">
              📅 第 {day.day} 天
            </span>
            {day.summary && (
              <span className="text-primary-600 text-xs ml-2">{day.summary}</span>
            )}
          </div>
          <div className="divide-y">
            {day.stops?.map((stop, j) => (
              <div key={j} className="px-3 py-2 flex items-start gap-2 hover:bg-gray-50 transition-colors">
                <span className="flex-shrink-0 mt-0.5">
                  {SLOT_ICONS[stop.slot || ''] || '📍'}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium truncate">{stop.poi_name}</span>
                    {stop.area && (
                      <span className="text-gray-400 text-xs flex-shrink-0">{stop.area}</span>
                    )}
                  </div>
                  {stop.start_minutes != null && stop.end_minutes != null && (
                    <div className="text-gray-500 text-xs mt-0.5">
                      {formatTime(stop.start_minutes)} - {formatTime(stop.end_minutes)}
                    </div>
                  )}
                  {stop.reason && (
                    <div className="text-gray-600 text-xs mt-1 italic">{stop.reason}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Travel tips */}
      {content.travel_tips && content.travel_tips.length > 0 && (
        <div className="px-3 py-2 bg-green-50 rounded-lg border border-green-200">
          <div className="text-xs font-medium text-green-800 mb-1">💡 旅行贴士</div>
          {content.travel_tips.map((tip, i) => (
            <div key={i} className="text-green-700 text-xs">• {tip}</div>
          ))}
        </div>
      )}
    </div>
  );
}


