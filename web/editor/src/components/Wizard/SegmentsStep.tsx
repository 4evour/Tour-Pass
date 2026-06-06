import React, { useState } from 'react';
import { useItineraryStore } from '../../stores/itineraryStore';
import type { CitySegment } from '../../types';

const TRANSPORT_OPTIONS = [
  { value: 'train', label: '🚄 高铁/火车', icon: '🚄' },
  { value: 'flight', label: '✈️ 飞机', icon: '✈️' },
  { value: 'bus', label: '🚌 大巴', icon: '🚌' },
  { value: 'car', label: '🚗 自驾', icon: '🚗' },
  { value: 'other', label: '🔄 其他', icon: '🔄' },
];

export const SegmentsStep: React.FC = () => {
  const { cities, citySegments, setCitySegments, setWizardStep } = useItineraryStore();
  
  // Generate default segments from city list
  const defaultSegments: CitySegment[] = [];
  for (let i = 0; i < cities.length - 1; i++) {
    const existing = citySegments.find(s => s.fromCity === cities[i] && s.toCity === cities[i + 1]);
    defaultSegments.push(existing || {
      id: `seg-${i}`,
      fromCity: cities[i],
      toCity: cities[i + 1],
      departTime: '09:00',
      arriveTime: '12:00',
      transport: 'train',
      note: '',
    });
  }
  
  const [segments, setSegments] = useState<CitySegment[]>(defaultSegments);

  const updateSegment = (idx: number, field: keyof CitySegment, value: string) => {
    const updated = [...segments];
    updated[idx] = { ...updated[idx], [field]: value };
    setSegments(updated);
  };

  const handleNext = () => {
    setCitySegments(segments);
    setWizardStep('hotels');
  };

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h2 className="text-2xl font-bold mb-2">配置跨城交通</h2>
      <p className="text-gray-500 mb-6">设置每段城际交通的出发/到达时间和方式</p>
      
      <div className="space-y-4 mb-6">
        {segments.map((seg, idx) => (
          <div key={seg.id} className="p-4 bg-white border rounded-lg shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <span className="font-bold text-lg">{seg.fromCity}</span>
              <span className="text-gray-400">→</span>
              <span className="font-bold text-lg">{seg.toCity}</span>
            </div>
            
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label className="block text-sm text-gray-500 mb-1">出发时间</label>
                <input
                  type="time"
                  value={seg.departTime}
                  onChange={(e) => updateSegment(idx, 'departTime', e.target.value)}
                  className="w-full px-3 py-2 border rounded"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">到达时间</label>
                <input
                  type="time"
                  value={seg.arriveTime}
                  onChange={(e) => updateSegment(idx, 'arriveTime', e.target.value)}
                  className="w-full px-3 py-2 border rounded"
                />
              </div>
            </div>
            
            <div className="mb-3">
              <label className="block text-sm text-gray-500 mb-1">交通方式</label>
              <div className="flex gap-2 flex-wrap">
                {TRANSPORT_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => updateSegment(idx, 'transport', opt.value)}
                    className={`px-3 py-1.5 rounded text-sm ${
                      seg.transport === opt.value
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-100 hover:bg-gray-200'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            
            <div>
              <label className="block text-sm text-gray-500 mb-1">备注</label>
              <input
                type="text"
                value={seg.note}
                onChange={(e) => updateSegment(idx, 'note', e.target.value)}
                placeholder="可选：车次号、航班号等"
                className="w-full px-3 py-2 border rounded"
              />
            </div>
          </div>
        ))}
      </div>
      
      <div className="flex gap-3">
        <button
          onClick={() => setWizardStep('cities')}
          className="px-6 py-3 bg-gray-200 rounded-lg hover:bg-gray-300"
        >
          ← 上一步
        </button>
        <button
          onClick={handleNext}
          className="flex-1 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
        >
          下一步：选择酒店 →
        </button>
      </div>
    </div>
  );
};
