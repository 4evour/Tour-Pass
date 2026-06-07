import React, { useState, useEffect } from 'react';
import { useItineraryStore } from '../../stores/itineraryStore';

const CITY_EMOJI_MAP: Record<string, string> = {
  "武汉": "🌉", "大理": "🏔️", "丽江": "🏘️", "南京": "🏛️", "苏州": "🏡",
  "北京": "🏯", "成都": "🐼", "重庆": "🔥", "杭州": "🌊", "西安": "🏛️",
  "上海": "🌃", "广州": "🌺", "深圳": "💎", "厦门": "🏖️", "青岛": "🍺",
  "桂林": "🏞️", "三亚": "🌊", "哈尔滨": "❄️", "昆明": "🌸", "张家界": "🏔️", "长沙": "🏙️",
};

const FALLBACK_CITY_OPTIONS = [
  { name: '武汉', emoji: '🌉' },
  { name: '大理', emoji: '🏔️' },
  { name: '丽江', emoji: '🏘️' },
  { name: '南京', emoji: '🏛️' },
  { name: '苏州', emoji: '🏡' },
  { name: '北京', emoji: '🏯' },
  { name: '成都', emoji: '🐼' },
  { name: '重庆', emoji: '🔥' },
  { name: '杭州', emoji: '🌊' },
  { name: '西安', emoji: '🏛️' },
  { name: '上海', emoji: '🌃' },
  { name: '广州', emoji: '🌺' },
  { name: '深圳', emoji: '💎' },
  { name: '厦门', emoji: '🏖️' },
  { name: '青岛', emoji: '🍺' },
  { name: '桂林', emoji: '🏞️' },
  { name: '三亚', emoji: '🌊' },
  { name: '哈尔滨', emoji: '❄️' },
  { name: '昆明', emoji: '🌸' },
  { name: '张家界', emoji: '🏔️' },
  { name: '长沙', emoji: '🏙️' },
];

export const CitiesStep: React.FC = () => {
  const { cities, setCities, totalDays, setWizardStep } = useItineraryStore();
  const [selected, setSelected] = useState<string[]>([]);
  const [availableCities, setAvailableCities] = useState<{ name: string; emoji: string }[]>(FALLBACK_CITY_OPTIONS);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    fetch('/cities')
      .then(r => r.json())
      .then(data => {
        if (cancelled) return;
        const apiCities: { name: string }[] = data.cities || [];
        const mapped = apiCities.map(city => ({
          name: city.name,
          emoji: CITY_EMOJI_MAP[city.name] || '🗺️',
        }));
        setAvailableCities(mapped.length > 0 ? mapped : FALLBACK_CITY_OPTIONS);
      })
      .catch(() => {
        if (!cancelled) setAvailableCities(FALLBACK_CITY_OPTIONS);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, []);

  const toggleCity = (city: string) => {
    setSelected(prev => 
      prev.includes(city) ? prev.filter(c => c !== city) : [...prev, city]
    );
  };

  const handleNext = () => {
    if (selected.length === 0) return;
    setCities(selected);
    setWizardStep(selected.length > 1 ? 'segments' : 'hotels');
  };

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h2 className="text-2xl font-bold mb-2">选择城市</h2>
      <p className="text-gray-500 mb-6">
        你的 {totalDays} 天旅行要去哪些城市？可多选，顺序代表行程顺序
      </p>
      
      <div className="grid grid-cols-3 gap-3 mb-6">
        {loading ? (
          <div className="col-span-3 text-center text-sm text-gray-400 py-6">正在加载城市列表...</div>
        ) : (
          availableCities.map(city => {
            const isSelected = selected.includes(city.name);
            const orderIdx = selected.indexOf(city.name);
            return (
              <button
                key={city.name}
                onClick={() => toggleCity(city.name)}
                className={`relative flex items-center gap-2 p-3 rounded-lg border-2 transition-all ${isSelected ? 'border-blue-500 bg-blue-50 shadow-md' : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'}`}
              >
                <span className="text-xl">{city.emoji}</span>
                <span className="font-medium">{city.name}</span>
                {isSelected && (
                  <span className="absolute -top-2 -right-2 w-6 h-6 bg-blue-500 text-white rounded-full text-xs flex items-center justify-center font-bold">
                    {orderIdx + 1}
                  </span>
                )}
              </button>
            );
          })
        )}
      </div>
      
      {selected.length > 0 && (
        <div className="mb-6 p-4 bg-blue-50 rounded-lg">
          <p className="text-sm text-blue-700">
            行程路线：{selected.map((c, i) => (
              <span key={c}>
                {i > 0 && ' → '}
                <strong>{c}</strong>
              </span>
            ))}
          </p>
        </div>
      )}
      
      <div className="flex gap-3">
        <button
          onClick={() => setWizardStep('days')}
          className="px-6 py-3 bg-gray-200 rounded-lg hover:bg-gray-300"
        >
          ← 上一步
        </button>
        <button
          onClick={handleNext}
          disabled={selected.length === 0}
          className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          {selected.length > 1 ? '下一步：配置跨城 →' : '下一步：选择酒店 →'}
        </button>
      </div>
    </div>
  );
};
