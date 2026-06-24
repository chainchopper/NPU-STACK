import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Trash2, Settings, Copy, AlertCircle, ImagePlus, X } from 'lucide-react';
import { useChat } from '../hooks/useChat';
import '../styles/chat-interface.css';

/**
 * Main assistant chat.
 * Note: backend /api/agent/chat is currently text-only.
 */
export const ChatInterface = ({
  initialMessage = null,
  enableFleetContext = true,
  onMessageSent = null,
  model = null,
  className = '',
}) => {
  const draftKey = `npu-chat-draft-${model?.id || 'system'}-${enableFleetContext ? 'fleet' : 'default'}`;
  const { messages, isLoading, error, sendMessage, clearChat, setMaxTokens, threadId } = useChat({ selectedModel: model });
  const [inputValue, setInputValue] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [copiedId, setCopiedId] = useState(null);
  const [pendingImages, setPendingImages] = useState([]);
  const [tokenLimit, setTokenLimit] = useState(() => {
    try { return parseInt(localStorage.getItem('npu-chat-max-tokens'), 10) || 4096; } catch { return 4096; }
  });
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => { setMaxTokens(tokenLimit); try { localStorage.setItem('npu-chat-max-tokens', tokenLimit); } catch {} }, [tokenLimit, setMaxTokens]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(draftKey);
      if (saved) setInputValue(saved);
    } catch {}
  }, [draftKey]);

  useEffect(() => {
    try {
      if (inputValue?.trim()) localStorage.setItem(draftKey, inputValue);
      else localStorage.removeItem(draftKey);
    } catch {}
  }, [draftKey, inputValue]);

  useEffect(() => {
    if (initialMessage && messages.length === 0) {
      handleSend(initialMessage);
    }
  }, []);

  const handleSend = async (msg = inputValue) => {
    const trimmed = msg.trim();
    if ((!trimmed && pendingImages.length === 0) || isLoading) return;

    const imagesToSend = [...pendingImages];
    setPendingImages([]);
    setInputValue('');
    try { localStorage.removeItem(draftKey); } catch {}
    await sendMessage(trimmed, imagesToSend);

    if (onMessageSent) onMessageSent(trimmed);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      if (e.shiftKey) return;
      e.preventDefault();
      handleSend();
    }
  };

  const handleImageFile = (e) => {
    const files = Array.from(e.target.files || []);
    files.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (ev) => setPendingImages((prev) => [...prev, ev.target.result]);
      reader.readAsDataURL(file);
    });
    e.target.value = '';
  };

  const removeImage = (idx) => {
    setPendingImages((prev) => prev.filter((_, i) => i !== idx));
  };

  const copyToClipboard = (text, msgId) => {
    navigator.clipboard.writeText(text);
    setCopiedId(msgId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const renderMessage = (msg) => {
    const isUser = msg.role === 'user';
    const isError = msg.isError;

    return (
      <div
        key={msg.id}
        className={`chat-message ${isUser ? 'user-message' : 'assistant-message'} ${isError ? 'error-message' : ''}`}
      >
        <div className="message-avatar">
          {isUser ? (
            <div className="avatar-circle user">U</div>
          ) : isError ? (
            <AlertCircle size={24} className="error-icon" />
          ) : (
            <div className="avatar-circle assistant">A</div>
          )}
        </div>

        <div className="message-content">
          <div className="message-bubble">
            {msg.images?.length > 0 && (
              <div className="message-images">
                {msg.images.map((src, i) => (
                  <img key={i} src={src} alt="attachment" className="message-img-thumb" />
                ))}
              </div>
            )}

            <p className="message-text">{msg.content}</p>

            {msg.metadata && Object.values(msg.metadata).some(Boolean) && (
              <div className="message-metadata">
                {msg.metadata.reasoning && (
                  <details className="metadata-section">
                    <summary>🧠 Reasoning</summary>
                    <pre>{msg.metadata.reasoning}</pre>
                  </details>
                )}

                {msg.metadata.toolCalls?.length > 0 && (
                  <details className="metadata-section">
                    <summary>⚙️ Tool Calls ({msg.metadata.toolCalls.length})</summary>
                    <div className="tool-calls-list">
                      {msg.metadata.toolCalls.map((tool, i) => (
                        <div key={i} className="tool-call">
                          <code>{tool.name}</code>
                          {tool.result && <span className="tool-result">✓</span>}
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {msg.metadata.fleetContext && (
                  <details className="metadata-section">
                    <summary>🚀 Fleet Context</summary>
                    <pre>{JSON.stringify(msg.metadata.fleetContext, null, 2)}</pre>
                  </details>
                )}
              </div>
            )}

            <div className="message-timestamp">{new Date(msg.timestamp).toLocaleTimeString()}</div>
          </div>

          <div className="message-actions">
            <button className="action-btn" onClick={() => copyToClipboard(msg.content, msg.id)} title="Copy message">
              {copiedId === msg.id ? '✓' : <Copy size={16} />}
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className={`chat-interface ${className}`}>
      <div className="chat-header">
        <div className="header-info">
          <h3 className="header-title">NPU-STACK Chat</h3>
          <p className="header-subtitle">
            {model
              ? `Selected model: ${model.display_name || model.name} (${model.framework}/${model.format})`
              : enableFleetContext
                ? '🚀 Fleet-aware agent'
                : 'System chat'}
          </p>
        </div>

        <div className="header-actions">
          <button className="header-btn" onClick={() => setShowSettings(!showSettings)} title="Settings">
            <Settings size={18} />
          </button>
          <button className="header-btn danger" onClick={clearChat} title="Clear chat">
            <Trash2 size={18} />
          </button>
        </div>
      </div>

      {showSettings && (
        <div className="settings-panel">
          <div className="setting-item">
            <label>Thread: <code>{threadId?.slice(0,20)}…</code></label>
          </div>
          <div className="setting-item" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <label style={{ whiteSpace: 'nowrap', fontSize: 12 }}>Max tokens: <strong>{tokenLimit}</strong></label>
            <input type="range" min={256} max={8192} step={256} value={tokenLimit}
              onChange={e => setTokenLimit(Number(e.target.value))}
              style={{ flex: 1, accentColor: 'var(--accent-blue)' }} />
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>8192</span>
          </div>
          <div className="setting-item">
            <label>
              <input type="checkbox" defaultChecked={enableFleetContext} readOnly />
              Fleet Context
            </label>
          </div>
          <div className="setting-item" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            History saved in browser · {messages.length} messages · <button onClick={clearChat} style={{ background: 'none', border: 'none', color: 'var(--accent-red)', cursor: 'pointer', fontSize: 11, textDecoration: 'underline' }}>Clear all</button>
          </div>
        </div>
      )}

      <div className="messages-container">
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">💬</div>
            <h4>Start a conversation</h4>
            <p>Use chat for system assistant + use Model Test panel for model-level inference checks.</p>
          </div>
        ) : (
          messages.map((msg) => renderMessage(msg))
        )}
        <div ref={messagesEndRef} />
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {pendingImages.length > 0 && (
        <div className="pending-images">
          {pendingImages.map((src, i) => (
            <div key={i} className="pending-img-wrap">
              <img src={src} alt="pending" className="pending-img" />
              <button className="pending-img-remove" onClick={() => removeImage(i)}>
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="chat-input-area">
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: 'none' }}
          onChange={handleImageFile}
        />

        <button
          className="img-upload-btn"
          onClick={() => fileInputRef.current?.click()}
          title="Attach image preview"
          disabled={isLoading}
        >
          <ImagePlus size={18} />
        </button>

        <textarea
          ref={inputRef}
          className="chat-input"
          placeholder="Ask anything… (Shift+Enter for newline, Enter to send)"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          rows="3"
        />

        <button
          className="send-button"
          onClick={() => handleSend()}
          disabled={isLoading || (!inputValue.trim() && pendingImages.length === 0)}
          title="Send message"
        >
          {isLoading ? <Loader2 size={20} className="spinner" /> : <Send size={20} />}
        </button>
      </div>
    </div>
  );
};

export default ChatInterface;
