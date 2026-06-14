import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiUrl } from '../api/client';
import { Bot, Settings, MessageSquare, Puzzle, Clock, Server, Database } from 'lucide-react';

export default function NirvanaDashboard() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetch(apiUrl('/nirvana/overview'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { setOverview(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading Nirvana overview...</span></div>;
  if (error) return <div className="page-card" style={{color:'var(--text-secondary)'}}>Error: {error}</div>;
  if (!overview) return null;

  return (
    <div style={{ padding: 24, maxWidth: 1000 }}>
      <h2 style={{ marginBottom: 4 }}>Nirvana</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 24 }}>
        Native overview — all data read directly from shared Nirvana state.
      </p>

      {/* Status cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12, marginBottom: 24 }}>
        <StatusCard icon={<Bot size={18}/>} label="Agent" value={overview.agent?.name || 'Nirvana'} sub={overview.agent?.provider} color="#4ade80" />
        <StatusCard icon={<Database size={18}/>} label="Sessions" value={overview.sessions?.total || 0} sub={`${overview.sessions?.pinned || 0} pinned`} color="#60a5fa" />
        <StatusCard icon={<Puzzle size={18}/>} label="Skills" value={overview.skills?.count || 0} sub={overview.skills?.names?.join(', ')} color="#facc15" />
        <StatusCard icon={<Server size={18}/>} label="Provider" value={overview.config?.model?.provider || 'unknown'} sub={overview.config?.model?.default} color="#c084fc" />
      </div>

      {/* Quick nav */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10, marginBottom: 24 }}>
        <QuickNav onClick={() => navigate('/nirvana-settings')} icon={<Settings size={16}/>} label="Settings" />
        <QuickNav onClick={() => navigate('/nirvana-sessions')} icon={<MessageSquare size={16}/>} label="Sessions" />
        <QuickNav onClick={() => navigate('/nirvana-skills')} icon={<Puzzle size={16}/>} label="Skills" />
        <QuickNav onClick={() => navigate('/nirvana-chat')} icon={<Bot size={16}/>} label="Chat" />
      </div>

      {/* Recent sessions */}
      {overview.sessions?.recent?.length > 0 && (
        <div>
          <h3 style={{ fontSize: 13, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>
            Recent Sessions
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {overview.sessions.recent.map((s, i) => (
              <div key={i}
                onClick={() => navigate(`/nirvana-sessions`)}
                style={{
                  padding: '8px 12px', borderRadius: 8, cursor: 'pointer',
                  background: 'var(--bg-card)', border: '1px solid var(--border-color)',
                  fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                <span style={{ color: 'var(--text-primary)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:'70%' }}>
                  {s.title || 'Untitled'}
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{s.model} · {s.message_count} msgs</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatusCard({ icon, label, value, sub, color }) {
  return (
    <div style={{
      padding: 16, borderRadius: 10, background: 'var(--bg-card)',
      border: `1px solid ${color}33`, display: 'flex', flexDirection: 'column', gap: 6,
    }}>
      <div style={{display:'flex',alignItems:'center',gap:8}}>
        <span style={{color}}>{icon}</span>
        <span style={{color:'var(--text-muted)',fontSize:11,textTransform:'uppercase',letterSpacing:0.5}}>{label}</span>
      </div>
      <div style={{fontSize:22,fontWeight:700,color:'var(--text-primary)'}}>{value}</div>
      {sub && <div style={{fontSize:11,color:'var(--text-muted)'}}>{sub}</div>}
    </div>
  );
}

function QuickNav({ onClick, icon, label }) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px',
      borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--border-color)',
      color: 'var(--text-primary)', cursor: 'pointer', fontSize: 13, fontWeight: 500,
      transition: 'background 0.15s',
    }}>
      {icon} {label}
    </button>
  );
}
