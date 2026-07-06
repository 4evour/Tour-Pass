import { useState, useRef, useEffect, useCallback } from 'react';
import AgentToolStatus from './AgentToolStatus';
import StreamingItinerary from './StreamingItinerary';

interface AgentEvent {
  type: string;
  content?: string;
  intent?: Record<string, unknown>;
  hotel?: Record<string, unknown>;
  day_plan?: { day: number; stops: unknown[] };
  itinerary?: Record<string, unknown>;
  [key: string]: unknown;
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  events?: AgentEvent[];
  itinerary?: Record<string, unknown>;
}

interface Props {
  city: string;
  onItineraryGenerated?: (itinerary: Record<string, unknown>) => void;
}

export default function AgentChat({ city, onItineraryGenerated }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: '你好！我是 Tour Pass AI 旅行规划师。告诉我你想去哪里玩，比如“带父母去长沙3天，想去岳麓山和橘子洲”，我来帮你规划行程。',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [currentEvents, setCurrentEvents] = useState<AgentEvent[]>([]);
  const [currentItinerary, setCurrentItinerary] = useState<Record<string, unknown> | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(
    sessionStorage.getItem('tp_session_id')
  );
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, currentEvents]);

  const sendPlanRequest = useCallback(async (message: string) => {
    setLoading(true);
    setCurrentEvents([]);
    setCurrentItinerary(null);

    const userMsg: Message = { role: 'user', content: message };
    setMessages(prev => [...prev, userMsg]);

    try {
      const res = await fetch('/agent/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error('No reader');

      const decoder = new TextDecoder();
      let buffer = '';
      const events: AgentEvent[] = [];
      let finalItinerary: Record<string, unknown> | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            continue;
          }
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6)) as AgentEvent;
              events.push(data);
              setCurrentEvents([...events]);

              // Capture session_id for multi-turn
              if (data.session_id) {
                setSessionId(data.session_id as string);
                sessionStorage.setItem('tp_session_id', data.session_id as string);
              }
              // Backend sends type: "itinerary" for the final result
              if (data.type === 'itinerary' || data.type === 'itinerary_complete' || data.type === 'cache_hit') {
                finalItinerary = (data as any).itinerary || null;
                setCurrentItinerary(finalItinerary);
              }
            } catch {
              // Skip malformed JSON
            }
          }
        }
      }

      const summary = finalItinerary?.summary as string || '行程已生成！';
      const assistantMsg: Message = {
        role: 'assistant',
        content: summary,
        events,
        itinerary: finalItinerary || undefined,
      };
      setMessages(prev => [...prev, assistantMsg]);

      if (finalItinerary && onItineraryGenerated) {
        onItineraryGenerated(finalItinerary);
      }
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `抱歉，生成失败：${err instanceof Error ? err.message : '未知错误'}` },
      ]);
    } finally {
      setLoading(false);
      setCurrentEvents([]);
    }
  }, [onItineraryGenerated]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const msg = input.trim();
    setInput('');

    if (currentItinerary && isModificationRequest(msg)) {
      await sendChatMessage(msg);
    } else {
      await sendPlanRequest(msg);
    }
  };

  const sendChatMessage = async (message: string) => {
    setLoading(true);
    const userMsg: Message = { role: 'user', content: message };
    setMessages(prev => [...prev, userMsg]);

    try {
      const res = await fetch('/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          itinerary: currentItinerary,
          history: messages.slice(-10).map(m => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await res.json();

      // Update session_id if returned
      if (data.session_id && !sessionId) {
        setSessionId(data.session_id);
        sessionStorage.setItem('tp_session_id', data.session_id);
      }

      const reply = data.reply || '抱歉，我无法理解。';
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: reply },
      ]);

      // If the chat returned a modification action, apply it
      if (data.action && sessionId) {
        await applyModification(data.action, message);
      }
    } catch {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: '网络错误，请稍后重试。' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const applyModification = async (action: Record<string, unknown>, message: string) => {
    if (!sessionId) return;
    try {
      const token = localStorage.getItem('tp_token');
      const res = await fetch('/agent/modify', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          session_id: sessionId,
          action: action.action,
          day: action.day,
          poi_id: action.poi_id,
          new_poi_name: action.new_poi_name,
          new_start_minutes: action.new_start_minutes,
          new_pace: action.new_pace,
          message,
        }),
      });
      const data = await res.json();
      if (data.status === 'ok' && data.itinerary) {
        setCurrentItinerary(data.itinerary);
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: '✅ 行程已更新！' },
        ]);
        if (onItineraryGenerated) {
          onItineraryGenerated(data.itinerary);
        }
      }
    } catch (err) {
      console.error('Modification failed:', err);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-xl shadow-lg border">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-t-xl">
        <span className="text-lg">🗺️</span>
        <span className="font-semibold">AI 旅行规划师</span>
        {loading && <span className="text-xs opacity-70 ml-2">生成中...</span>}
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                msg.role === 'user'
                  ? 'bg-primary-500 text-white'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              <div className="whitespace-pre-wrap">{msg.content}</div>
              {msg.itinerary && (
                <div className="mt-3">
                  <StreamingItinerary itinerary={msg.itinerary as any} />
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Streaming status */}
        {loading && currentEvents.length > 0 && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-2xl px-4 py-3 bg-blue-50 border border-blue-200">
              <AgentToolStatus events={currentEvents} />
            </div>
          </div>
        )}

        {loading && currentEvents.length === 0 && (
          <div className="flex justify-start">
            <div className="rounded-2xl px-4 py-3 bg-gray-100 text-sm text-gray-500">
              <span className="animate-pulse">正在连接 AI 规划师...</span>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-3 border-t">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
            placeholder="描述你的旅行需求，如：去成都4天，重点吃美食..."
            className="flex-1 px-4 py-2.5 border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="px-5 py-2.5 bg-primary-500 text-white rounded-xl text-sm font-medium hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? '⏳' : '发送'}
          </button>
        </div>
        <div className="mt-1.5 text-xs text-gray-400 px-1">
          试试：&ldquo;带老人去长沙3天&rdquo; &bull; &ldquo;穷游成都5天吃火锅&rdquo; &bull; &ldquo;情侣杭州2天文艺游&rdquo;
        </div>
      </div>
    </div>
  );
}

function isModificationRequest(msg: string): boolean {
  const keywords = ['换', '改', '不要', '去掉', '换成', '加', '增加', '调整', '修改'];
  return keywords.some(kw => msg.includes(kw));
}
