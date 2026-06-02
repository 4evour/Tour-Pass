import { useState, useRef, useEffect } from 'react';

interface InlineTimeEditorProps {
  value: number; // minutes from midnight
  onChange: (minutes: number) => void;
  className?: string;
}

function formatMin(m: number): string {
  const h = Math.floor(m / 60);
  const min = m % 60;
  return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}

function parseTime(str: string): number {
  const [h, m] = str.split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
}

export function InlineTimeDisplay({ value, onChange, className }: InlineTimeEditorProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(formatMin(value));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  useEffect(() => {
    if (!editing) setDraft(formatMin(value));
  }, [value, editing]);

  const commit = () => {
    const mins = parseTime(draft);
    if (mins >= 0 && mins < 24 * 60) {
      onChange(mins);
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="time"
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false); }}
        className={`w-16 px-1 py-0 text-xs border rounded ${className || ''}`}
      />
    );
  }

  return (
    <span
      onClick={() => setEditing(true)}
      className={`cursor-pointer hover:bg-primary-100 px-1 rounded ${className || ''}`}
      title="点击编辑时间"
    >
      {formatMin(value)}
    </span>
  );
}

interface DurationEditorProps {
  value: number; // minutes
  onChange: (minutes: number) => void;
  className?: string;
}

const DURATION_PRESETS = [30, 45, 60, 90, 120, 180];

export function InlineDurationEditor({ value, onChange, className }: DurationEditorProps) {
  const [showPicker, setShowPicker] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setShowPicker(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} className="relative inline-block">
      <span
        onClick={() => setShowPicker(!showPicker)}
        className={`cursor-pointer hover:bg-primary-100 px-1 rounded text-xs text-gray-500 ${className || ''}`}
        title="点击调整时长"
      >
        {value}分
      </span>
      {showPicker && (
        <div className="absolute bottom-full left-0 mb-1 bg-white border rounded-lg shadow-lg z-50 p-2">
          <div className="flex flex-wrap gap-1 w-40">
            {DURATION_PRESETS.map(d => (
              <button
                key={d}
                onClick={() => { onChange(d); setShowPicker(false); }}
                className={`px-2 py-1 text-xs rounded ${d === value ? 'bg-primary-500 text-white' : 'bg-gray-100 hover:bg-primary-100'}`}
              >
                {d}分
              </button>
            ))}
          </div>
          <div className="mt-1 flex items-center gap-1">
            <input
              type="number"
              min={15}
              max={480}
              step={15}
              defaultValue={value}
              className="w-16 px-1 py-0.5 text-xs border rounded"
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  onChange(parseInt((e.target as HTMLInputElement).value) || 60);
                  setShowPicker(false);
                }
              }}
            />
            <span className="text-xs text-gray-400">分钟</span>
          </div>
        </div>
      )}
    </div>
  );
}
