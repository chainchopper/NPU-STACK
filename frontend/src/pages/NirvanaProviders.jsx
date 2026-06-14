import { useState, useEffect } from 'react';
import { apiUrl } from '../api/client';

export default function NirvanaProviders() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(apiUrl('/nirvana/providers'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading providers...</span></div>;
  if (error) return <div className="page-card" style={{color:'var(--text-secondary)'}}>Error: {error}</div>;

  const providers = data?.providers || {};

  return (
    <div style={{ padding: 24, maxWidth: 900 }}>
      <h2 style={{ marginBottom: 4 }}>Model Providers</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 24 }}>
        {data?.count || 0} providers — credential pool from shared Nirvana auth state.
      </p>

      {Object.entries(providers).map(([name, creds]) => (
        <div key={name} style={{ marginBottom: 20 }}>
          <h3 style={{
            fontSize: 14, fontWeight: 600, color: 'var(--text-primary)',
            textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10,
            paddingBottom: 6, borderBottom: '1px solid var(--border-color)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            {name === 'deepseek' && '🔵'} {name === 'copilot' && '🟢'}
            {name}
            <span style={{
              fontSize: 11, padding: '1px 8px', borderRadius: 10,
              background: '#1a3a2a', color: '#4ade80', fontWeight: 400,
            }}>
              {creds.length} credential{creds.length !== 1 ? 's' : ''}
            </span>
          </h3>

          {creds.map((c, i) => (
            <div key={i} style={{
              padding: '10px 14px', marginBottom: 6, borderRadius: 8,
              background: 'var(--bg-card)', border: '1px solid var(--border-color)',
              fontSize: 13,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{c.label}</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{c.source}</span>
              </div>
              <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-muted)' }}>
                <span>{c.base_url}</span>
                <span style={{ marginLeft: 16 }}>{c.request_count.toLocaleString()} requests</span>
                {c.last_error && <span style={{ marginLeft: 12, color: '#f87171' }}>⚠ {c.last_error.substring(0, 60)}</span>}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
