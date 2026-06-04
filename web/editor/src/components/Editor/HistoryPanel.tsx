import React from 'react';
import { useHistoryStore } from '../../stores/historyStore';

interface HistoryPanelProps {
  maxItems?: number;
}

export const HistoryPanel: React.FC<HistoryPanelProps> = ({ maxItems = 20 }) => {
  const { undoStack, redoStack, undo, redo, canUndo, canRedo } = useHistoryStore();
  
  const allItems = [
    ...undoStack.map((cmd, i) => ({
      command: cmd,
      index: i,
      type: 'undo' as const,
    })),
    ...redoStack.map((cmd, i) => ({
      command: cmd,
      index: i,
      type: 'redo' as const,
    })),
  ].reverse().slice(0, maxItems);
  
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-gray-700">编辑历史</h3>
        <div className="flex gap-2">
          <button
            onClick={undo}
            disabled={!canUndo()}
            className="px-2 py-1 text-sm bg-gray-100 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed rounded"
          >
            撤销
          </button>
          <button
            onClick={redo}
            disabled={!canRedo()}
            className="px-2 py-1 text-sm bg-gray-100 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed rounded"
          >
            重做
          </button>
        </div>
      </div>
      
      <div className="space-y-1">
        {allItems.map((item, i) => (
          <div
            key={i}
            className={`p-2 text-sm rounded ${
              item.type === 'undo'
                ? 'bg-white border border-gray-200'
                : 'bg-gray-50 border border-dashed border-gray-300'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className={item.type === 'redo' ? 'text-gray-400' : 'text-gray-700'}>
                {item.command.description}
              </span>
              <span className="text-xs text-gray-400">
                {item.type === 'redo' ? '已撤销' : ''}
              </span>
            </div>
          </div>
        ))}
        
        {allItems.length === 0 && (
          <p className="text-gray-400 text-center py-4 text-sm">
            暂无编辑历史
          </p>
        )}
      </div>
    </div>
  );
};
