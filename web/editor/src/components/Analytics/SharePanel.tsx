import React, { useState } from 'react';
import type { DayPlan, Poi } from '../../types';
import { api } from '../../utils/api';
import { serializeForSave } from '../../utils/serialize';

interface SharePanelProps {
  days: DayPlan[];
  city: string;
  defaultHotel: Poi | null;
}

export const SharePanel: React.FC<SharePanelProps> = ({ days, city, defaultHotel }) => {
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [isCopied, setIsCopied] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  
  const handleGenerateLink = async () => {
    setIsLoading(true);
    
    try {
      const { title, request, response } = serializeForSave(city, days);
      const saved = await api('/trips/save', {
        method: 'POST',
        body: { title, request, response },
      });
      const data = await api(`/trips/${saved.id}/share`, { method: 'POST' });
      const sharePath = data.share_url || `/s/${data.share_id}`;
      setShareUrl(`${window.location.origin}${sharePath}`);
    } catch (error) {
      alert('生成分享链接失败');
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleCopyLink = () => {
    if (shareUrl) {
      navigator.clipboard.writeText(shareUrl);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    }
  };
  
  const handleShareToWeChat = () => {
    // 微信分享需要接入微信 JS-SDK
    alert('微信分享功能开发中');
  };
  
  return (
    <div className="space-y-4">
      <h4 className="font-medium text-gray-700">分享行程</h4>
      
      {!shareUrl ? (
        <button
          onClick={handleGenerateLink}
          disabled={isLoading}
          className="w-full px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
        >
          {isLoading ? '生成中...' : '生成分享链接'}
        </button>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={shareUrl}
              readOnly
              className="flex-1 px-3 py-2 border rounded bg-gray-50"
            />
            <button
              onClick={handleCopyLink}
              className="px-4 py-2 bg-gray-100 rounded hover:bg-gray-200"
            >
              {isCopied ? '已复制' : '复制'}
            </button>
          </div>
          
          <div className="flex gap-2">
            <button
              onClick={handleShareToWeChat}
              className="flex-1 px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600"
            >
              微信分享
            </button>
            <button
              onClick={() => window.open(`https://twitter.com/intent/tweet?url=${encodeURIComponent(shareUrl)}&text=${encodeURIComponent(city + '行程')}`)}
              className="flex-1 px-4 py-2 bg-blue-400 text-white rounded hover:bg-blue-500"
            >
              Twitter
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
