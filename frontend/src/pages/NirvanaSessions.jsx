import { useState, useEffect } from 'react';
import { apiUrl } from '../api/client';

/**
 * NirvanaSessions — native React session browser reading from /api/nirvana/sessions.
 */
export default function NirvanaSessions() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    fetch(apiUrl('/nirvana/sessions?limit=50'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { setSessions(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const openSession = async (id) => {
    setSelected({ id, loading: true });
    try {
      const r = await fetch(apiUrl(`/nirvana/sessions/${id}`));
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSelected({ id, data, loading: false });
    } catch (e) {
      setSelected({ id, error: e.message, loading: false });
    }
  };

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading sessions...</span></div>;
  if (error) return <div className="page-card" style={{color:'var(--text-secondary)'}}>Error: {error}</div>;

  return (
    <div style={{ padding: 24, maxWidth: 900 }}>
      <h2 style={{ marginBottom: 4 }}>Nirvana Sessions</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 24 }}>
        {sessions.length} sessions — native browser reading shared Nirvana state.
      </p>

      <div style={{ display: 'flex', gap: 16 }}>
        {/* Session list */}
        <div style={{ flex: 1, maxWidth: 360 }}>
          {sessions.map(s => (
            <div key={s.session_id}
              onClick={() => openSession(s.session_id)}
              style={{
                padding: '10px 12px', marginBottom: 6, borderRadius: 8,
                background: selected?.id === s.session_id ? 'var(--bg-card-hover)' : 'var(--bg-card)',
                border: '1px solid var(--border-color)', cursor: 'pointer',
                transition: 'background 0.15s',
              }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s.title?.split('\n')[0]?.slice(0, 60) || 'Untitled'}
              </div>
              <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 11, color: 'var(--text-muted)' }}>
                <span>{s.model}</span>
                <span>{s.message_count} msgs</span>
                {s.pinned && <span style={{ color: '#facc15' }}>📌</span>}
              </div>
            </div>
          ))}
        </div>

        {/* Session detail */}
        <div style={{ flex: 2, minWidth: 0 }}>
          {!selected && (
            <div style={{ color: 'var(--text-muted)', padding: 40, textAlign: 'center', fontSize: 13 }}>
              Select a session to view details
            </div>
          )}
          {selected?.loading && <div className="spinner" style={{margin:'40px auto'}}/>}
          {selected?.error && <div style={{color:'#f87171',fontSize:13}}>Error: {selected.error}</div>}
          {selected?.data && (
            <div style={{
              background: 'var(--bg-card)', border: '1px solid var(--border-color)',
              borderRadius: 10, padding: 16, maxHeight: '70vh', overflow: 'auto',
            }}>
              <h3 style={{ margin: '0 0 12px', fontSize: 15 }}>
                {selected.data.title?.split('\n')[0]?.slice(0, 80) || 'Untitled'}
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px', fontSize: 12, marginBottom: 16 }}>
                <Meta kv="Model" v={selected.data.model} />
                <Meta kv="Provider" v={selected.data.model_provider || '—'} />
                <Meta kv="Messages" v={selected.data.message_count} />
                <Meta kv="User msgs" v={selected.data.user_message_count} />
                <Meta kv="Input tokens" v={selected.data.input_tokens?.toLocaleString()} />
                <Meta kv="Output tokens" v={selected.data.output_tokens?.toLocaleString()} />
                <Meta kv="Pinned" v={selected.data.pinned ? 'Yes' : 'No'} />
                <Meta kv="Profile" v={selected.data.profile} />
              </div>
              {selected.data.messages?.length > 0 && (
                <div>
                  <h4 style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>Messages ({selected.data.messages.length})</h4>
                  {selected.data.messages.slice(-20).map((m, i) => (
                    <div key={i} style={{
                      padding: '6px 10px', marginBottom: 4, borderRadius: 6,
                      background: m.role === 'user' ? 'var(--bg-tertiary)' : 'transparent',
                      fontSize: 12, color: 'var(--text-primary)',
                      borderLeft: m.role === 'assistant' ? '2px solid #4ade80' : 'none',
                      maxHeight: 80, overflow: 'hidden',
                    }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: 10, marginRight: 8 }}>
                        {m.role}
                      </span>
                      {typeof m.content === 'string' ? m.content.slice(0, 200) : JSON.stringify(m.content).slice(0, 200)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Meta({ kv, v }) {
  return (
    <>
      <span style={{ color: 'var(--text-muted)' }}>{kv}</span>
      <span style={{ color: 'var(--text-primary)' }}>{v ?? '—'}</span>
    </>
  );
}
