import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

const PROXY_URL = 'http://127.0.0.1:8010';

const SCRIPT_ORDER = [
  'static/pwa-startup.js',
  'static/boot.js',
  'static/i18n.js',
  'static/icons.js',
  'static/messages.js',
  'static/sessions.js',
  'static/commands.js',
  'static/panels.js',
  'static/workspace.js',
  'static/terminal.js',
  'static/ui.js',
  'static/onboarding.js',
  'static/vendor/smd.min.js',
  'static/vendor/katex/0.16.22/katex.min.js',
];

/**
 * NirvanaChatNative — mounts the absorbed Nirvana WebUI directly into React DOM.
 * No iframe. Scripts loaded in-order against the injected HTML structure.
 */
export default function NirvanaChatNative() {
  const navigate = useNavigate();
  const containerRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function mount() {
      try {
        // 1. Fetch the full HTML from the proxy
        const resp = await fetch(`${PROXY_URL}/`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const html = await resp.text();

        // 2. Extract <body> content and <head> styles/links
        const bodyMatch = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
        if (!bodyMatch) throw new Error('No body found in HTML');
        const bodyHTML = bodyMatch[1];

        const headMatch = html.match(/<head[^>]*>([\s\S]*)<\/head>/i);
        const headHTML = headMatch ? headMatch[1] : '';

        // 3. Extract styles and meta that need to be in the container
        const styles = (headHTML.match(/<link[^>]*stylesheet[^>]*>/gi) || []).join('\n');
        const metas = (headHTML.match(/<meta[^>]*>/gi) || []).join('\n');

        if (cancelled) return;

        // 4. Inject into React-managed container
        const container = containerRef.current;
        if (!container) return;

        // Remove scripts from body HTML initially — we load them separately
        const cleanBody = bodyHTML.replace(/<script[\s\S]*?<\/script>/gi, '');

        // Set innerHTML with styles first, then body content
        container.innerHTML = `
          <base href="${PROXY_URL}/">
          ${metas}
          ${styles}
          <style>
            .nirvana-native { color-scheme: dark; }
            .nirvana-native * { box-sizing: border-box; }
            .nirvana-native textarea, .nirvana-native input, .nirvana-native button { font-family: inherit; }
          </style>
          <div class="nirvana-native">
            ${cleanBody}
          </div>
        `;

        // 5. Load scripts in order
        for (const src of SCRIPT_ORDER) {
          if (cancelled) return;
          await new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = `${PROXY_URL}/${src}`;
            script.onload = resolve;
            script.onerror = () => {
              // Soft-fail for non-critical scripts
              resolve();
            };
            container.appendChild(script);
          });
        }

        if (!cancelled) setLoading(false);
      } catch (e) {
        if (!cancelled) {
          setError(e.message);
          setLoading(false);
        }
      }
    }

    mount();
    return () => { cancelled = true; };
  }, []);

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      zIndex: 50, background: '#0D0D1A',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 16px', background: '#141425',
        borderBottom: '1px solid #2a2a4a', minHeight: 44, flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => navigate('/agents')} style={{
            background: 'none', border: 'none', color: '#888', cursor: 'pointer',
            fontSize: 18, padding: '4px 8px', borderRadius: 6,
          }}>← Back</button>
          <span style={{ fontWeight: 600, fontSize: 15, color: '#e0e0e0' }}>Nirvana</span>
          <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 10, background: '#1a3a2a', color: '#4ade80' }}>DeepSeek</span>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div style={{ padding: 40, textAlign: 'center', color: '#888' }}>
          <p>Failed to load Nirvana: {error}</p>
          <button onClick={() => window.location.reload()} style={{
            marginTop: 16, padding: '8px 24px', background: '#4ade80', color: '#000',
            border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600,
          }}>Retry</button>
        </div>
      )}

      {/* Loading overlay */}
      {loading && !error && (
        <div style={{
          position: 'absolute', top: 44, left: 0, right: 0, bottom: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: '#0D0D1A', zIndex: 5,
        }}>
          <div style={{ textAlign: 'center', color: '#888' }}>
            <div style={{ width: 40, height: 40, border: '3px solid #333', borderTop: '3px solid #4ade80', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 16px' }}/>
            Loading Nirvana...
          </div>
        </div>
      )}

      {/* Native WebUI container */}
      <div ref={containerRef} style={{ flex: 1, overflow: 'hidden' }}/>
    </div>
  );
}
