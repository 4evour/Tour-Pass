import React, { useState } from 'react';

interface Collaborator {
  id: string;
  name: string;
  email: string;
  role: 'owner' | 'editor' | 'viewer';
  avatar?: string;
}

interface CollaboratorManagerProps {
  collaborators: Collaborator[];
  onInvite: (email: string, role: 'editor' | 'viewer') => void;
  onRemove: (id: string) => void;
  onChangeRole: (id: string, role: 'editor' | 'viewer') => void;
}

export const CollaboratorManager: React.FC<CollaboratorManagerProps> = ({
  collaborators,
  onInvite,
  onRemove,
  onChangeRole,
}) => {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'editor' | 'viewer'>('editor');
  
  const handleInvite = () => {
    if (email) {
      onInvite(email, role);
      setEmail('');
    }
  };
  
  return (
    <div className="space-y-4">
      <h4 className="font-medium text-gray-700">协作者管理</h4>
      
      {/* 邀请表单 */}
      <div className="flex gap-2">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="输入邮箱地址"
          className="flex-1 px-3 py-2 border rounded"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as 'editor' | 'viewer')}
          className="px-3 py-2 border rounded"
        >
          <option value="editor">编辑者</option>
          <option value="viewer">查看者</option>
        </select>
        <button
          onClick={handleInvite}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          邀请
        </button>
      </div>
      
      {/* 协作者列表 */}
      <div className="space-y-2">
        {collaborators.map((collaborator) => (
          <div
            key={collaborator.id}
            className="flex items-center justify-between p-3 border rounded"
          >
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center">
                {collaborator.avatar ? (
                  <img
                    src={collaborator.avatar}
                    alt={collaborator.name}
                    className="w-8 h-8 rounded-full"
                  />
                ) : (
                  <span className="text-sm font-medium">
                    {collaborator.name.charAt(0)}
                  </span>
                )}
              </div>
              <div>
                <div className="font-medium">{collaborator.name}</div>
                <div className="text-sm text-gray-500">{collaborator.email}</div>
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              {collaborator.role !== 'owner' && (
                <>
                  <select
                    value={collaborator.role}
                    onChange={(e) => onChangeRole(collaborator.id, e.target.value as 'editor' | 'viewer')}
                    className="px-2 py-1 text-sm border rounded"
                  >
                    <option value="editor">编辑者</option>
                    <option value="viewer">查看者</option>
                  </select>
                  <button
                    onClick={() => onRemove(collaborator.id)}
                    className="text-sm text-red-500 hover:text-red-700"
                  >
                    移除
                  </button>
                </>
              )}
              {collaborator.role === 'owner' && (
                <span className="px-2 py-1 text-sm bg-blue-100 text-blue-700 rounded">
                  所有者
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
