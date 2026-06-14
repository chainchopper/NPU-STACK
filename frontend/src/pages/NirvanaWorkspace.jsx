import { useState } from 'react';
import { apiUrl } from '../api/client';
import { Folder, File, ChevronRight } from 'lucide-react';

export default function NirvanaWorkspace() {
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const browse = async (dir) => {
    setLoading(true); setError(null);
    try {
      const r = await fetch(apiUrl(`/nirvana/workspace?path=${encodeURIComponent(dir)}`));
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setPath(dir);
      setEntries(d.entries || []);
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  };

  return (
    <div style={{ padding: 24, maxWidth: 900 }}>
      <h2 style={{ marginBottom: 4 }}>Workspace</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16 }}>
        {path || 'J:\\NPU-STACK'} — {entries.length} entries
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button onClick={() => browse('')} style={btnStyle}>Root</button>
        <button onClick={() => browse('backend')} style={btnStyle}>backend/</button>
        <button onClick={() => browse('frontend')} style={btnStyle}>frontend/</button>
        <button onClick={() => browse('docs')} style={btnStyle}>docs/</button>
        <button onClick={() => browse('hermes-agent')} style={btnStyle}>hermes-agent/</button>
        <button onClick={() => browse('hermes-webui')} style={btnStyle}>hermes-webui/</button>
      </div>

      {loading && <div className="spinner" style={{margin:'20px auto'}}/>}
      {error && <div style={{color:'#f87171',fontSize:13,marginBottom:12}}>Error: {error}</div>}

      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border-color)',
        borderRadius: 10, overflow: 'hidden',
      }}>
        {entries.map((e, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '8px 14px', fontSize: 13,
            borderBottom: i < entries.length - 1 ? '1px solid var(--border-color)' : 'none',
            cursor: e.is_dir ? 'pointer' : 'default',
            color: 'var(--text-primary)',
            ':hover': { background: 'var(--bg-card-hover)' },
          }}
            onClick={() => e.is_dir && browse(e.path)}
          >
            {e.is_dir ? <Folder size={16} color="#facc15" /> : <File size={16} color="var(--text-muted)" />}
            <span style={{ flex: 1 }}>{e.name}</span>
            {e.size > 0 && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{(e.size / 1024).toFixed(1)} KB</span>}
            {e.is_dir && <ChevronRight size={14} color="var(--text-muted)" />}
          </div>
        ))}
      </div>
    </div>
  );
}

const btnStyle = {
  padding: '4px 12px', fontSize: 12, borderRadius: 6,
  background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)',
  color: 'var(--text-secondary)', cursor: 'pointer',
};
