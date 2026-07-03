import { useEffect } from 'react';

const WEBUI_URL = 'http://127.0.0.1:8789';  // standalone Nirvana WebUI — opens in new tab

export default function NirvanaChat() {
  // Auto-open WebUI in new tab — iframes are blocked by CSP/X-Frame-Options
  useEffect(() => {
    window.open(WEBUI_URL, 'nirvana-chat');
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px)', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
      <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>Nirvana Chat should open in a new tab.</p>
      <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>If blocked by popup blocker, click below:</p>
      <a href={WEBUI_URL} target="_blank" rel="noopener noreferrer"
        style={{ padding: '12px 24px', borderRadius: 8, background: 'var(--accent-blue)', color: '#fff', textDecoration: 'none', fontSize: 14, fontWeight: 600 }}>
        Open Nirvana Chat
      </a>
    </div>
  );
}
