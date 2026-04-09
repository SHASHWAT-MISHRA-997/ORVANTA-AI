'use client';

import { FormEvent, useMemo, useRef, useState, useEffect } from 'react';
import { MessageCircle, X, Send, Loader2, Sparkles } from 'lucide-react';
import { assistantAPI } from '@/lib/api';

type ChatRole = 'user' | 'assistant';

type ChatMessage = {
  role: ChatRole;
  content: string;
};

const INITIAL_MESSAGE: ChatMessage = {
  role: 'assistant',
  content: 'Namaste. I am your AI assistant for Dashboard, Events, Alerts, Analytics, and Manage. How can I help?',
};

export default function AssistantWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([INITIAL_MESSAGE]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const canSend = useMemo(() => input.trim().length > 0 && !isSending, [input, isSending]);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, isOpen]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const text = input.trim();
    if (!text || isSending) return;

    const userMessage: ChatMessage = { role: 'user', content: text };
    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);
    setInput('');
    setIsSending(true);

    try {
      const history = nextMessages.slice(-12).map((item) => ({ role: item.role, content: item.content }));
      const response = await assistantAPI.chat({
        message: text,
        history,
        client_now_iso: new Date().toISOString(),
        client_tz_offset_minutes: new Date().getTimezoneOffset(),
      });

      const assistantText = String(response.data?.response || '').trim() || 'I could not generate a response right now.';
      setMessages((prev) => [...prev, { role: 'assistant', content: assistantText }]);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: typeof detail === 'string' && detail ? detail : 'Assistant is temporarily unavailable. Please try again.',
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <>
      {isOpen && (
        <div
          style={{
            position: 'fixed',
            right: 20,
            bottom: 84,
            width: 'min(420px, calc(100vw - 32px))',
            height: 'min(560px, calc(100vh - 120px))',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
            borderRadius: 16,
            boxShadow: '0 24px 64px rgba(0,0,0,0.35)',
            zIndex: 80,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px 14px',
              borderBottom: '1px solid var(--border-color)',
              background: 'linear-gradient(120deg, rgba(14,165,233,0.18), rgba(16,185,129,0.18))',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Sparkles size={16} style={{ color: 'var(--accent-cyan)' }} />
              <strong style={{ fontSize: 14 }}>AI Assistant</strong>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              aria-label="Close assistant"
              className="btn btn-ghost"
              style={{ padding: '6px 8px' }}
            >
              <X size={16} />
            </button>
          </div>

          <div ref={scrollRef} style={{ padding: 12, overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {messages.map((item, index) => {
              const isUser = item.role === 'user';
              return (
                <div
                  key={`${item.role}-${index}`}
                  style={{
                    alignSelf: isUser ? 'flex-end' : 'flex-start',
                    maxWidth: '88%',
                    borderRadius: 12,
                    padding: '10px 12px',
                    whiteSpace: 'pre-wrap',
                    fontSize: 13,
                    lineHeight: 1.45,
                    background: isUser ? 'linear-gradient(120deg, var(--accent-cyan), #0891b2)' : 'var(--bg-hover)',
                    color: isUser ? '#ecfeff' : 'var(--text-primary)',
                    border: `1px solid ${isUser ? 'rgba(6,182,212,0.45)' : 'var(--border-color)'}`,
                  }}
                >
                  {item.content}
                </div>
              );
            })}
          </div>

          <form onSubmit={handleSubmit} style={{ borderTop: '1px solid var(--border-color)', padding: 10, display: 'flex', gap: 8 }}>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask anything about this workspace..."
              className="input"
              style={{ flex: 1 }}
              maxLength={4000}
            />
            <button type="submit" className="btn btn-primary" disabled={!canSend} style={{ minWidth: 42, paddingInline: 10 }}>
              {isSending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </form>
        </div>
      )}

      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="btn btn-primary"
        style={{
          position: 'fixed',
          right: 20,
          bottom: 20,
          zIndex: 81,
          borderRadius: 999,
          width: 54,
          height: 54,
          display: 'grid',
          placeItems: 'center',
          boxShadow: '0 12px 30px rgba(6,182,212,0.32)',
          padding: 0,
        }}
        aria-label="Open AI assistant"
      >
        <MessageCircle size={20} />
      </button>
    </>
  );
}
