import { useEffect } from 'react';

const WEBUI_URL = 'http://127.0.0.1:8789';

export default function NirvanaChat() {
  useEffect(() => {
    window.location.href = WEBUI_URL;
  }, []);

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 'calc(100vh - 64px)' }}>
      <a href={WEBUI_URL} style={{ fontSize: 16, color: 'var(--accent-blue)', textDecoration: 'none', fontWeight: 600 }}>
        Opening Nirvana Chat…
      </a>
    </div>
  );
}
