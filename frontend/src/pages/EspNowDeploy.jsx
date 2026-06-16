import { useState, useEffect } from 'react';
import { apiUrl } from '../api/client';
import { Cpu, Download, Zap, CheckCircle, XCircle } from 'lucide-react';

export default function EspNowDeploy() {
  const [status, setStatus] = useState(null);
  const [examples, setExamples] = useState([]);
  const [selected, setSelected] = useState(null);
  const [buildInfo, setBuildInfo] = useState(null);
  const [binaries, setBinaries] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(apiUrl('/espnow/status'))
      .then(r => r.ok ? r.json() : Promise.reject('failed'))
      .then(d => setStatus(d))
      .catch(() => setStatus({ library_available: false }));

    fetch(apiUrl('/espnow/examples'))
      .then(r => r.ok ? r.json() : Promise.reject('failed'))
      .then(d => setExamples(d.examples || []))
      .catch(() => setExamples([]))
      .finally(() => setLoading(false));
  }, []);

  const loadExample = async (name) => {
    setSelected(name);
    setBuildInfo(null);
    setBinaries(null);
    try {
      const [bResp, fResp] = await Promise.all([
        fetch(apiUrl(`/espnow/examples/${name}/build`)).then(r => r.json()),
        fetch(apiUrl(`/espnow/examples/${name}/binaries`)).then(r => r.json()),
      ]);
      setBuildInfo(bResp);
      setBinaries(fResp);
    } catch (e) { setError('Failed to load build info'); }
  };

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading ESP-NOW...</span></div>;
  if (!status?.library_available) return <div className="page-card" style={{color:'var(--text-secondary)',textAlign:'center',padding:40}}>
    <Cpu size={48} style={{marginBottom:16,opacity:0.3}}/>
    <p>ESP-NOW library not found in <code>libraries/esp-now-lib/</code></p>
    <p style={{fontSize:12}}>Run the assimilation step to bake ESP-NOW into the workspace.</p>
  </div>;

  return (
    <div style={{ padding: 24, maxWidth: 1000 }}>
      <h2 style={{ marginBottom: 4 }}>ESP-NOW Deployment</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16 }}>
        {examples.length} examples · IDF {status.idf_available ? 'available' : 'not detected'} · {binaries?.built ? `${binaries.count} binaries built` : 'no binaries'}
      </p>

      {error && <div style={{color:'#f87171',fontSize:13,marginBottom:12}}>{error}</div>}

      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 1, maxWidth: 280 }}>
          {examples.map(e => (
            <div key={e.name}
              onClick={() => loadExample(e.name)}
              style={{
                padding: '10px 12px', marginBottom: 6, borderRadius: 8, cursor: 'pointer',
                background: selected === e.name ? 'var(--bg-card-hover)' : 'var(--bg-card)',
                border: '1px solid var(--border-color)',
              }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Cpu size={14} color="#4ade80"/>
                <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{e.name.replace(/_/g, ' ')}</span>
                {e.has_cmake && <Zap size={12} color="#facc15" title="Has CMake"/>}
              </div>
            </div>
          ))}
        </div>

        <div style={{ flex: 2 }}>
          {!selected && <div style={{ color: 'var(--text-muted)', padding: 30, textAlign: 'center', fontSize: 13 }}>Select an example</div>}

          {buildInfo && !buildInfo.error && (
            <div style={{
              padding: 16, borderRadius: 10, marginBottom: 12,
              background: 'var(--bg-card)', border: '1px solid var(--border-color)',
            }}>
              <h3 style={{ margin: '0 0 8px', fontSize: 14 }}>Build — {selected}</h3>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
                Target: {buildInfo.target} · Port: {buildInfo.port} · IDF: {buildInfo.idf_available ? <CheckCircle size={12} style={{display:'inline',color:'#4ade80'}}/> : <XCircle size={12} style={{display:'inline',color:'#f87171'}}/>}
              </div>
              {Object.entries(buildInfo.commands || {}).map(([step, cmd]) => (
                <div key={step} style={{ marginBottom: 6 }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{step}</div>
                  <code style={{ fontSize: 11, padding: '4px 8px', borderRadius: 4, background: 'var(--bg-input)', display: 'block' }}>{cmd}</code>
                </div>
              ))}
            </div>
          )}

          {binaries?.built && (
            <div style={{
              padding: 16, borderRadius: 10,
              background: 'var(--bg-card)', border: '1px solid #4ade8044',
            }}>
              <h3 style={{ margin: '0 0 8px', fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Download size={14} color="#4ade80"/> {binaries.count} binaries
              </h3>
              {binaries.binaries.map((b, i) => (
                <div key={i} style={{ fontSize: 12, color: 'var(--text-primary)', display: 'flex', gap: 12, marginBottom: 4 }}>
                  <span>{b.name}</span>
                  <span style={{ color: 'var(--text-muted)' }}>{(b.size / 1024).toFixed(1)} KB · {b.offset}</span>
                </div>
              ))}
            </div>
          )}

          {binaries && !binaries.built && (
            <div style={{ padding: 16, borderRadius: 10, background: 'var(--bg-card)', border: '1px dashed var(--border-color)', textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
              No binaries built yet. Run build to generate firmware, then flash to your ESP32 device.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
