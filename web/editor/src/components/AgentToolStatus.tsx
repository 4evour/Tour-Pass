interface AgentEvent {
  type: string;
  content?: string;
  [key: string]: unknown;
}

interface Props {
  events: AgentEvent[];
}

const STATUS_ICONS: Record<string, string> = {
  status: '⚙️',
  intent_parsed: '🧠',
  guides_retrieved: '📚',
  data_loaded: '🔍',
  hotel_selected: '🏨',
  day_planned: '📅',
  routes_optimized: '🗺️',
  itinerary_complete: '✅',
  cache_hit: '⚡',
  warning: '⚠️',
  error: '❌',
};

export default function AgentToolStatus({ events }: Props) {
  if (events.length === 0) return null;

  // Show the latest meaningful events
  const meaningful = events.filter(
    e => e.type !== 'status' || events.indexOf(e) === events.length - 1
  );
  const recent = meaningful.slice(-5);

  return (
    <div className="space-y-1.5">
      <div className="text-xs font-semibold text-blue-700 mb-2">🤖 AI 规划中...</div>
      {recent.map((event, i) => (
        <div key={i} className="flex items-start gap-2 text-xs">
          <span className="flex-shrink-0">{STATUS_ICONS[event.type] || '📌'}</span>
          <span className="text-gray-700">
            {event.content || formatEventType(event.type)}
          </span>
        </div>
      ))}
      {/* Pulsing indicator for the last event */}
      <div className="flex items-center gap-1 text-xs text-gray-400 mt-1">
        <span className="animate-pulse">●</span>
        <span>处理中...</span>
      </div>
    </div>
  );
}

function formatEventType(type: string): string {
  const map: Record<string, string> = {
    status: '处理中...',
    intent_parsed: '已理解需求',
    guides_retrieved: '已检索攻略',
    data_loaded: '已加载数据',
    hotel_selected: '已选酒店',
    day_planned: '已规划一天',
    routes_optimized: '路线已优化',
    itinerary_complete: '行程生成完成',
    cache_hit: '命中缓存',
  };
  return map[type] || type;
}
