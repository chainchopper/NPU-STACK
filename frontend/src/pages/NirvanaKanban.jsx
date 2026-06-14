import { useState, useEffect } from 'react';
import { apiUrl } from '../api/client';

export default function NirvanaKanban() {
  const [boards, setBoards] = useState([]);
  const [active, setActive] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(apiUrl('/nirvana/kanban'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => {
        setBoards(d.boards || []);
        setActive(d.active);
        setLoading(false);
      })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const openBoard = async (slug) => {
    setSelected({ slug, loading: true });
    try {
      const r = await fetch(apiUrl(`/nirvana/kanban/${slug}`));
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSelected({ slug, data, loading: false });
    } catch (e) {
      setSelected({ slug, error: e.message, loading: false });
    }
  };

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading kanban...</span></div>;
  if (error) return <div className="page-card" style={{color:'var(--text-secondary)'}}>Error: {error}</div>;

  return (
    <div style={{ padding: 24, maxWidth: 900 }}>
      <h2 style={{ marginBottom: 4 }}>Kanban Boards</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 24 }}>
        {boards.length} boards — active: <strong>{active || 'none'}</strong>
      </p>

      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 1, maxWidth: 300 }}>
          {boards.map(b => (
            <div key={b.slug}
              onClick={() => openBoard(b.slug)}
              style={{
                padding: '12px 14px', marginBottom: 8, borderRadius: 10, cursor: 'pointer',
                background: selected?.slug === b.slug ? 'var(--bg-card-hover)' : 'var(--bg-card)',
                border: `1px solid ${b._active ? '#facc15' : 'var(--border-color)'}`,
              }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 10, height: 10, borderRadius: '50%',
                  background: b.color || '#666', flexShrink: 0,
                }}/>
                <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                  {b.name}
                  {b._active && <span style={{color:'#facc15',fontSize:11,marginLeft:6}}>● Active</span>}
                </span>
              </div>
              {b.description && <div style={{fontSize:11,color:'var(--text-muted)',marginTop:4,marginLeft:18}}>{b.description}</div>}
              {b.archived && <div style={{fontSize:10,color:'#f87171',marginLeft:18}}>Archived</div>}
            </div>
          ))}
        </div>

        <div style={{ flex: 2 }}>
          {!selected && (
            <div style={{ color: 'var(--text-muted)', padding: 40, textAlign: 'center', fontSize: 13 }}>
              Select a board to view details
            </div>
          )}
          {selected?.loading && <div className="spinner" style={{margin:'20px auto'}}/>}
          {selected?.error && <div style={{color:'#f87171',fontSize:13}}>Error: {selected.error}</div>}
          {selected?.data && (
            <div style={{
              background: 'var(--bg-card)', border: '1px solid var(--border-color)',
              borderRadius: 10, padding: 20,
            }}>
              <h3 style={{ margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 12, height: 12, borderRadius: '50%', background: selected.data.color || '#666' }}/>
                {selected.data.name}
              </h3>
              <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 16 }}>
                {selected.data.description || 'No description'}
              </p>
              <pre style={{
                background: 'var(--bg-input)', color: 'var(--text-primary)',
                padding: 16, borderRadius: 8, fontSize: 12, lineHeight: 1.6,
                maxHeight: 400, overflow: 'auto', whiteSpace: 'pre-wrap',
                fontFamily: "'JetBrains Mono', monospace",
              }}>
                {JSON.stringify(selected.data, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
