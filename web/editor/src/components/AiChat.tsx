import { useState } from 'react';
import AgentChat from './AgentChat';
import HotItineraries from './HotItineraries';

interface Props {
  city: string;
}

type ViewMode = 'chat' | 'hot';

export default function AiChat({ city }: Props) {
  const [open, setOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('chat');

  if (!open) {
    return (
      <div className="fixed bottom-4 right-4 z-[1001] flex flex-col items-end gap-2">
        <button
          onClick={() => { setOpen(true); setViewMode('hot'); }}
          className="px-3 py-2 bg-amber-500 text-white rounded-full shadow-lg hover:bg-amber-600 flex items-center gap-1.5 text-sm transition-colors"
        >
          🔥 热门行程
        </button>
        <button
          onClick={() => { setOpen(true); setViewMode('chat'); }}
          className="w-14 h-14 bg-primary-500 text-white rounded-full shadow-lg hover:bg-primary-600 flex items-center justify-center text-xl transition-colors"
        >
          🗺️
        </button>
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-[1001] w-[420px] h-[600px] flex flex-col">
      {/* Tab switcher */}
      <div className="flex gap-1 mb-1">
        <button
          onClick={() => setViewMode('chat')}
          className={`px-3 py-1.5 rounded-t-lg text-xs font-medium transition-colors ${
            viewMode === 'chat'
              ? 'bg-white text-primary-600 shadow-sm'
              : 'bg-white/60 text-gray-500 hover:bg-white/80'
          }`}
        >
          🗺️ AI 规划师
        </button>
        <button
          onClick={() => setViewMode('hot')}
          className={`px-3 py-1.5 rounded-t-lg text-xs font-medium transition-colors ${
            viewMode === 'hot'
              ? 'bg-white text-amber-600 shadow-sm'
              : 'bg-white/60 text-gray-500 hover:bg-white/80'
          }`}
        >
          🔥 热门行程
        </button>
        <div className="flex-1" />
        <button
          onClick={() => setOpen(false)}
          className="px-2 py-1.5 text-gray-400 hover:text-gray-600 text-xs bg-white/60 rounded-t-lg"
        >
          ✕
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden rounded-xl shadow-xl">
        {viewMode === 'chat' ? (
          <AgentChat city={city} />
        ) : (
          <div className="h-full overflow-y-auto bg-white p-4">
            <h3 className="font-semibold text-sm mb-3">🔥 热门行程推荐</h3>
            <HotItineraries />
          </div>
        )}
      </div>
    </div>
  );
}
