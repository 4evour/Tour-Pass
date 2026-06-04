import React, { useState } from 'react';
import type { DayPlan } from '../../types';

interface Version {
  id: string;
  name: string;
  createdAt: Date;
  createdBy: string;
  description?: string;
  snapshot: DayPlan[];
}

interface VersionManagerProps {
  versions: Version[];
  currentVersion: Version | null;
  onSaveVersion: (name: string, description?: string) => void;
  onRestoreVersion: (id: string) => void;
  onDeleteVersion: (id: string) => void;
}

export const VersionManager: React.FC<VersionManagerProps> = ({
  versions,
  currentVersion,
  onSaveVersion,
  onRestoreVersion,
  onDeleteVersion,
}) => {
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [versionName, setVersionName] = useState('');
  const [versionDescription, setVersionDescription] = useState('');
  
  const handleSave = () => {
    if (versionName.trim()) {
      onSaveVersion(versionName, versionDescription);
      setVersionName('');
      setVersionDescription('');
      setShowSaveDialog(false);
    }
  };
  
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="font-medium text-gray-700">版本管理</h4>
        <button
          onClick={() => setShowSaveDialog(true)}
          className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          保存版本
        </button>
      </div>
      
      {/* 保存对话框 */}
      {showSaveDialog && (
        <div className="p-4 border rounded-lg bg-gray-50">
          <div className="space-y-3">
            <input
              type="text"
              value={versionName}
              onChange={(e) => setVersionName(e.target.value)}
              placeholder="版本名称"
              className="w-full px-3 py-2 border rounded"
            />
            <textarea
              value={versionDescription}
              onChange={(e) => setVersionDescription(e.target.value)}
              placeholder="版本描述（可选）"
              className="w-full px-3 py-2 border rounded resize-none"
              rows={2}
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowSaveDialog(false)}
                className="px-3 py-1.5 text-sm bg-gray-100 rounded hover:bg-gray-200"
              >
                取消
              </button>
              <button
                onClick={handleSave}
                className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* 版本列表 */}
      <div className="space-y-2">
        {versions.map((version) => (
          <div
            key={version.id}
            className={`p-3 border rounded ${
              currentVersion?.id === version.id ? 'border-blue-500 bg-blue-50' : ''
            }`}
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{version.name}</div>
                <div className="text-sm text-gray-500">
                  {formatDate(version.createdAt)} · {version.createdBy}
                </div>
                {version.description && (
                  <div className="text-sm text-gray-600 mt-1">{version.description}</div>
                )}
              </div>
              
              <div className="flex gap-2">
                {currentVersion?.id !== version.id && (
                  <>
                    <button
                      onClick={() => onRestoreVersion(version.id)}
                      className="text-sm text-blue-500 hover:text-blue-700"
                    >
                      恢复
                    </button>
                    <button
                      onClick={() => onDeleteVersion(version.id)}
                      className="text-sm text-red-500 hover:text-red-700"
                    >
                      删除
                    </button>
                  </>
                )}
                {currentVersion?.id === version.id && (
                  <span className="text-sm text-blue-600">当前版本</span>
                )}
              </div>
            </div>
          </div>
        ))}
        
        {versions.length === 0 && (
          <p className="text-center text-gray-400 text-sm py-4">
            暂无保存的版本
          </p>
        )}
      </div>
    </div>
  );
};

function formatDate(date: Date): string {
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
