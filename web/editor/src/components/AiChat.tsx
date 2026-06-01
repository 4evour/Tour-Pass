import { useState, useRef, useEffect } from 'react';
import { useItineraryStore } from '../stores/itineraryStore';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function AiChat({ city }: { city: string }) {
  const { days, hotel } = useItineraryStore();
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '你好！我是 Tour Pass AI 助手。你可以问我关于行程的问题，比如「附近有什么好吃的」「下午还有空余时间吗」等。' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    const allStops = days.flatMap(d => d.stops);
    const context = {
      city,
      hotel: hotel?.name || '未选择',
      stops: allStops.map(s => ({ name: s.poi.name, area: s.poi.area, arrival: s.arrival, departure: s.departure })),
      total_days: days.length,
    };

    try {
      const res = await fetch('/trip/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg,
          context: `当前行程上下文：${JSON.stringify(context)}`,
        }),
      });
      const data = await res.json();
      const reply = data.reply || data.message || '抱歉，我无法理解你的问题。';
      setMessages(prev => [...prev, { role: 'assistant', content: reply }]);
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '网络错误，请稍后重试。' }]);
    } finally {
      setLoading(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-[1001] w-12 h-12 bg-primary-500 text-white rounded-full shadow-lg hover:bg-primary-600 flex items-center justify-center text-lg"
      >
        💬
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-[1001] w-80 h-96 bg-white rounded-xl shadow-xl border flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b bg-primary-500 text-white rounded-t-xl">
        <span className="text-sm font-semibold">🤖 AI 助手</span>
        <button onClick={() => setOpen(false)} className="ml-auto text-white/70 hover:text-white text-xs">✕</button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-2">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] px-3 py-2 rounded-lg text-sm ${msg.role === 'user' ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-800'}`}>
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="px-3 py-2 rounded-lg bg-gray-100 text-sm text-gray-500">思考中...</div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex gap-2 p-2 border-t">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && sendMessage()}
          placeholder="问我任何问题..."
          className="flex-1 px-3 py-1.5 border rounded-lg text-sm"
          disabled={loading}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="px-3 py-1.5 bg-primary-500 text-white rounded-lg text-sm hover:bg-primary-600 disabled:opacity-50"
        >
          发送
        </button>
      </div>
    </div>
  );
}
