import { useState, useEffect } from 'react';
import { apiUrl } from '../api/client';

export default function NirvanaPlugins() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(apiUrl('/nirvana/overview'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading...</span></div>;
  if (error) return <div className="page-card" style={{color:'var(--text-secondary)'}}>Error: {error}</div>;

  return (
    <div style={{ padding: 24, maxWidth: 800 }}>
      <h2 style={{ marginBottom: 4 }}>Plugins & Extensions</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 24 }}>
        Nirvana's plugin system — context engines, memory providers, observability, image generation, and more.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
        <PluginCard name="Memory Providers" desc="honcho, mem0, supermemory, ..." active={2} total={4} />
        <PluginCard name="Context Engines" desc="Session compression, anchoring" active={1} total={2} />
        <PluginCard name="Model Providers" desc="openrouter, anthropic, gmi, ..." active={3} total={8} />
        <PluginCard name="Observability" desc="Metrics, traces, logs" active={0} total={1} />
        <PluginCard name="Image Generation" desc="Stable Diffusion, DALL-E, ..." active={0} total={3} />
        <PluginCard name="Achievements" desc="Gamified tracking" active={0} total={1} />
        <PluginCard name="Kanban Dispatcher" desc="Multi-agent board" active={1} total={1} />
        <PluginCard name="Disk Cleanup" desc="Automatic cache clearing" active={0} total={1} />
      </div>

      <div style={{ marginTop: 32, padding: 20, borderRadius: 10,
        background: 'var(--bg-card)', border: '1px dashed var(--border-color)',
        textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
        Plugins are discovered at startup from <code>hermes-agent/plugins/</code>.<br/>
        Configure them in the full Nirvana WebUI settings or via MCP tools.
      </div>
    </div>
  );
}

function PluginCard({ name, desc, active, total }) {
  return (
    <div style={{
      padding: 14, borderRadius: 10, background: 'var(--bg-card)',
      border: '1px solid var(--border-color)',
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
        {name}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>{desc}</div>
      <div style={{ display: 'flex', gap: 4 }}>
        {Array.from({length: total}, (_, i) => (
          <div key={i} style={{
            width: 20, height: 6, borderRadius: 3,
            background: i < active ? '#4ade80' : 'var(--bg-tertiary)',
          }}/>
        ))}
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
        {active}/{total} enabled
      </div>
    </div>
  );
}
