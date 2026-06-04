import React from 'react';
import { useEditorStore } from '../../stores/editorStore';
import { UndoRedoToolbar } from '../Shared/UndoRedoToolbar';
import { ValidationPanel } from '../Validation/ValidationPanel';
import type { Issue } from '../../core/validation/rules';

interface EditorLayoutProps {
  children: React.ReactNode;
  sidebar: React.ReactNode;
  map: React.ReactNode;
  validationIssues?: Issue[];
}

export const EditorLayout: React.FC<EditorLayoutProps> = ({
  children,
  sidebar,
  map,
  validationIssues = []
}) => {
  const { mode, currentDay, hasChanges } = useEditorStore();
  
  return (
    <div className="h-screen flex flex-col">
      <header className="h-14 border-b bg-white flex items-center justify-between px-4">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold">
            {mode === 'day' ? `第${(currentDay || 0) + 1}天编辑` : '行程编辑器'}
          </h1>
          
          {hasChanges && (
            <span className="px-2 py-0.5 text-xs bg-yellow-100 text-yellow-700 rounded">
              已修改
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-4">
          <UndoRedoToolbar />
          
          {mode === 'day' && (
            <button
              onClick={() => useEditorStore.getState().exitDayEditMode()}
              className="px-4 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              退出编辑
            </button>
          )}
        </div>
      </header>
      
      <div className="flex-1 flex overflow-hidden">
        <aside className="w-80 border-r bg-white overflow-y-auto">
          {sidebar}
        </aside>
        
        <main className="flex-1 relative">
          {map}
        </main>
        
        {validationIssues.length > 0 && (
          <aside className="w-72 border-l bg-white p-4 overflow-y-auto">
            <ValidationPanel issues={validationIssues} />
          </aside>
        )}
      </div>
    </div>
  );
};
