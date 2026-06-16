import { useState, useEffect, useRef, useCallback } from 'react';
import { apiUrl, API_BASE } from '../api/client';
import {
  Cpu, Terminal, Zap, Radio, FolderOpen, MonitorSmartphone,
  RefreshCw, Play, Square, Wifi, WifiOff, CheckCircle,
  XCircle, Download, Upload, FolderPlus, Trash2,
} from 'lucide-react';

// ── Tabs ──────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'devices', label: 'Devices', icon: MonitorSmartphone },
  { id: 'terminal', label: 'Terminal', icon: Terminal },
  { id: 'espnow', label: 'ESP-NOW', icon: Radio },
  { id: 'projects', label: 'IDF Projects', icon: FolderOpen },
];

// ── Terminals ──────────────────────────────────────────────────────────────
let xtermLib = null;
let fitAddonLib = null;
let webLinksAddonLib = null;

async function loadXterm() {
  if (xtermLib) return { Terminal: xtermLib, FitAddon: fitAddonLib, WebLinksAddon: webLinksAddonLib };
  const [xt, fit, wl] = await Promise.all([
    import('@xterm/xterm'),
    import('@xterm/addon-fit'),
    import('@xterm/addon-web-links'),
  ]);
  xtermLib = xt.Terminal;
  fitAddonLib = fit.FitAddon;
  webLinksAddonLib = wl.WebLinksAddon;
  return { Terminal: xtermLib, FitAddon: fitAddonLib, WebLinksAddon: webLinksAddonLib };
}

