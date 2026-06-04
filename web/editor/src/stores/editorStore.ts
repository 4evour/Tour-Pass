import { create } from 'zustand';

interface EditorState {
  mode: 'global' | 'day';
  currentDay: number | null;
  isEditing: boolean;
  changedItems: Map<string, string>;
  hasChanges: boolean;
  
  enterDayEditMode: (day: number) => void;
  exitDayEditMode: () => void;
  markChanged: (itemId: string, description: string) => void;
  clearChanges: () => void;
  reset: () => void;
}

const initialState = {
  mode: 'global' as const,
  currentDay: null,
  isEditing: false,
  changedItems: new Map<string, string>(),
  hasChanges: false
};

export const useEditorStore = create<EditorState>((set) => ({
  ...initialState,
  
  enterDayEditMode: (day: number) => {
    set({
      mode: 'day',
      currentDay: day,
      isEditing: true
    });
  },
  
  exitDayEditMode: () => {
    set({
      mode: 'global',
      currentDay: null,
      isEditing: false,
      changedItems: new Map(),
      hasChanges: false
    });
  },
  
  markChanged: (itemId: string, description: string) => {
    set(state => {
      const newChangedItems = new Map(state.changedItems);
      newChangedItems.set(itemId, description);
      return {
        changedItems: newChangedItems,
        hasChanges: true
      };
    });
  },
  
  clearChanges: () => {
    set({
      changedItems: new Map(),
      hasChanges: false
    });
  },
  
  reset: () => set(initialState)
}));
