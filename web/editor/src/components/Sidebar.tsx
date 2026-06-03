import { useState, useMemo } from 'react';
import { useDraggable } from '@dnd-kit/core';
import type { Poi, PoiTypeFilter } from '../types';
import PoiCard from './PoiCard';

const FILTERS: { key: PoiTypeFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'attraction', label: '景点' },
  { key: 'restaurant', label: '餐饮' },
  { key: 'nightlife', label: '夜生活' },
];

interface SidebarProps {
  pois: Poi[];
}

export default function Sidebar({ pois }: SidebarProps) {
  const [filter, setFilter] = useState<PoiTypeFilter>('all');
  const [search, setSearch] = useState('');
  const [showCount, setShowCount] = useState(50);

  const filtered = useMemo(() => {
    let list = pois;
    if (filter !== 'all') list = list.filter(p => p.type === filter);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(p => p.name.toLowerCase().includes(q) || p.area.toLowerCase().includes(q));
    }
    return list;
  }, [pois, filter, search]);

  const visiblePois = filtered.slice(0, showCount);
  const hasMore = filtered.length > showCount;

  return (
    <div className="flex flex-col h-full bg-gray-50 border-r">
      <div className="p-3 border-b bg-white">
        <h2 className="text-sm font-semibold text-gray-700 mb-2">POI 列表</h2>
        <input
          value={search}
          onChange={e => { setSearch(e.target.value); setShowCount(50); }}
          placeholder="搜索景点..."
          className="w-full px-3 py-1.5 border rounded-lg text-sm mb-2"
        />
        <div className="flex gap-1 flex-wrap">
          {FILTERS.map(f => (
            <button
              key={f.key}
              onClick={() => { setFilter(f.key); setShowCount(50); }}
              className={`px-2 py-1 rounded text-xs ${filter === f.key ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {visiblePois.map(poi => (
          <DraggablePoiCard key={poi.id} poi={poi} />
        ))}
        {hasMore && (
          <button
            onClick={() => setShowCount(c => c + 50)}
            className="w-full py-2 text-xs text-primary-600 hover:text-primary-800 hover:bg-primary-50 rounded"
          >
            加载更多 ({filtered.length - showCount} 个剩余)
          </button>
        )}
        {filtered.length === 0 && (
          <div className="text-sm text-gray-400 text-center py-4">无匹配结果</div>
        )}
      </div>
      <div className="p-2 border-t bg-white text-xs text-gray-500 text-center">
        显示 {visiblePois.length}/{filtered.length} · 共 {pois.length} 个 POI
      </div>
    </div>
  );
}

function DraggablePoiCard({ poi }: { poi: Poi }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `sidebar-${poi.id}`,
    data: { poi, variant: 'sidebar' },
  });

  return (
    <div ref={setNodeRef} {...attributes} {...listeners} style={{ opacity: isDragging ? 0.5 : 1 }}>
      <PoiCard poi={poi} variant="sidebar" />
    </div>
  );
}
