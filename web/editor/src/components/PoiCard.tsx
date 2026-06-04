import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { Poi, Stop } from '../types';
import { InlineTimeDisplay, InlineDurationEditor } from './InlineTimeEditor';
import { useItineraryStore } from '../stores/itineraryStore';

const TYPE_ICONS: Record<string, string> = {
  attraction: '🏛', restaurant: '🍜', hotel: '🏨', nightlife: '🌙', transit: '🚌',
};

interface PoiCardProps {
  poi: Poi;
  variant: 'sidebar' | 'timeline';
  stop?: Stop;
  index?: number;
  day?: number;
  onRemove?: () => void;
}

function formatMin(m: number): string {
  const h = Math.floor(m / 60);
  const min = m % 60;
  return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}

export default function PoiCard({ poi, variant, stop, index, day, onRemove }: PoiCardProps) {
  const updateStopTime = useItineraryStore(s => s.updateStopTime);
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: variant === 'timeline' ? stop?.id || poi.id : `sidebar-${poi.id}`,
    data: { poi, variant, day, index },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  if (variant === 'sidebar') {
    const shortDesc = poi.description && poi.description.length > 10
      ? poi.description.substring(0, 40) + (poi.description.length > 40 ? '...' : '')
      : '';
    return (
      <div
        ref={setNodeRef}
        style={style}
        {...attributes}
        {...listeners}
        title={poi.description || ''}
        className="flex items-center gap-2 px-3 py-2 bg-white rounded-lg border border-gray-200 cursor-grab hover:border-primary-400 hover:shadow-sm active:cursor-grabbing"
      >
        <span className="text-lg">{TYPE_ICONS[poi.type] || '📍'}</span>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{poi.name}</div>
          <div className="text-xs text-gray-500 truncate">{poi.area}{poi.open_minutes != null ? ` · ${formatMin(poi.open_minutes)}-${formatMin(poi.close_minutes || 0)}` : ''}</div>
          {shortDesc && <div className="text-xs text-gray-400 truncate mt-0.5">{shortDesc}</div>}
        </div>
      </div>
    );
  }

  // Timeline variant
  const handleArrivalChange = (minutes: number) => {
    if (day !== undefined && index !== undefined) {
      updateStopTime(day, index, 'arrival', minutes);
    }
  };

  const handleDurationChange = (minutes: number) => {
    if (day !== undefined && index !== undefined) {
      updateStopTime(day, index, 'duration', minutes);
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      className={`flex items-center gap-2 px-3 py-2 bg-white rounded-lg border cursor-grab active:cursor-grabbing ${isDragging ? 'border-primary-500 shadow-lg' : 'border-gray-200 hover:border-primary-300'}`}
    >
      <div {...listeners} className="text-gray-400 cursor-grab">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="8" cy="6" r="1.5"/><circle cx="16" cy="6" r="1.5"/><circle cx="8" cy="12" r="1.5"/><circle cx="16" cy="12" r="1.5"/><circle cx="8" cy="18" r="1.5"/><circle cx="16" cy="18" r="1.5"/></svg>
      </div>
      {index !== undefined && (
        <div className="w-6 h-6 rounded-full bg-primary-500 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">
          {index + 1}
        </div>
      )}
      <span className="text-lg flex-shrink-0">{TYPE_ICONS[poi.type] || '📍'}</span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{poi.name}</div>
        {stop && (
          <div className="text-xs text-gray-500">
            <InlineTimeDisplay value={stop.arrival} onChange={handleArrivalChange} />
            {' - '}
            <InlineTimeDisplay value={stop.departure} onChange={(v) => {
              // Changing departure = changing duration
              const newDuration = v - stop.arrival;
              if (newDuration >= 15) handleDurationChange(newDuration);
            }} />
            {' · '}
            <InlineDurationEditor value={stop.poi.visit_duration || 60} onChange={handleDurationChange} />
            {stop.travelMinutes > 0 && <span className="text-gray-400"> · 🚶 {stop.travelMinutes}分</span>}
          </div>
        )}
      </div>
      {onRemove && (
        <button onClick={onRemove} className="text-gray-400 hover:text-red-500 flex-shrink-0">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      )}
    </div>
  );
}
