import { useMemo } from 'react';
import { useEditorStore } from '../stores/editorStore';
import { useItineraryStore } from '../stores/itineraryStore';
import { validateDay, type Issue } from '../core/validation/rules';

export function useValidation() {
  const { mode, currentDay } = useEditorStore();
  const { days } = useItineraryStore();
  
  const currentDayData = useMemo(() => {
    if (mode === 'day' && currentDay !== null) {
      return days[currentDay];
    }
    return null;
  }, [mode, currentDay, days]);
  
  const issues = useMemo(() => {
    if (!currentDayData) return [];
    return validateDay(currentDayData);
  }, [currentDayData]);
  
  const errorCount = useMemo(() => 
    issues.filter(i => i.severity === 'error').length,
    [issues]
  );
  
  const warningCount = useMemo(() => 
    issues.filter(i => i.severity === 'warning').length,
    [issues]
  );
  
  const hasIssues = issues.length > 0;
  const hasErrors = errorCount > 0;
  
  return {
    issues,
    errorCount,
    warningCount,
    hasIssues,
    hasErrors
  };
}
