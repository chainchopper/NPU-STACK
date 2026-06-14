import { useState, useEffect } from 'react';
import { apiUrl } from '../api/client';

export default function NirvanaMemory() {
  const [files, setFiles] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(apiUrl('/nirvana/memory'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { setFiles(d.files || []); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const openFile = async (name) => {
    setSelected({ name, loading: true });
    try {
      const r = await fetch(apiUrl(`/nirvana/memory/${name}`));
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSelected({ name, data, loading: false });
    } catch (e) {
      setSelected({ name, error: e.message, loading: false });
    }
  };

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading memory...</span></div>;
  if (error) return <div className="page-card" style={{color:'var(--text-secondary)'}}>Error: {error}</div>;

  return (
    <div style={{ padding: 24, maxWidth: 960 }}>
      <h2 style={{ marginBottom: 4 }}>Memory</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 24 }}>
        {files.length} memory files — native reader from shared Nirvana state.
      </p>

      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 1, maxWidth: 260 }}>
          {files.map(f => (
            <div key={f.name}
              onClick={() => openFile(f.name)}
              style={{
                padding: '10px 12px', marginBottom: 6, borderRadius: 8, cursor: 'pointer',
                background: selected?.name === f.name ? 'var(--bg-card-hover)' : 'var(--bg-card)',
                border: '1px solid var(--border-color)',
              }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                {f.name.replace('.md', '')}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                {f.size.toLocaleString()} bytes
              </div>
            </div>
          ))}
        </div>

        <div style={{ flex: 2 }}>
          {!selected && (
            <div style={{ color: 'var(--text-muted)', padding: 40, textAlign: 'center', fontSize: 13 }}>
              Select a memory file to view
            </div>
          )}
          {selected?.loading && <div className="spinner" style={{margin:'20px auto'}}/>}
          {selected?.error && <div style={{color:'#f87171',fontSize:13}}>Error: {selected.error}</div>}
          {selected?.data && (
            <div style={{
              background: 'var(--bg-card)', border: '1px solid var(--border-color)',
              borderRadius: 10, padding: 20, maxHeight: '70vh', overflow: 'auto',
            }}>
              <h3 style={{ margin: '0 0 12px', fontSize: 15 }}>{selected.name}</h3>
              <pre style={{
                background: 'var(--bg-input)', color: 'var(--text-primary)',
                padding: 16, borderRadius: 8, fontSize: 12, lineHeight: 1.6,
                whiteSpace: 'pre-wrap', fontFamily: "'JetBrains Mono', monospace",
                maxHeight: 500, overflow: 'auto',
              }}>
                {selected.data.content}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
