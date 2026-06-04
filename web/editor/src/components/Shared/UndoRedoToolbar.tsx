import React from 'react';
import { useHistoryStore } from '../../stores/historyStore';

export const UndoRedoToolbar: React.FC = () => {
  const { canUndo, canRedo, undo, redo, getUndoDescription, getRedoDescription } = useHistoryStore();
  
  const handleUndo = () => {
    if (canUndo()) {
      undo();
    }
  };
  
  const handleRedo = () => {
    if (canRedo()) {
      redo();
    }
  };
  
  return (
    <div className="flex gap-2">
      <button
        onClick={handleUndo}
        disabled={!canUndo()}
        className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed rounded"
        title={getUndoDescription() || '撤销'}
      >
        撤销
      </button>
      <button
        onClick={handleRedo}
        disabled={!canRedo()}
        className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed rounded"
        title={getRedoDescription() || '重做'}
      >
        重做
      </button>
    </div>
  );
};
