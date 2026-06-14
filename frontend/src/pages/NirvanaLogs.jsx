import { useState, useEffect } from 'react';
import { apiUrl } from '../api/client';

export default function NirvanaLogs() {
  const [files, setFiles] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(apiUrl('/nirvana/logs'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { setFiles(d.files || []); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const openLog = async (name) => {
    setSelected({ name, loading: true });
    try {
      const r = await fetch(apiUrl(`/nirvana/logs/${name}?tail=300`));
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSelected({ name, data, loading: false });
    } catch (e) {
      setSelected({ name, error: e.message, loading: false });
    }
  };

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading logs...</span></div>;
  if (error) return <div className="page-card" style={{color:'var(--text-secondary)'}}>Error: {error}</div>;

  return (
    <div style={{ padding: 24, maxWidth: 960 }}>
      <h2 style={{ marginBottom: 4 }}>Logs</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 24 }}>
        {files.length} log files — native reader from shared Nirvana state.
      </p>

      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 1, maxWidth: 220 }}>
          {files.map(f => (
            <div key={f.name}
              onClick={() => openLog(f.name)}
              style={{
                padding: '10px 12px', marginBottom: 6, borderRadius: 8, cursor: 'pointer',
                background: selected?.name === f.name ? 'var(--bg-card-hover)' : 'var(--bg-card)',
                border: '1px solid var(--border-color)',
              }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                {f.name}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                {(f.size / 1024).toFixed(1)} KB
              </div>
            </div>
          ))}
        </div>

        <div style={{ flex: 3, minWidth: 0 }}>
          {!selected && (
            <div style={{ color: 'var(--text-muted)', padding: 40, textAlign: 'center', fontSize: 13 }}>
              Select a log file to view
            </div>
          )}
          {selected?.loading && <div className="spinner" style={{margin:'20px auto'}}/>}
          {selected?.error && <div style={{color:'#f87171',fontSize:13}}>Error: {selected.error}</div>}
          {selected?.data && (
            <div>
              <div style={{
                fontSize: 11, color: 'var(--text-muted)', marginBottom: 8,
                display: 'flex', gap: 16,
              }}>
                <span>{(selected.data.size / 1024).toFixed(1)} KB</span>
                <span>{selected.data.total_lines.toLocaleString()} total lines</span>
                <span>showing last {selected.data.shown_lines}</span>
              </div>
              <pre style={{
                background: 'var(--bg-input)', color: 'var(--text-primary)',
                padding: 16, borderRadius: 8, fontSize: 11, lineHeight: 1.5,
                maxHeight: 600, overflow: 'auto', whiteSpace: 'pre-wrap',
                fontFamily: "'JetBrains Mono', monospace",
                border: '1px solid var(--border-color)',
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
