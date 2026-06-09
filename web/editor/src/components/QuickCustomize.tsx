import { useState } from 'react';

interface Props {
  itinerary: Record<string, unknown>;
  onCustomize: (message: string) => void;
  onClose: () => void;
}

const QUICK_OPTIONS = [
  { label: '加一天', icon: '➕', message: '加一天行程' },
  { label: '换酒店', icon: '🏨', message: '帮我换一个更好的酒店' },
  { label: '加美食', icon: '🍜', message: '加一些当地特色美食推荐' },
  { label: '休闲些', icon: '😴', message: '行程太紧了，安排休闲一些' },
  { label: '加夜游', icon: '🌙', message: '晚上加一些夜景或夜生活安排' },
  { label: '换景点', icon: '🔄', message: '换掉一些热门景点，推荐小众的' },
];

export default function QuickCustomize({ itinerary, onCustomize, onClose }: Props) {
  const [customInput, setCustomInput] = useState('');

  const handleQuickOption = (message: string) => {
    onCustomize(message);
    onClose();
  };

  const handleCustomSubmit = () => {
    if (customInput.trim()) {
      onCustomize(customInput.trim());
      onClose();
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-lg border p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm">快速调整行程</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-sm">✕</button>
      </div>

      {/* Quick options */}
      <div className="grid grid-cols-3 gap-2">
        {QUICK_OPTIONS.map(opt => (
          <button
            key={opt.label}
            onClick={() => handleQuickOption(opt.message)}
            className="flex flex-col items-center gap-1 px-3 py-2.5 border rounded-lg hover:border-primary-500 hover:bg-primary-50 transition-colors"
          >
            <span className="text-lg">{opt.icon}</span>
            <span className="text-xs text-gray-700">{opt.label}</span>
          </button>
        ))}
      </div>

      {/* Custom input */}
      <div className="flex gap-2">
        <input
          value={customInput}
          onChange={e => setCustomInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleCustomSubmit()}
          placeholder="或者输入你的具体需求..."
          className="flex-1 px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        <button
          onClick={handleCustomSubmit}
          disabled={!customInput.trim()}
          className="px-4 py-2 bg-primary-500 text-white rounded-lg text-sm hover:bg-primary-600 disabled:opacity-50"
        >
          调整
        </button>
      </div>
    </div>
  );
}
