import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

const NIRVANA_WEBUI_URL = 'http://127.0.0.1:8789';

/**
 * NirvanaChat — Full Nirvana agent interface baked into NPU-STACK.
 *
 * Phase 1 embeds the absorbed Hermes WebUI via iframe so all features
 * (streaming chat, sessions, tools, skills, cron, kanban, settings)
 * work immediately through the proxy middleware at :8010.
 *
 * Phase 2 will replace the iframe with directly-mounted vanilla JS modules
 * from frontend/src/nirvana-webui/ when CSRF/server-template dependencies
 * are resolved.
 */
export default function NirvanaChat() {
  const navigate = useNavigate();
  const iframeRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Hide global NPU-STACK sidebar when in Nirvana chat for full immersion
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) sidebar.style.display = 'none';

    return () => {
      if (sidebar) sidebar.style.display = '';
    };
  }, []);

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      zIndex: 50,
      background: 'var(--bg-primary, #0D0D1A)',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Top bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 16px',
        background: 'var(--bg-secondary, #141425)',
        borderBottom: '1px solid var(--border-color, #2a2a4a)',
        minHeight: 44,
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            onClick={() => navigate('/agents')}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-secondary, #888)',
              cursor: 'pointer',
              fontSize: 18,
              padding: '4px 8px',
              borderRadius: 6,
            }}
            title="Back to Agents"
          >
            ← Back
          </button>
          <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-primary, #e0e0e0)' }}>
            Nirvana
          </span>
          <span style={{
            fontSize: 11,
            padding: '2px 8px',
            borderRadius: 10,
            background: '#1a3a2a',
            color: '#4ade80',
          }}>
            DeepSeek
          </span>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => window.open(NIRVANA_WEBUI_URL, '_blank')}
            style={{
              background: 'var(--bg-tertiary, #1a1a2e)',
              border: '1px solid var(--border-color, #333)',
              color: 'var(--text-secondary, #aaa)',
              cursor: 'pointer',
              fontSize: 12,
              padding: '4px 12px',
              borderRadius: 6,
            }}
            title="Open Nirvana in a separate tab"
          >
            ↗ Pop out
          </button>
          <button
            onClick={() => { if (iframeRef.current) iframeRef.current.src = NIRVANA_WEBUI_URL; }}
            style={{
              background: 'var(--bg-tertiary, #1a1a2e)',
              border: '1px solid var(--border-color, #333)',
              color: 'var(--text-secondary, #aaa)',
              cursor: 'pointer',
              fontSize: 12,
              padding: '4px 12px',
              borderRadius: 6,
            }}
            title="Reload the Nirvana interface"
          >
            ↻ Reload
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div style={{
          padding: '40px',
          textAlign: 'center',
          color: 'var(--text-secondary, #888)',
        }}>
          <p>{error}</p>
          <button
            onClick={() => {
              setError(null);
              setLoading(true);
              if (iframeRef.current) iframeRef.current.src = NIRVANA_WEBUI_URL;
            }}
            style={{
              marginTop: 16,
              padding: '8px 24px',
              background: '#4ade80',
              color: '#000',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading overlay */}
      {loading && !error && (
        <div style={{
          position: 'absolute',
          top: 44,
          left: 0,
          right: 0,
          bottom: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg-primary, #0D0D1A)',
          zIndex: 5,
        }}>
          <div style={{ textAlign: 'center', color: 'var(--text-secondary, #888)' }}>
            <div style={{
              width: 40,
              height: 40,
              border: '3px solid var(--border-color, #333)',
              borderTop: '3px solid #4ade80',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
              margin: '0 auto 16px',
            }} />
            Loading Nirvana...
          </div>
        </div>
      )}

      {/* Nirvana WebUI iframe */}
      <iframe
        ref={iframeRef}
        src={NIRVANA_WEBUI_URL}
        onLoad={() => setLoading(false)}
        onError={() => {
          setLoading(false);
          setError('Nirvana WebUI is not reachable. Make sure the backend and Nirvana runtime are running.');
        }}
        style={{
          flex: 1,
          border: 'none',
          width: '100%',
          background: 'var(--bg-primary, #0D0D1A)',
        }}
        title="Nirvana - NPU-STACK Orchestration Agent"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}
