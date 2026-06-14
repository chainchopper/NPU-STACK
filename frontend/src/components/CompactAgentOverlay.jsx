import { useState, useRef, useEffect } from 'react';
import { apiUrl } from '../api/client';
import { Bot, Send, X, Sparkles } from 'lucide-react';

/**
 * CompactAgentOverlay — native quick-chat drawer that appears on any page
 * when you click the agent icon. Sends directly to /api/agent/chat.
 */
export default function CompactAgentOverlay({ onClose }) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    setSending(true);
    setError(null);

    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);

    try {
      const r = await fetch(apiUrl('/agent/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [userMsg],
          profile_id: 'orchestration-agent',
          runtime_mode: 'auto',
          use_fleet_tools: false,
          use_orchestration_context: false,
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response || '(no response)',
        runtime: data.nirvana_runtime,
      }]);
    } catch (e) {
      setError(e.message);
      setMessages(prev => [...prev, { role: 'assistant', content: `[Error: ${e.message}]`, error: true }]);
    }
    setSending(false);
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div style={{
      position: 'fixed', bottom: 20, right: 20, zIndex: 1000,
      width: 380, maxHeight: 520, borderRadius: 16,
      background: 'var(--bg-card-solid, #0f172a)',
      border: '1px solid var(--border-color)',
      boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 14px', borderBottom: '1px solid var(--border-color)',
        background: 'var(--bg-secondary)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Bot size={16} color="#4ade80" />
          <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>Nirvana</span>
          <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 8, background: '#1a3a2a', color: '#4ade80' }}>
            DeepSeek
          </span>
        </div>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', color: 'var(--text-secondary)',
          cursor: 'pointer', padding: 4,
        }}><X size={16}/></button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {messages.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', padding: 30 }}>
            Quick chat with Nirvana.<br/>Ask anything about NPU-STACK.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{
            padding: '8px 12px', borderRadius: 10, fontSize: 12, lineHeight: 1.5,
            background: m.role === 'user' ? 'var(--bg-tertiary)' : 'transparent',
            color: m.error ? '#f87171' : 'var(--text-primary)',
            borderLeft: m.role === 'assistant' && !m.error ? '2px solid #4ade80' : 'none',
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '90%',
          }}>
            <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {m.content?.length > 500 ? m.content.slice(0, 500) + '...' : m.content}
            </div>
            {m.runtime && (
              <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 4 }}>
                {m.runtime.engine} · {m.runtime.model_file || m.runtime.provider}
              </div>
            )}
          </div>
        ))}
        {sending && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: 8 }}>
            <div className="spinner" style={{display:'inline-block',width:12,height:12,marginRight:8}}/>
            Nirvana is thinking...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '10px 14px', borderTop: '1px solid var(--border-color)',
        display: 'flex', gap: 8, alignItems: 'flex-end',
      }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask Nirvana..."
          rows={2}
          style={{
            flex: 1, resize: 'none',
            background: 'var(--bg-input, #080d1a)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-color)',
            borderRadius: 10, padding: '8px 12px',
            fontSize: 12, fontFamily: 'inherit',
            outline: 'none',
          }}
          disabled={sending}
        />
        <button
          onClick={send}
          disabled={sending || !input.trim()}
          style={{
            background: input.trim() ? '#4ade80' : 'var(--bg-tertiary)',
            border: 'none', borderRadius: 10, padding: '8px 12px',
            cursor: input.trim() ? 'pointer' : 'default',
            color: input.trim() ? '#000' : 'var(--text-muted)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'background 0.15s',
          }}>
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
