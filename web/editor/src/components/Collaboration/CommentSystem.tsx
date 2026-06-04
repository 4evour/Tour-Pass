import React, { useState } from 'react';

interface Comment {
  id: string;
  userId: string;
  userName: string;
  content: string;
  createdAt: Date;
  stopId?: string;
}

interface CommentSystemProps {
  comments: Comment[];
  onAddComment: (content: string, stopId?: string) => void;
  onDeleteComment: (id: string) => void;
  currentUserId: string;
}

export const CommentSystem: React.FC<CommentSystemProps> = ({
  comments,
  onAddComment,
  onDeleteComment,
  currentUserId,
}) => {
  const [newComment, setNewComment] = useState('');
  
  const handleSubmit = () => {
    if (newComment.trim()) {
      onAddComment(newComment);
      setNewComment('');
    }
  };
  
  return (
    <div className="space-y-4">
      <h4 className="font-medium text-gray-700">评论</h4>
      
      {/* 评论输入 */}
      <div className="flex gap-2">
        <textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="添加评论..."
          className="flex-1 px-3 py-2 border rounded resize-none"
          rows={2}
        />
        <button
          onClick={handleSubmit}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 self-end"
        >
          发送
        </button>
      </div>
      
      {/* 评论列表 */}
      <div className="space-y-3">
        {comments.map((comment) => (
          <div key={comment.id} className="p-3 bg-gray-50 rounded">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm">{comment.userName}</span>
                <span className="text-xs text-gray-400">
                  {formatDate(comment.createdAt)}
                </span>
              </div>
              {comment.userId === currentUserId && (
                <button
                  onClick={() => onDeleteComment(comment.id)}
                  className="text-xs text-red-500 hover:text-red-700"
                >
                  删除
                </button>
              )}
            </div>
            <p className="text-sm text-gray-700">{comment.content}</p>
          </div>
        ))}
        
        {comments.length === 0 && (
          <p className="text-center text-gray-400 text-sm py-4">
            暂无评论
          </p>
        )}
      </div>
    </div>
  );
};

function formatDate(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  
  const days = Math.floor(hours / 24);
  return `${days}天前`;
}
