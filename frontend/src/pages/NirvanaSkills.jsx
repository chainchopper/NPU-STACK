import { useState, useEffect } from 'react';
import { apiUrl } from '../api/client';

/**
 * NirvanaSkills — native React skills browser reading from /api/nirvana/skills.
 */
export default function NirvanaSkills() {
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    fetch(apiUrl('/nirvana/skills'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { setSkills(d.skills || []); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const viewSkill = async (name) => {
    setSelected({ name, loading: true });
    try {
      const r = await fetch(apiUrl(`/nirvana/skills/${name}`));
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSelected({ name, data, loading: false });
    } catch (e) {
      setSelected({ name, error: e.message, loading: false });
    }
  };

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading skills...</span></div>;
  if (error) return <div className="page-card" style={{color:'var(--text-secondary)'}}>Error: {error}</div>;

  return (
    <div style={{ padding: 24, maxWidth: 960 }}>
      <h2 style={{ marginBottom: 4 }}>Nirvana Skills</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 24 }}>
        {skills.length} skills — native browser reading shared Nirvana state.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12, marginBottom: 24 }}>
        {skills.map(s => (
          <div key={s.name}
            onClick={() => viewSkill(s.name)}
            style={{
              padding: 14, borderRadius: 10, cursor: 'pointer',
              background: selected?.name === s.name ? 'var(--bg-card-hover)' : 'var(--bg-card)',
              border: `1px solid ${s.pinned ? '#facc15' : 'var(--border-color)'}`,
              transition: 'background 0.15s',
            }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>{s.name}</span>
              {s.pinned && <span style={{ fontSize: 11 }}>📌</span>}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              <span style={{
                display: 'inline-block', padding: '1px 6px', borderRadius: 4,
                background: 'var(--bg-tertiary)', marginRight: 8,
              }}>{s.category}</span>
              <span>{s.state}</span>
              <span style={{ marginLeft: 8 }}>used {s.use_count}×</span>
            </div>
          </div>
        ))}
      </div>

      {/* Skill detail */}
      {selected?.loading && <div className="spinner" style={{margin:'20px auto'}}/>}
      {selected?.error && <div style={{color:'#f87171',fontSize:13}}>Error: {selected.error}</div>}
      {selected?.data && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border-color)',
          borderRadius: 10, padding: 20, maxHeight: '50vh', overflow: 'auto',
        }}>
          <h3 style={{ margin: '0 0 4px' }}>{selected.data.name}</h3>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
            {selected.data.category}
          </div>
          <pre style={{
            background: 'var(--bg-input)', color: 'var(--text-primary)',
            padding: 16, borderRadius: 8, fontSize: 12, lineHeight: 1.6,
            overflow: 'auto', maxHeight: 400, whiteSpace: 'pre-wrap',
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            {selected.data.content}
          </pre>
        </div>
      )}
    </div>
  );
}
