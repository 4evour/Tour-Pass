import React from 'react';
import { useItineraryStore } from '../../stores/itineraryStore';
import { useHistoryStore } from '../../stores/historyStore';
import { useEditorStore } from '../../stores/editorStore';
import { RemoveStopCommand } from '../../core/commands/RemoveStopCommand';
import { ReorderCommand } from '../../core/commands/ReorderCommand';

interface DayEditorProps {
  dayIndex: number;
}

export const DayEditor: React.FC<DayEditorProps> = ({ dayIndex }) => {
  const days = useItineraryStore(state => state.days);
  const setDays = useItineraryStore(state => state.setDays);
  const { execute } = useHistoryStore();
  const { markChanged } = useEditorStore();
  
  const day = days[dayIndex];
  if (!day) return null;
  
  const handleRemoveStop = (index: number) => {
    const store = { days, setDays };
    const command = new RemoveStopCommand(store, dayIndex, index);
    execute(command);
    markChanged(`stop-${index}`, command.description);
  };
  
  const handleReorder = (oldIndex: number, newIndex: number) => {
    const store = { days, setDays };
    const command = new ReorderCommand(store, dayIndex, oldIndex, newIndex);
    execute(command);
    markChanged(`stop-${oldIndex}`, command.description);
  };
  
  return (
    <div className="space-y-3">
      <h3 className="font-medium text-gray-700">
        第{dayIndex + 1}天行程
      </h3>
      
      <div className="space-y-2">
        {day.stops.map((stop, index) => (
          <div
            key={stop.id}
            className="p-3 bg-white border rounded-lg flex items-center justify-between"
          >
            <div>
              <span className="text-sm text-gray-500 mr-2">{index + 1}.</span>
              <span className="font-medium">{stop.poi.name}</span>
            </div>
            
            <div className="flex gap-2">
              {index > 0 && (
                <button
                  onClick={() => handleReorder(index, index - 1)}
                  className="text-gray-500 hover:text-gray-700 text-sm"
                >
                  ↑
                </button>
              )}
              {index < day.stops.length - 1 && (
                <button
                  onClick={() => handleReorder(index, index + 1)}
                  className="text-gray-500 hover:text-gray-700 text-sm"
                >
                  ↓
                </button>
              )}
              <button
                onClick={() => handleRemoveStop(index)}
                className="text-red-500 hover:text-red-700 text-sm"
              >
                删除
              </button>
            </div>
          </div>
        ))}
      </div>
      
      {day.stops.length === 0 && (
        <p className="text-gray-500 text-center py-8">
          还没有添加景点，点击地图上的景点添加
        </p>
      )}
    </div>
  );
};
