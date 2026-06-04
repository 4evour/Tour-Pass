import { create } from 'zustand';
import { Command } from '../core/commands/Command';

interface HistoryState {
  undoStack: Command[];
  redoStack: Command[];
  
  execute: (command: Command) => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
  getUndoDescription: () => string | null;
  getRedoDescription: () => string | null;
  clear: () => void;
}

export const useHistoryStore = create<HistoryState>((set, get) => ({
  undoStack: [],
  redoStack: [],
  
  execute: (command: Command) => {
    command.execute();
    set(state => ({
      undoStack: [...state.undoStack, command],
      redoStack: []
    }));
  },
  
  undo: () => {
    const { undoStack, redoStack } = get();
    if (undoStack.length === 0) return;
    
    const command = undoStack[undoStack.length - 1];
    command.undo();
    
    set({
      undoStack: undoStack.slice(0, -1),
      redoStack: [...redoStack, command]
    });
  },
  
  redo: () => {
    const { undoStack, redoStack } = get();
    if (redoStack.length === 0) return;
    
    const command = redoStack[redoStack.length - 1];
    command.execute();
    
    set({
      undoStack: [...undoStack, command],
      redoStack: redoStack.slice(0, -1)
    });
  },
  
  canUndo: () => get().undoStack.length > 0,
  canRedo: () => get().redoStack.length > 0,
  
  getUndoDescription: () => {
    const { undoStack } = get();
    return undoStack.length > 0 ? undoStack[undoStack.length - 1].description : null;
  },
  
  getRedoDescription: () => {
    const { redoStack } = get();
    return redoStack.length > 0 ? redoStack[redoStack.length - 1].description : null;
  },
  
  clear: () => set({ undoStack: [], redoStack: [] })
}));
