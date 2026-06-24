import { useState, useRef, useEffect, useCallback } from 'react';
import { apiUrl } from '../api/client';
import { Bot, Send, X, Sparkles, Mic, MicOff, ChevronDown } from 'lucide-react';

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const STORAGE_KEY_MIC = 'nirvana_selected_mic';

/**
 * CompactAgentOverlay — native quick-chat drawer that appears on any page
 * when you click the agent icon. Sends directly to /api/agent/chat.
 * Supports voice input via Web Speech API with selectable microphone.
 */
export default function CompactAgentOverlay({ onClose }) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  // ── Voice state ──
  const [listening, setListening] = useState(false);
  const [interimText, setInterimText] = useState('');
  const [micDevices, setMicDevices] = useState([]);
  const [selectedMic, setSelectedMic] = useState(() => localStorage.getItem(STORAGE_KEY_MIC) || 'default');
  const [micMenuOpen, setMicMenuOpen] = useState(false);
  const recognitionRef = useRef(null);
  const micMenuRef = useRef(null);

  // Enumerate microphones
  useEffect(() => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const load = async () => {
      try {
        // Request permission to see device labels
        await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => {});
        const devices = await navigator.mediaDevices.enumerateDevices();
        const mics = devices
          .filter(d => d.kind === 'audioinput' && d.deviceId)
          .map(d => ({ id: d.deviceId, label: d.label || `Mic ${d.deviceId.slice(0, 8)}` }));
        if (mics.length > 0) {
          setMicDevices(mics);
          // If stored mic not in list, fall back to first
          if (!mics.find(m => m.id === selectedMic)) {
            setSelectedMic(mics[0].id);
          }
        }
      } catch { /* enumerateDevices may fail in some contexts */ }
    };
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist mic selection
  useEffect(() => { localStorage.setItem(STORAGE_KEY_MIC, selectedMic); }, [selectedMic]);

  // Close mic menu on outside click
  useEffect(() => {
    if (!micMenuOpen) return;
    const h = (e) => { if (micMenuRef.current && !micMenuRef.current.contains(e.target)) setMicMenuOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [micMenuOpen]);

  // Cleanup recognition on unmount
  useEffect(() => () => { recognitionRef.current?.abort(); }, []);

  const startListening = useCallback(() => {
    if (!SpeechRecognition) return;
    const rec = new SpeechRecognition();
    rec.lang = 'en-US';
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    recognitionRef.current = rec;

    rec.onresult = (e) => {
      let interim = '';
      let final = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t;
        else interim += t;
      }
      if (final) {
        setInput(prev => (prev ? prev + ' ' : '') + final.trim());
        setInterimText('');
      } else {
        setInterimText(interim);
      }
    };

    rec.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') { /* ignore */ }
      else setError(`Mic error: ${e.error}`);
      setListening(false);
    };

    rec.onend = () => {
      setListening(false);
      // Auto-send after voice capture if we got text
      setInput(prev => {
        if (prev.trim()) {
          // Trigger send on next tick after state settles
          setTimeout(() => {
            setSending(s => { if (!s) return true; return s; });
          }, 50);
        }
        return prev;
      });
    };

    setListening(true);
    setError(null);
    rec.start();
  }, []);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  // Auto-send trigger after voice capture
  useEffect(() => {
    if (!sending) return;
    if (!input.trim()) { setSending(false); return; }
    // Only auto-send from voice — manual sends use the button
    // We detect voice-triggered send by checking if listening just ended
    send();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sending]);

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
            Nirvana
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
        display: 'flex', gap: 6, alignItems: 'flex-end',
      }}>
        {/* Mic selector + button */}
        {SpeechRecognition && (
          <div ref={micMenuRef} style={{ position: 'relative' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <button
                onClick={() => setMicMenuOpen(v => !v)}
                title="Select microphone"
                style={{
                  background: 'var(--bg-input, #080d1a)', border: '1px solid var(--border-color)',
                  borderRadius: 8, padding: '4px 6px', cursor: 'pointer',
                  color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 2,
                  fontSize: 10,
                }}>
                <ChevronDown size={10} />
              </button>
              <button
                onClick={listening ? stopListening : startListening}
                disabled={sending && !listening}
                title={listening ? 'Stop listening' : 'Speak to Nirvana'}
                style={{
                  background: listening ? '#ef4444' : 'var(--bg-input, #080d1a)',
                  border: listening ? 'none' : '1px solid var(--border-color)',
                  borderRadius: 8, padding: '6px 8px', cursor: 'pointer',
                  color: listening ? '#fff' : 'var(--text-muted)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'all 0.15s', opacity: sending && !listening ? 0.4 : 1,
                }}>
                {listening ? <MicOff size={16} /> : <Mic size={16} />}
              </button>
            </div>
            {micMenuOpen && micDevices.length > 1 && (
              <div style={{
                position: 'absolute', bottom: '100%', left: 0, marginBottom: 4,
                background: 'var(--bg-card-solid, #0f172a)',
                border: '1px solid var(--border-color)', borderRadius: 10,
                padding: 4, minWidth: 180, maxHeight: 180, overflow: 'auto',
                boxShadow: '0 8px 24px rgba(0,0,0,0.4)', zIndex: 10,
              }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', padding: '4px 8px' }}>Microphone</div>
                {micDevices.map(m => (
                  <button key={m.id}
                    onClick={() => { setSelectedMic(m.id); setMicMenuOpen(false); }}
                    style={{
                      display: 'block', width: '100%', textAlign: 'left',
                      padding: '5px 8px', border: 'none', borderRadius: 6,
                      background: selectedMic === m.id ? 'var(--bg-tertiary)' : 'transparent',
                      color: selectedMic === m.id ? '#4ade80' : 'var(--text-primary)',
                      fontSize: 11, cursor: 'pointer',
                    }}>
                    {m.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <textarea
          value={listening ? (input + (interimText ? ' ' + interimText : '')) : input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={listening ? 'Listening...' : 'Ask Nirvana...'}
          rows={2}
          style={{
            flex: 1, resize: 'none',
            background: listening ? 'rgba(74,222,128,0.06)' : 'var(--bg-input, #080d1a)',
            color: 'var(--text-primary)',
            border: listening ? '1px solid #4ade8066' : '1px solid var(--border-color)',
            borderRadius: 10, padding: '8px 12px',
            fontSize: 12, fontFamily: 'inherit',
            outline: 'none', transition: 'border-color 0.2s, background 0.2s',
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
