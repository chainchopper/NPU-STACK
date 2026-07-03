import { useRef, useState, useCallback } from 'react';
import { ExternalLink, RefreshCw, MessageSquare, AlertCircle } from 'lucide-react';

const WEBUI_URL = '/nirvana-webui/';  // WebUI CSP patched to allow localhost:5180

export default function NirvanaChat() {
  const iframeRef = useRef(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const retryCount = useRef(0);

  const reload = useCallback(() => {
    setLoaded(false);
    setError(false);
    retryCount.current++;
    if (iframeRef.current) {
      iframeRef.current.src = WEBUI_URL + (WEBUI_URL.includes('?') ? '&' : '?') + '_r=' + retryCount.current;
    }
  }, []);

  const handleError = () => { setError(true); setLoaded(false); };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px)', position: 'relative' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 16px', background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-color)', minHeight: 38, flexShrink: 0, gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <MessageSquare size={18} style={{ color: 'var(--accent-blue)' }} />
          <span style={{ fontWeight: 600, fontSize: 14 }}>Nirvana Chat</span>
          <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 12, background: '#1a3a2a', color: '#4ade80' }}>Agent</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={reload} style={btnStyle} title="Reload"><RefreshCw size={13} /> Reload</button>
          <button onClick={() => window.open(WEBUI_URL, '_blank')} style={{ ...btnStyle, borderColor: 'var(--accent-blue)', color: 'var(--accent-blue)' }}>
            <ExternalLink size={13} /> Pop Out</button>
        </div>
      </div>

      {!loaded && !error && (
        <div style={{ position: 'absolute', top: 38, left: 0, right: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-primary)', zIndex: 5 }}>
          <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
            <div className="spinner" style={{ margin: '0 auto 12px' }} />
            <p style={{ fontSize: 13 }}>Loading Nirvana agent...</p>
          </div>
        </div>
      )}

      {error && (
        <div style={{ position: 'absolute', top: 38, left: 0, right: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-primary)', zIndex: 5 }}>
          <div style={{ textAlign: 'center', maxWidth: 400 }}>
            <AlertCircle size={40} style={{ color: 'var(--accent-red)', marginBottom: 12 }} />
            <p style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Could not load the Nirvana agent</p>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>Is the Nirvana WebUI running on port 8789?</p>
            <button onClick={reload} style={{ padding: '8px 20px', borderRadius: 8, background: 'var(--accent-blue)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 13 }}>Retry</button>
            <button onClick={() => window.open(WEBUI_URL, '_blank')} style={{ marginLeft: 8, padding: '8px 20px', borderRadius: 8, background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', border: '1px solid var(--border-color)', cursor: 'pointer', fontSize: 13 }}>Open in new tab</button>
          </div>
        </div>
      )}

      <iframe
        ref={iframeRef}
        src={WEBUI_URL}
        onLoad={() => setLoaded(true)}
        onError={handleError}
        style={{ flex: 1, border: 'none', width: '100%', background: 'var(--bg-primary)' }}
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
