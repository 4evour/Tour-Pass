import { useState } from 'react';
import { useItineraryStore } from '../stores/itineraryStore';
import { api } from '../utils/api';
import { serializeForSave, deserializeTrip } from '../utils/serialize';
import type { Poi } from '../types';

interface EditorToolbarProps {
  allPois: Poi[];
}

export default function EditorToolbar({ allPois }: EditorToolbarProps) {
  const { city, days, setCity, setDays, defaultHotel } = useItineraryStore();
  const [saving, setSaving] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [savedTrips, setSavedTrips] = useState<any[]>([]);
  const [loadingTrips, setLoadingTrips] = useState(false);
  const [toast, setToast] = useState('');

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  };

  const handleSave = async () => {
    const token = localStorage.getItem('tp_token');
    if (!token) {
      showToast('请先在首页登录');
      return;
    }
    setSaving(true);
    try {
      const { title, request, response } = serializeForSave(city, days);
      const result = await api('/trips/save', {
        method: 'POST',
        body: { title, request, response },
      });
      showToast(`已保存 (ID: ${result.id})`);
    } catch (e: any) {
      showToast(`保存失败: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleShare = async () => {
    const token = localStorage.getItem('tp_token');
    if (!token) {
      showToast('请先在首页登录');
      return;
    }
    setSaving(true);
    try {
      // Save first
      const { title, request, response } = serializeForSave(city, days);
      const saveResult = await api('/trips/save', {
        method: 'POST',
        body: { title, request, response },
      });
      // Then share
      const shareResult = await api(`/trips/${saveResult.id}/share`, { method: 'POST' });
      const shareUrl = shareResult.share_url || `/s/${shareResult.share_id}`;
      const fullUrl = `${window.location.origin}${shareUrl}`;
      try {
        await navigator.clipboard.writeText(fullUrl);
        showToast('分享链接已复制到剪贴板');
      } catch {
        showToast(`分享链接: ${fullUrl}`);
      }
    } catch (e: any) {
      showToast(`分享失败: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleLoadTrips = async () => {
    setShowImport(!showImport);
    if (showImport) return;
    const token = localStorage.getItem('tp_token');
    if (!token) {
      showToast('请先在首页登录');
      return;
    }
    setLoadingTrips(true);
    try {
      const result = await api('/trips/list');
      setSavedTrips(result.data || []);
    } catch (e: any) {
      showToast(`加载失败: ${e.message}`);
    } finally {
      setLoadingTrips(false);
    }
  };

  const handleImport = async (tripId: number) => {
    try {
      const trip = await api(`/trips/${tripId}`);
      const respData = typeof trip.response_json === 'string'
        ? JSON.parse(trip.response_json)
        : trip.response_json;
      const result = deserializeTrip(respData, allPois);
      if (result) {
        if (result.city && result.city !== city) {
          setCity(result.city);
        }
        setDays(result.days);
        showToast(`已导入: ${trip.title}`);
        setShowImport(false);
      } else {
        showToast('导入失败: 数据格式不兼容');
      }
    } catch (e: any) {
      showToast(`导入失败: ${e.message}`);
    }
  };

  return (
    <div className="relative">
      <div className="flex items-center gap-2">
        <button
          onClick={handleSave}
          disabled={saving || days.every(d => d.stops.length === 0)}
          className="px-3 py-1 text-xs bg-primary-500 text-white rounded hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? '...' : '💾 保存'}
        </button>
        <button
          onClick={handleShare}
          disabled={saving || days.every(d => d.stops.length === 0)}
          className="px-3 py-1 text-xs bg-white border border-primary-500 text-primary-600 rounded hover:bg-primary-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          🔗 分享
        </button>
        <button
          onClick={handleLoadTrips}
          className="px-3 py-1 text-xs bg-white border text-gray-600 rounded hover:bg-gray-50"
        >
          📥 导入
        </button>
      </div>

      {/* Import modal */}
      {showImport && (
        <div className="absolute top-full right-0 mt-1 w-72 bg-white border rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto">
          <div className="p-2 border-b bg-gray-50 flex items-center justify-between">
            <span className="text-xs font-medium">选择要导入的行程</span>
            <button onClick={() => setShowImport(false)} className="text-gray-400 hover:text-gray-600 text-xs">✕</button>
          </div>
          {loadingTrips ? (
            <div className="p-3 text-xs text-gray-400 text-center">加载中...</div>
          ) : savedTrips.length === 0 ? (
            <div className="p-3 text-xs text-gray-400 text-center">没有已保存的行程</div>
          ) : (
            <div className="divide-y">
              {savedTrips.map((trip: any) => (
                <button
                  key={trip.id}
                  onClick={() => handleImport(trip.id)}
                  className="w-full text-left px-3 py-2 hover:bg-primary-50 text-xs"
                >
                  <div className="font-medium truncate">{trip.title}</div>
                  <div className="text-gray-400 text-xs">{trip.created_at}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-gray-800 text-white text-sm rounded-lg shadow-lg z-[9999]">
          {toast}
        </div>
      )}
    </div>
  );
}
