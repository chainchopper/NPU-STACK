import { useRef } from 'react';

const NIRVANA_WEBUI_URL = 'http://127.0.0.1:8010';

export default function NirvanaChat() {
  const iframeRef = useRef(null);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px)' }}>
      {/* Minimal top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 16px', background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-color)', minHeight: 38, flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>Nirvana Chat</span>
          <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 8, background: '#1a3a2a', color: '#4ade80' }}>DeepSeek</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={() => window.open(NIRVANA_WEBUI_URL, '_blank')} style={btnStyle} title="Open in new tab">↗ Pop out</button>
          <button onClick={() => { if (iframeRef.current) iframeRef.current.src = NIRVANA_WEBUI_URL; }} style={btnStyle}>↻ Reload</button>
        </div>
      </div>

      {/* Full-height iframe */}
      <iframe
        ref={iframeRef}
        src={NIRVANA_WEBUI_URL}
        style={{
          flex: 1, border: 'none', width: '100%',
          background: 'var(--bg-primary)', borderRadius: '0 0 10px 10px',
        }}
        title="Nirvana Chat"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}

const btnStyle = {
  background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)',
  color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 11,
  padding: '3px 10px', borderRadius: 6,
};