// ── Serial Terminal Tab ────────────────────────────────────────────────────
function SerialTerminal() {
  const termRef = useRef(null);
  const termInstance = useRef(null);
  const wsRef = useRef(null);
  const fitAddonRef = useRef(null);
  const [ports, setPorts] = useState([]);
  const [espPorts, setEspPorts] = useState([]);
  const [selectedPort, setSelectedPort] = useState('');
  const [connected, setConnected] = useState(false);
  const [loadingPorts, setLoadingPorts] = useState(true);
  const [xtermReady, setXtermReady] = useState(false);

  // Load xterm.js
  useEffect(() => {
    loadXterm().then(() => setXtermReady(true)).catch(() => {});
  }, []);

  // Fetch serial ports
  const refreshPorts = useCallback(async () => {
    setLoadingPorts(true);
    try {
      const r = await fetch(API_BASE + '/api/esp/serial-ports');
      const data = await r.json();
      setPorts(data.ports || []);
      setEspPorts(data.esp_ports || []);
      if (!selectedPort && data.esp_ports?.length > 0) {
        setSelectedPort(data.esp_ports[0].device);
      }
    } catch { /* ignore */ }
    setLoadingPorts(false);
  }, [selectedPort]);

  useEffect(() => { refreshPorts(); }, []);

  // Init terminal
  useEffect(() => {
    if (!xtermReady || !termRef.current) return;
    const term = new xtermLib({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: "'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace",
      theme: {
        background: '#0a0f1a',
        foreground: '#c9d1d9',
        cursor: '#4ade80',
        selectionBackground: '#1e3a5f',
        black: '#161b22',
        red: '#f85149',
        green: '#3fb950',
        yellow: '#d29922',
        blue: '#58a6ff',
        magenta: '#bc8cff',
        cyan: '#39c5cf',
        white: '#b1bac4',
        brightBlack: '#6e7681',
        brightRed: '#ff7b72',
        brightGreen: '#56d364',
        brightYellow: '#e3b341',
        brightBlue: '#79c0ff',
        brightMagenta: '#d2a8ff',
        brightCyan: '#56d4dd',
        brightWhite: '#f0f6fc',
      },
      allowProposedApi: true,
    });
    const fitAddon = new fitAddonLib();
    const webLinksAddon = new webLinksAddonLib();
    term.loadAddon(fitAddon);
    term.loadAddon(webLinksAddon);
    term.open(termRef.current);
    fitAddon.fit();
    termInstance.current = term;
    fitAddonRef.current = fitAddon;

    term.write('\x1b[2J\x1b[H'); // Clear
    term.writeln('\x1b[1;36m╔══════════════════════════════════════════╗');
    term.writeln('\x1b[1;36m║     NPU-STACK ESP Serial Terminal        ║');
    term.writeln('\x1b[1;36m║     Select a device and click Connect    ║');
    term.writeln('\x1b[1;36m╚══════════════════════════════════════════╝\x1b[0m\r\n');

    const handleResize = () => { try { fitAddon.fit(); } catch {} };
    window.addEventListener('resize', handleResize);
    return () => { window.removeEventListener('resize', handleResize); term.dispose(); };
  }, [xtermReady]);

  const connect = async () => {
    if (!selectedPort || !termInstance.current) return;
    const term = termInstance.current;

    const wsUrl = (API_BASE.replace('http', 'ws')) + `/api/esp/terminal/${encodeURIComponent(selectedPort)}?baud=115200`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'data') {
          term.write(msg.text.replace(/\n/g, '\r\n'));
        } else if (msg.type === 'connected') {
          term.writeln(`\r\n\x1b[1;32m✔ ${msg.message}\x1b[0m\r\n`);
        } else if (msg.type === 'error') {
          term.writeln(`\r\n\x1b[1;31m✖ ${msg.message}\x1b[0m\r\n`);
          setConnected(false);
        }
      } catch {
        term.write(e.data);
      }
    };
    ws.onclose = () => {
      term.writeln('\r\n\x1b[1;33m[Disconnected]\x1b[0m\r\n');
      setConnected(false);
    };
    ws.onerror = () => {
      term.writeln('\r\n\x1b[1;31m[Connection error]\x1b[0m\r\n');
      setConnected(false);
    };

    // Send keystrokes to serial
    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ text: data }));
      }
    });
  };

  const disconnect = () => {
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ action: 'close' }));
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 10 }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
        padding: '8px 10px', background: 'var(--bg-secondary)', borderRadius: 8,
        border: '1px solid var(--border-color)',
      }}>
        <MonitorSmartphone size={16} color="#4ade80" />
        <select
          value={selectedPort}
          onChange={e => setSelectedPort(e.target.value)}
          disabled={connected}
          style={{
            background: 'var(--bg-input)', color: 'var(--text-primary)',
            border: '1px solid var(--border-color)', borderRadius: 6,
            padding: '4px 8px', fontSize: 12, minWidth: 180,
          }}>
          <option value="">-- Select port --</option>
          {espPorts.length > 0 && (
            <optgroup label="ESP Devices">
              {espPorts.map(p => (
                <option key={p.device} value={p.device}>
                  {p.device} {p.chip ? `(${p.chip})` : ''}
                </option>
              ))}
            </optgroup>
          )}
          {ports.filter(p => !p.is_esp).length > 0 && (
            <optgroup label="Other Ports">
              {ports.filter(p => !p.is_esp).map(p => (
                <option key={p.device} value={p.device}>{p.device} — {p.description}</option>
              ))}
            </optgroup>
          )}
        </select>
        <button onClick={refreshPorts} disabled={connected || loadingPorts}
          style={{
            background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)',
            borderRadius: 6, padding: '4px 8px', cursor: 'pointer', color: 'var(--text-secondary)',
          }} title="Refresh ports">
          <RefreshCw size={14} />
        </button>
        {!connected ? (
          <button onClick={connect} disabled={!selectedPort}
            style={{
              background: selectedPort ? '#4ade80' : 'var(--bg-tertiary)',
              border: 'none', borderRadius: 6, padding: '5px 12px', cursor: selectedPort ? 'pointer' : 'default',
              color: selectedPort ? '#000' : 'var(--text-muted)', fontSize: 12, fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
            <Play size={12} /> Connect
          </button>
        ) : (
          <button onClick={disconnect}
            style={{
              background: '#ef4444', color: '#fff', border: 'none', borderRadius: 6,
              padding: '5px 12px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
            <Square size={12} /> Disconnect
          </button>
        )}
        <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {ports.length} port{ports.length !== 1 ? 's' : ''} · {espPorts.length} ESP
        </span>
      </div>

      {/* Terminal */}
      <div ref={termRef} style={{
        flex: 1, minHeight: 350, borderRadius: 8, overflow: 'hidden',
        border: connected ? '1px solid #4ade8066' : '1px solid var(--border-color)',
      }} />
    </div>
  );
}

// ── Devices Tab ────────────────────────────────────────────────────────────
function DevicesPanel() {
  const [ports, setPorts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fleetDevices, setFleetDevices] = useState([]);

  const refresh = async () => {
    setLoading(true);
    try {
      const [pRes, fRes] = await Promise.all([
        fetch(API_BASE + '/api/esp/serial-ports').then(r => r.json()),
        fetch(API_BASE + '/api/fleet/devices').then(r => r.ok ? r.json() : { devices: [] }),
      ]);
      setPorts(pRes.ports || []);
      setFleetDevices(fRes.devices || []);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { refresh(); }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <MonitorSmartphone size={18} color="#4ade80" />
        <h3 style={{ margin: 0, fontSize: 16, color: 'var(--text-primary)' }}>ESP Devices</h3>
        <button onClick={refresh} style={{
          background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)',
          borderRadius: 6, padding: '4px 8px', cursor: 'pointer', color: 'var(--text-secondary)',
        }}><RefreshCw size={14} /></button>
      </div>

      {loading && <div className="spinner" style={{margin:'20px auto'}} />}

      {/* Connected via USB */}
      <div>
        <h4 style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8, marginTop: 0 }}>
          USB Serial ({ports.filter(p => p.is_esp).length} ESP / {ports.length} total)
        </h4>
        {ports.length === 0 && !loading && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 12 }}>
            No serial ports detected. Connect an ESP device via USB.
          </div>
        )}
        {ports.map(p => (
          <div key={p.device} style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
            marginBottom: 4, borderRadius: 8, fontSize: 12,
            background: p.is_esp ? 'rgba(74,222,128,0.05)' : 'var(--bg-card)',
            border: p.is_esp ? '1px solid rgba(74,222,128,0.2)' : '1px solid var(--border-color)',
          }}>
            {p.is_esp ? <Cpu size={14} color="#4ade80" /> : <MonitorSmartphone size={14} color="var(--text-muted)" />}
            <code style={{ color: 'var(--text-primary)', fontSize: 11 }}>{p.device}</code>
            <span style={{ color: 'var(--text-muted)', flex: 1 }}>{p.description}</span>
            {p.chip && <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: '#1a3a2a', color: '#4ade80' }}>{p.chip}</span>}
            {p.vid && <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'monospace' }}>{p.vid}:{p.pid}</span>}
          </div>
        ))}
      </div>

      {/* Fleet registry */}
      <div>
        <h4 style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8, marginTop: 0 }}>
          Fleet Registry ({fleetDevices.length} paired)
        </h4>
        {fleetDevices.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 12 }}>
            No devices in fleet registry. Pair devices via Edge Fleet page.
          </div>
        )}
        {fleetDevices.slice(0, 10).map(d => (
          <div key={d.id} style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
            marginBottom: 4, borderRadius: 8, fontSize: 12,
            background: 'var(--bg-card)', border: '1px solid var(--border-color)',
          }}>
            {d.family?.startsWith('esp') ? <Cpu size={14} color="#4ade80" /> : <MonitorSmartphone size={14} color="var(--text-muted)" />}
            <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{d.id}</span>
            <span style={{ color: 'var(--text-muted)' }}>{d.chip || d.family}</span>
            <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontSize: 10 }}>
              {d.transport || '?'} · {d.status || 'unknown'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── ESP-NOW Tab (existing functionality) ───────────────────────────────────
function EspNowPanel() {
  const [examples, setExamples] = useState([]);
  const [selected, setSelected] = useState(null);
  const [buildInfo, setBuildInfo] = useState(null);
  const [binaries, setBinaries] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(apiUrl('/espnow/examples'))
      .then(r => r.ok ? r.json() : Promise.reject('failed'))
      .then(d => setExamples(d.examples || []))
      .catch(() => setExamples([]))
      .finally(() => setLoading(false));
  }, []);

  const loadExample = async (name) => {
    setSelected(name); setBuildInfo(null); setBinaries(null);
    try {
      const [bResp, fResp] = await Promise.all([
        fetch(apiUrl(`/espnow/examples/${name}/build`)).then(r => r.json()),
        fetch(apiUrl(`/espnow/examples/${name}/binaries`)).then(r => r.json()),
      ]);
      setBuildInfo(bResp); setBinaries(fResp);
    } catch { /* ignore */ }
  };

  return (
    <div style={{ display: 'flex', gap: 16 }}>
      <div style={{ flex: 1, maxWidth: 260 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
          <Radio size={16} color="#4ade80" />
          <h4 style={{ margin: 0, fontSize: 13, color: 'var(--text-primary)' }}>{examples.length} Examples</h4>
        </div>
        {loading && <div className="spinner" style={{margin:'20px auto'}} />}
        {examples.map(e => (
          <div key={e.name}
            onClick={() => loadExample(e.name)}
            style={{
              padding: '8px 12px', marginBottom: 4, borderRadius: 8, cursor: 'pointer',
              background: selected === e.name ? 'var(--bg-card-hover)' : 'var(--bg-card)',
              border: selected === e.name ? '1px solid #4ade8066' : '1px solid var(--border-color)',
            }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Cpu size={12} color="#4ade80" />
              <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)' }}>
                {e.name.replace(/_/g, ' ')}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ flex: 2 }}>
        {!selected && <div style={{ color: 'var(--text-muted)', padding: 30, textAlign: 'center', fontSize: 13 }}>
          Select an ESP-NOW example
        </div>}

        {buildInfo && !buildInfo.error && (
          <div style={{ padding: 14, borderRadius: 10, marginBottom: 10, background: 'var(--bg-card)', border: '1px solid var(--border-color)' }}>
            <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>Build · {selected}</h4>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
              Target: {buildInfo.target} · Port: {buildInfo.port} · IDF: {buildInfo.idf_available ? <CheckCircle size={12} style={{display:'inline',color:'#4ade80'}} /> : <XCircle size={12} style={{display:'inline',color:'#f87171'}} />}
            </div>
            {Object.entries(buildInfo.commands || {}).map(([step, cmd]) => (
              <div key={step} style={{ marginBottom: 6 }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>{step}</div>
                <code style={{ fontSize: 10, padding: '4px 8px', borderRadius: 4, background: 'var(--bg-input)', display: 'block', overflowX: 'auto' }}>
                  {cmd}
                </code>
              </div>
            ))}
          </div>
        )}

        {binaries?.built && (
          <div style={{ padding: 14, borderRadius: 10, background: 'var(--bg-card)', border: '1px solid #4ade8044' }}>
            <h4 style={{ margin: '0 0 8px', fontSize: 13, color: '#4ade80' }}>
              <CheckCircle size={14} style={{display:'inline',marginRight:4}} />
              {binaries.count} Binary{binaries.count !== 1 ? 'ies' : 'y'} Built
            </h4>
            {binaries.binaries?.slice(0, 8).map(b => (
              <div key={b.name} style={{ fontSize: 10, fontFamily: 'monospace', padding: '2px 0', color: 'var(--text-secondary)' }}>
                {b.name} · {(b.size / 1024).toFixed(1)} KB
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── IDF Projects Tab ───────────────────────────────────────────────────────
function ProjectsPanel() {
  const [projects, setProjects] = useState([]);
  const [idfStatus, setIdfStatus] = useState(null);
  const [newName, setNewName] = useState('');
  const [template, setTemplate] = useState('blank');
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    try {
      const [pRes, sRes] = await Promise.all([
        fetch(API_BASE + '/api/esp/idf/projects').then(r => r.json()),
        fetch(API_BASE + '/api/esp/idf/status').then(r => r.json()),
      ]);
      setProjects(pRes.projects || []);
      setIdfStatus(sRes);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { refresh(); }, []);

  const createProject = async () => {
    if (!newName.trim() || creating) return;
    setCreating(true);
    try {
      const r = await fetch(API_BASE + `/api/esp/idf/projects?name=${encodeURIComponent(newName.trim())}&template=${template}`, { method: 'POST' });
      if (r.ok) { setNewName(''); refresh(); }
      else { alert('Failed to create project'); }
    } catch { alert('Error creating project'); }
    setCreating(false);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
        padding: '8px 12px', borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--border-color)', fontSize: 12 }}>
        <FolderOpen size={16} color="#4ade80" />
        <span style={{ color: 'var(--text-primary)' }}>ESP-IDF:</span>
        {idfStatus?.idf_available ? (
          <span style={{ color: '#4ade80', display:'flex',alignItems:'center',gap:4 }}><CheckCircle size={12} /> Available</span>
        ) : (
          <span style={{ color: '#f87171', display:'flex',alignItems:'center',gap:4 }}><XCircle size={12} /> Not detected</span>
        )}
        {idfStatus?.idf_version && (
          <code style={{ fontSize:11,color:'var(--text-muted)' }}>{idfStatus.idf_version}</code>
        )}
        <span style={{ color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {projects.length} project{projects.length !== 1 ? 's' : ''}
        </span>
        <button onClick={refresh} style={{
          background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)',
          borderRadius: 6, padding: '4px 8px', cursor: 'pointer', color: 'var(--text-secondary)',
        }}><RefreshCw size={12} /></button>
      </div>

      {/* Create */}
      <div style={{
        display: 'flex', gap: 8, alignItems: 'center',
        padding: '10px 12px', borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--border-color)',
      }}>
        <input value={newName} onChange={e => setNewName(e.target.value)}
          placeholder="project-name"
          style={{
            flex: 1, background: 'var(--bg-input)', color: 'var(--text-primary)',
            border: '1px solid var(--border-color)', borderRadius: 6, padding: '6px 10px',
            fontSize: 12, fontFamily: 'monospace', outline: 'none',
          }}
          onKeyDown={e => e.key === 'Enter' && createProject()} />
        <select value={template} onChange={e => setTemplate(e.target.value)}
          style={{
            background: 'var(--bg-input)', color: 'var(--text-primary)',
            border: '1px solid var(--border-color)', borderRadius: 6, padding: '6px 8px', fontSize: 12,
          }}>
          <option value="blank">Blank</option>
          <option value="blink">Blink</option>
        </select>
        <button onClick={createProject} disabled={!newName.trim() || creating}
          style={{
            background: newName.trim() ? '#4ade80' : 'var(--bg-tertiary)', border: 'none',
            borderRadius: 6, padding: '6px 14px', cursor: newName.trim() ? 'pointer' : 'default',
            color: newName.trim() ? '#000' : 'var(--text-muted)', fontSize: 12, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 4,
          }}>
          <FolderPlus size={14} /> Create
        </button>
      </div>

      {/* Project list */}
      {loading && <div className="spinner" style={{margin:'20px auto'}} />}
      {projects.length === 0 && !loading && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>
          No projects yet. Create one above.
        </div>
      )}
      {projects.map(p => (
        <div key={p.name} style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 14px', borderRadius: 8,
          background: 'var(--bg-card)', border: '1px solid var(--border-color)',
        }}>
          <FolderOpen size={16} color={p.has_cmake ? '#4ade80' : 'var(--text-muted)'} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{p.name}</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'monospace' }}>{p.path}</div>
          </div>
          <div style={{ display: 'flex', gap: 6, fontSize: 10 }}>
            {p.has_cmake && <span style={{ padding: '1px 5px', borderRadius: 4, background: '#1a3a2a', color: '#4ade80' }}>cmake</span>}
            {p.has_main && <span style={{ padding: '1px 5px', borderRadius: 4, background: '#1a2a3a', color: '#58a6ff' }}>main</span>}
            {p.has_sdkconfig && <span style={{ padding: '1px 5px', borderRadius: 4, background: '#3a2a1a', color: '#d29922' }}>sdkconfig</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────
export default function EspDevConsole() {
  const [activeTab, setActiveTab] = useState('devices');

  return (
    <div style={{ padding: 24, maxWidth: 1100, display: 'flex', flexDirection: 'column', gap: 16, height: 'calc(100vh - 80px)' }}>
      <div>
        <h2 style={{ margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Cpu size={22} color="#4ade80" />
          ESP Development Console
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: 12, margin: 0 }}>
          Devices · Serial Terminal · ESP-NOW · IDF Projects
        </p>
      </div>

      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: 2, borderBottom: '1px solid var(--border-color)',
        paddingBottom: 0,
      }}>
        {TABS.map(tab => (
          <button key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', border: 'none', borderBottom: activeTab === tab.id ? '2px solid #4ade80' : '2px solid transparent',
              background: 'transparent', cursor: 'pointer',
              color: activeTab === tab.id ? '#4ade80' : 'var(--text-muted)',
              fontSize: 12, fontWeight: 500, transition: 'color 0.15s',
            }}>
            <tab.icon size={14} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {activeTab === 'devices' && <DevicesPanel />}
        {activeTab === 'terminal' && <SerialTerminal />}
        {activeTab === 'espnow' && <EspNowPanel />}
        {activeTab === 'projects' && <ProjectsPanel />}
      </div>
    </div>
  );
}
