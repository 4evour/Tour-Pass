import React from 'react';
import type { Issue } from '../../core/validation/rules';

interface ValidationPanelProps {
  issues: Issue[];
}

export const ValidationPanel: React.FC<ValidationPanelProps> = ({ issues }) => {
  const errors = issues.filter(i => i.severity === 'error');
  const warnings = issues.filter(i => i.severity === 'warning');
  
  if (issues.length === 0) {
    return (
      <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
        <div className="flex items-center gap-2">
          <span className="text-green-500">✓</span>
          <span className="text-green-700 font-medium">行程安排合理</span>
        </div>
      </div>
    );
  }
  
  return (
    <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-red-500">⚠</span>
        <span className="text-red-700 font-medium">
          {errors.length > 0 && `${errors.length} 个错误`}
          {errors.length > 0 && warnings.length > 0 && '，'}
          {warnings.length > 0 && `${warnings.length} 个警告`}
        </span>
      </div>
      
      <ul className="space-y-2">
        {issues.map((issue, index) => (
          <li 
            key={index}
            className={`text-sm ${
              issue.severity === 'error' ? 'text-red-600' : 'text-yellow-600'
            }`}
          >
            • {issue.message}
          </li>
        ))}
      </ul>
    </div>
  );
};
