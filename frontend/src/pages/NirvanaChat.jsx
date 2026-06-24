import { useState, useEffect } from 'react';
import { ChatInterface } from '../components/ChatInterface';
import { API_BASE } from '../api/client';
import { ExternalLink, MessageSquare, Settings } from 'lucide-react';

export default function NirvanaChat() {
  const [agentStatus, setAgentStatus] = useState(null);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/agent/status`).then(r => r.json()).then(d => setAgentStatus(d)).catch(() => {});
    fetch(`${API_BASE}/models`).then(r => r.json()).then(d => {
      const list = Array.isArray(d) ? d : (d.models || []);
      setModels(list.filter(m => m?.format === 'gguf' || m?.framework === 'llama.cpp'));
    }).catch(() => {});
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px)' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 16px', background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-color)', minHeight: 38, flexShrink: 0, gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <MessageSquare size={18} style={{ color: 'var(--accent-blue)' }} />
          <span style={{ fontWeight: 600, fontSize: 14 }}>Nirvana Agent Chat</span>
          {agentStatus && (
            <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 12, background: agentStatus.running ? '#1a3a2a' : '#3a1a1a', color: agentStatus.running ? '#4ade80' : '#f87171' }}>
              {agentStatus.running ? 'Agent Online' : 'Agent Offline'}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {models.length > 0 && (
            <select
              value={selectedModel?.id || ''}
              onChange={e => setSelectedModel(models.find(m => m.id === e.target.value) || null)}
              style={{ padding: '4px 8px', borderRadius: 6, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 12, maxWidth: 180 }}>
              <option value="">System Agent (default)</option>
              {models.map(m => <option key={m.id} value={m.id}>{m.display_name || m.name || m.id}</option>)}
            </select>
          )}
          <a href="http://127.0.0.1:8010" target="_blank" rel="noopener"
            style={{ color: 'var(--accent-blue)', fontSize: 12, display: 'flex', alignItems: 'center', gap: 4, textDecoration: 'none' }}>
            <ExternalLink size={12} /> Advanced UI
          </a>
        </div>
      </div>
      <ChatInterface model={selectedModel} className="nirvana-main-chat" />
    </div>
  );
}
