import { useState, useEffect, useRef, useCallback } from 'react';
import { apiUrl, API_BASE } from '../api/client';
import {
  Cpu, Terminal, Zap, Radio, FolderOpen, MonitorSmartphone,
  RefreshCw, Play, Square, Wifi, WifiOff, CheckCircle,
  XCircle, Download, Upload, FolderPlus, Trash2, Send, AlertCircle, Link2,
} from 'lucide-react';

// ── Tabs ──────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'devices', label: 'Devices', icon: MonitorSmartphone },
  { id: 'terminal', label: 'Terminal', icon: Terminal },
  { id: 'espnow', label: 'ESP-NOW', icon: Radio },
  { id: 'firmware', label: 'Firmware', icon: Download },
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
      const r = await fetch(API_BASE + '/esp/serial-ports');
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
    term.writeln('\x1b[1;36m║     NPU-STACK Serial Terminal            ║');
    term.writeln('\x1b[1;36m║     Select a port and click Connect      ║');
    term.writeln('\x1b[1;36m╚══════════════════════════════════════════╝\x1b[0m\r\n');

    const handleResize = () => { try { fitAddon.fit(); } catch {} };
    window.addEventListener('resize', handleResize);
    return () => { window.removeEventListener('resize', handleResize); term.dispose(); };
  }, [xtermReady]);

  const connect = async () => {
    if (!selectedPort || !termInstance.current) return;
    const term = termInstance.current;

    const wsUrl = (API_BASE.replace('http', 'ws')) + `/esp/terminal/${encodeURIComponent(selectedPort)}?baud=115200`;
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
function DevicesPanel({ selectedDevice, onSelectDevice, fleetDevices, setFleetDevices }) {
  const [ports, setPorts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pairingId, setPairingId] = useState(null);
  const [fleetFlashable, setFleetFlashable] = useState([]);

  const refresh = async () => {
    setLoading(true);
    try {
      const [pRes, dRes, fRes] = await Promise.all([
        fetch(API_BASE + '/esp/serial-ports').then(r => r.json()),
        fetch(API_BASE + '/devices').then(r => r.ok ? r.json() : { devices: [] }),
        fetch(API_BASE + '/esp/fleet-devices').then(r => r.ok ? r.json() : { devices: [] }),
      ]);
      setPorts(pRes.ports || []);
      setFleetDevices(Array.isArray(dRes?.devices) ? dRes.devices : []);
      setFleetFlashable(Array.isArray(fRes?.devices)
        ? fRes.devices.filter(d => d.flash_method !== 'unknown')
        : []);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { refresh(); }, []);

  const pairSerialDevice = async (portInfo) => {
    if (pairingId) return;
    setPairingId(portInfo.device);
    try {
      const scanResp = await fetch(API_BASE + `/devices/scan?serial=${encodeURIComponent(portInfo.device)}`, { method: 'POST' });
      if (!scanResp.ok) throw new Error('Scan failed');
      const scanData = await scanResp.json();
      const found = (scanData.devices || []).find(d => d.connection === 'serial' || d.port === portInfo.device);
      if (found) {
        await fetch(API_BASE + `/devices/${encodeURIComponent(found.id)}/pair`, { method: 'POST' });
      }
      // Full refresh
      const [dRes, fRes] = await Promise.all([
        fetch(API_BASE + '/devices').then(r => r.json()),
        fetch(API_BASE + '/esp/fleet-devices').then(r => r.json()),
      ]);
      setFleetDevices(Array.isArray(dRes?.devices) ? dRes.devices : []);
      setFleetFlashable(Array.isArray(fRes?.devices)
        ? fRes.devices.filter(d => d.flash_method !== 'unknown')
        : []);
    } catch (e) { console.warn('Pair failed:', e); }
    setPairingId(null);
  };

  const badgeColors = {
    esptool: { bg: '#1a3a2a', fg: '#4ade80' },
    uf2: { bg: '#1a2a3a', fg: '#58a6ff' },
    rockusb: { bg: '#3a2a1a', fg: '#d29922' },
    scp: { bg: '#2a1a3a', fg: '#bc8cff' },
    fel: { bg: '#1a2a2a', fg: '#56d4dd' },
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <MonitorSmartphone size={18} color="#4ade80" />
        <h3 style={{ margin: 0, fontSize: 16, color: 'var(--text-primary)' }}>Edge Devices</h3>
        <button onClick={refresh} style={{
          background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)',
          borderRadius: 6, padding: '4px 8px', cursor: 'pointer', color: 'var(--text-secondary)',
        }}><RefreshCw size={14} /></button>
        {selectedDevice && (
          <span style={{ marginLeft: 12, fontSize: 11, color: '#4ade80', display: 'flex', alignItems: 'center', gap: 4 }}>
            <CheckCircle size={12} /> Target: {selectedDevice}
          </span>
        )}
      </div>

      {loading && <div className="spinner" style={{margin:'20px auto'}} />}

      {/* ── Fleet Quick-Select (paired/flashable) ── */}
      {fleetFlashable.length > 0 && (
        <div>
          <h4 style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8, marginTop: 0 }}>
            <Link2 size={12} style={{verticalAlign:'middle',marginRight:4}} />
            Fleet Quick-Select ({fleetFlashable.length} flashable)
          </h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {fleetFlashable.slice(0, 12).map(d => {
              const bc = badgeColors[d.flash_method] || { bg: '#1a2035', fg: '#718096' };
              return (
                <button key={d.id}
                  onClick={() => onSelectDevice(selectedDevice === d.id ? null : d.id)}
                  style={{
                    padding: '5px 10px', borderRadius: 8, cursor: 'pointer', fontSize: 11,
                    background: selectedDevice === d.id ? 'rgba(74,222,128,0.12)' : 'var(--bg-card)',
                    border: selectedDevice === d.id ? '1px solid #4ade80' : '1px solid var(--border-color)',
                    color: 'var(--text-primary)', textAlign: 'left',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}>
                  <Cpu size={12} color={bc.fg} />
                  <span>{d.nickname || d.id}</span>
                  <span style={{ fontSize: 9, padding: '0px 4px', borderRadius: 3, background: bc.bg, color: bc.fg }}>
                    {d.toolchain}
                  </span>
                  {selectedDevice === d.id && <CheckCircle size={12} color="#4ade80" />}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── USB Serial ── */}
      <div>
        <h4 style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8, marginTop: 0 }}>
          USB Serial ({ports.filter(p => p.flash_method !== 'unknown').length} flashable / {ports.length} total)
        </h4>
        {ports.length === 0 && !loading && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 12 }}>
            No serial ports detected. Connect a device via USB.
          </div>
        )}
        {ports.map(p => {
          const isFlashable = p.flash_method && p.flash_method !== 'unknown';
          const bc = badgeColors[p.flash_method] || { bg: '#1a2035', fg: '#718096' };
          const alreadyInFleet = fleetDevices.some(d => d.port === p.device || d.id === p.serial_number);
          return (
            <div key={p.device} style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
              marginBottom: 4, borderRadius: 8, fontSize: 12,
              cursor: isFlashable ? 'pointer' : 'default',
              background: selectedDevice === p.device ? 'rgba(74,222,128,0.1)' : (isFlashable ? 'rgba(74,222,128,0.03)' : 'var(--bg-card)'),
              border: selectedDevice === p.device ? '1px solid #4ade80' : (isFlashable ? '1px solid rgba(74,222,128,0.15)' : '1px solid var(--border-color)'),
            }}
            onClick={() => isFlashable && onSelectDevice(selectedDevice === p.device ? null : p.device)}>
              {isFlashable ? <Cpu size={14} color={bc.fg} /> : <MonitorSmartphone size={14} color="var(--text-muted)" />}
              <code style={{ color: 'var(--text-primary)', fontSize: 11 }}>{p.device}</code>
              <span style={{ color: 'var(--text-muted)', flex: 1 }}>{p.description}</span>
              {isFlashable && (
                <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: bc.bg, color: bc.fg }}>
                  {p.toolchain}
                </span>
              )}
              {p.chip && <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: '#1a3a2a', color: '#4ade80' }}>{p.chip}</span>}
              {p.vid && <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'monospace' }}>{p.vid}:{p.pid}</span>}
              {isFlashable && !alreadyInFleet && (
                <button
                  onClick={(e) => { e.stopPropagation(); pairSerialDevice(p); }}
                  disabled={pairingId === p.device}
                  title="Pair with fleet registry"
                  style={{
                    background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)',
                    borderRadius: 6, padding: '2px 8px', cursor: 'pointer',
                    color: 'var(--text-secondary)', fontSize: 10, display: 'flex', alignItems: 'center', gap: 3,
                  }}>
                  <Link2 size={10} />
                  {pairingId === p.device ? 'Pairing...' : 'Pair'}
                </button>
              )}
              {alreadyInFleet && <Link2 size={12} color="#4ade80" title="Already in fleet" />}
              {selectedDevice === p.device && <CheckCircle size={14} color="#4ade80" />}
            </div>
          );
        })}
      </div>

      {/* ── Fleet ESP Devices ── */}
      <div>
        <h4 style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8, marginTop: 0 }}>
          Fleet ESP Devices ({fleetDevices.filter(d => d.family?.startsWith('esp') || d.chip?.toLowerCase().includes('esp')).length} ESP in fleet)
        </h4>
        {fleetDevices.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 12 }}>
            No devices in fleet registry. Pair devices via Edge Fleet or use the Pair button above.
          </div>
        )}
        {fleetDevices.slice(0, 20).map(d => {
          const isEspFamily = d.family?.startsWith('esp') || d.chip?.toLowerCase().includes('esp');
          return (
            <div key={d.id} style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
              marginBottom: 4, borderRadius: 8, fontSize: 12, cursor: 'pointer',
              background: selectedDevice === d.id ? 'rgba(74,222,128,0.1)' : (isEspFamily ? 'rgba(74,222,128,0.03)' : 'var(--bg-card)'),
              border: selectedDevice === d.id ? '1px solid #4ade80' : (isEspFamily ? '1px solid rgba(74,222,128,0.15)' : '1px solid var(--border-color)'),
            }}
            onClick={() => onSelectDevice(selectedDevice === d.id ? null : d.id)}>
              {isEspFamily ? <Cpu size={14} color="#4ade80" /> : <MonitorSmartphone size={14} color="var(--text-muted)" />}
              <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{d.nickname || d.id}</span>
              <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>{d.chip || d.family}</span>
              {d.ip && <span style={{ color: 'var(--text-muted)', fontSize: 10, fontFamily: 'monospace' }}>{d.ip}</span>}
              <span style={{ color: d.paired ? '#4ade80' : 'var(--text-muted)', marginLeft: 'auto', fontSize: 10, display: 'flex', alignItems: 'center', gap: 3 }}>
                {d.paired && <Link2 size={9} />}
                {d.paired ? 'paired' : (d.status || 'detected')}
              </span>
              {selectedDevice === d.id && <CheckCircle size={14} color="#4ade80" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── ESP-NOW Tab ─────────────────────────────────────────────────────────────
function EspNowPanel({ selectedDevice }) {
  const [examples, setExamples] = useState([]);
  const [selected, setSelected] = useState(null);
  const [buildInfo, setBuildInfo] = useState(null);
  const [binaries, setBinaries] = useState(null);
  const [loading, setLoading] = useState(true);
  const [flashing, setFlashing] = useState(false);
  const [flashResult, setFlashResult] = useState(null);

  useEffect(() => {
    fetch(apiUrl('/espnow/examples'))
      .then(r => r.ok ? r.json() : Promise.reject('failed'))
      .then(d => setExamples(d.examples || []))
      .catch(() => setExamples([]))
      .finally(() => setLoading(false));
  }, []);

  const loadExample = async (name) => {
    setSelected(name); setBuildInfo(null); setBinaries(null); setFlashResult(null);
    try {
      const [bResp, fResp] = await Promise.all([
        fetch(apiUrl(`/espnow/examples/${name}/build`)).then(r => r.json()),
        fetch(apiUrl(`/espnow/examples/${name}/binaries`)).then(r => r.json()),
      ]);
      setBuildInfo(bResp); setBinaries(fResp);
    } catch { /* ignore */ }
  };

  const handleFlash = async () => {
    if (!selected || !selectedDevice || flashing) return;
    setFlashing(true);
    setFlashResult({ status: 'parsing', message: 'Parsing fleet command...' });

    try {
      const nlCommand = `deploy ${selected} espnow firmware to device ${selectedDevice} using target ${buildInfo?.target || 'esp32'}`;

      // 1. Parse
      const parseResp = await fetch(API_BASE + '/fleet/command/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: nlCommand, use_agent: false }),
      });
      if (!parseResp.ok) throw new Error('Fleet parse failed');
      const parsedCmd = await parseResp.json();

      // 2. Execute
      setFlashResult({ status: 'executing', message: 'Dispatching to fleet...', parsed: parsedCmd });
      const execResp = await fetch(API_BASE + '/fleet/command/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parsed_command: parsedCmd, dry_run: false }),
      });
      if (!execResp.ok) throw new Error('Fleet execute failed');
      const result = await execResp.json();

      setFlashResult({
        status: 'queued',
        job_id: result.job_id,
        intent: result.intent,
        target_count: result.target_count,
        message: `Job ${result.job_id} queued. Polling for completion...`,
      });

      // 3. Poll for completion (up to 30s)
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const jobResp = await fetch(API_BASE + `/fleet/command/jobs/${result.job_id}`);
          const job = await jobResp.json();
          setFlashResult(prev => ({
            ...prev,
            job_status: job.status,
            results: job.results_by_device,
            completed: job.completed_at,
            message: `Status: ${job.status}${job.completed_at ? ' (completed)' : ''}`,
          }));
          if (job.status === 'complete' || job.status === 'failed' || attempts > 30) {
            clearInterval(poll);
            setFlashing(false);
          }
        } catch { clearInterval(poll); setFlashing(false); }
      }, 1000);
    } catch (e) {
      setFlashResult({ status: 'error', message: e.message });
      setFlashing(false);
    }
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

        {/* Device selector & deploy bar */}
        {selected && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
            padding: '10px 12px', borderRadius: 8, marginBottom: 10,
            background: 'var(--bg-card)', border: '1px solid var(--border-color)',
          }}>
            <Radio size={14} color="#4ade80" />
            <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>
              {selected.replace(/_/g, ' ')}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', flex: 1 }}>
              {selectedDevice ? `→ ${selectedDevice}` : 'No device selected'}
            </span>
            <button
              onClick={handleFlash}
              disabled={!selectedDevice || flashing}
              style={{
                background: selectedDevice ? (flashing ? '#d29922' : '#4ade80') : 'var(--bg-tertiary)',
                border: 'none', borderRadius: 6, padding: '6px 14px',
                cursor: selectedDevice && !flashing ? 'pointer' : 'default',
                color: selectedDevice ? '#000' : 'var(--text-muted)',
                fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4,
              }}>
              {flashing ? <AlertCircle size={14} /> : <Send size={14} />}
              {flashing ? 'Flashing...' : 'Flash to Device'}
            </button>
          </div>
        )}

        {/* Flash result */}
        {flashResult && (
          <div style={{
            padding: 10, borderRadius: 8, marginBottom: 10, fontSize: 12,
            background: flashResult.status === 'error' ? 'rgba(248,81,73,0.1)' :
              flashResult.job_status === 'complete' ? 'rgba(74,222,128,0.08)' : 'rgba(210,153,34,0.08)',
            border: `1px solid ${flashResult.status === 'error' ? '#f8514966' :
              flashResult.job_status === 'complete' ? '#4ade8066' : '#d2992266'}`,
            color: 'var(--text-primary)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: flashResult.job_id ? 6 : 0 }}>
              {flashResult.status === 'error' ? <XCircle size={14} color="#f85149" /> :
               flashResult.job_status === 'complete' ? <CheckCircle size={14} color="#4ade80" /> :
               <AlertCircle size={14} color="#d29922" />}
              <span>{flashResult.message}</span>
            </div>
            {flashResult.job_id && (
              <code style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                Job: {flashResult.job_id} · Intent: {flashResult.intent} · Targets: {flashResult.target_count}
              </code>
            )}
          </div>
        )}

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

// ── Firmware Tab (REAL flash + backup + detect) ────────────────────────────
function FirmwarePanel({ selectedDevice, fleetDevices }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [backups, setBackups] = useState([]);
  const [flashDevice, setFlashDevice] = useState(selectedDevice || '');
  const [chipInfo, setChipInfo] = useState(null);
  const [detecting, setDetecting] = useState(false);
  const [backingUp, setBackingUp] = useState(false);
  const [flashing, setFlashing] = useState(false);
  const [backupResult, setBackupResult] = useState(null);
  const [flashResult, setFlashResult] = useState(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [fwPath, setFwPath] = useState('');
  const [baudRate, setBaudRate] = useState('921600');
  const [flashOffset, setFlashOffset] = useState('0x0');
  const [selectedTemplate, setSelectedTemplate] = useState(null);

  // Sync selectedDevice from parent
  useEffect(() => {
    if (selectedDevice && !flashDevice) setFlashDevice(selectedDevice);
  }, [selectedDevice]);

  const refreshAll = async () => {
    setLoading(true);
    try {
      const [tRes, bRes] = await Promise.all([
        fetch(API_BASE + '/esp/firmware-templates').then(r => r.ok ? r.json() : { templates: [] }),
        fetch(API_BASE + '/esp/flash/backups').then(r => r.ok ? r.json() : { backups: [] }),
      ]);
      setTemplates(tRes.templates || []);
      setBackups(bRes.backups || []);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { refreshAll(); }, []);

  // ── Detect Chip ──
  const handleDetect = async () => {
    if (!flashDevice || detecting) return;
    setDetecting(true); setChipInfo(null);
    try {
      const r = await fetch(API_BASE + `/esp/flash/detect/${encodeURIComponent(flashDevice)}`);
      const data = await r.json();
      setChipInfo(data);
    } catch (e) {
      setChipInfo({ success: false, error: e.message });
    }
    setDetecting(false);
  };

  // ── Backup Firmware ──
  const handleBackup = async () => {
    if (!flashDevice || backingUp) return;
    setBackingUp(true); setBackupResult(null);
    try {
      const r = await fetch(API_BASE + `/esp/flash/backup/${encodeURIComponent(flashDevice)}?size=4MB`, { method: 'POST' });
      const data = await r.json();
      setBackupResult(data);
      if (data.success) refreshAll(); // refresh backup list
    } catch (e) {
      setBackupResult({ success: false, error: e.message });
    }
    setBackingUp(false);
  };

  // ── Flash Firmware (with confirm) ──
  const triggerFlash = () => {
    if (!flashDevice) return;
    setShowConfirm(true);
    setPendingAction('flash');
  };

  const confirmFlash = async () => {
    setShowConfirm(false);
    if (!flashDevice || flashing) return;
    setFlashing(true); setFlashResult(null);
    try {
      const params = new URLSearchParams({
        firmware_path: fwPath || 'auto-detect',
        offset: flashOffset,
        baud: baudRate,
        backup_first: 'true',
      });
      const r = await fetch(API_BASE + `/esp/flash/write/${encodeURIComponent(flashDevice)}?${params}`, { method: 'POST' });
      const data = await r.json();
      setFlashResult(data);
      if (data.backup?.success) setBackupResult(data.backup);
    } catch (e) {
      setFlashResult({ success: false, error: e.message });
    }
    setFlashing(false);
  };

  const cancelAction = () => {
    setShowConfirm(false);
    setPendingAction(null);
  };

  // Build list of flashable devices for quick-select
  const flashableDevices = fleetDevices.filter(d =>
    d.family?.startsWith('esp') || d.chip?.toLowerCase().includes('esp') || d.family === 'rp2040' || d.family === 'rp2350'
  );

  const categories = [...new Set(templates.map(t => t.category_label))];
  const catIcons = {
    'ESP-NOW': <Radio size={14} color="#4ade80" />,
    'Firmware': <Download size={14} color="#d29922" />,
    'Template': <Zap size={14} color="#58a6ff" />,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* ── Device Selector & Actions ── */}
      <div style={{
        padding: 14, borderRadius: 10, background: 'var(--bg-card)',
        border: '2px solid #4ade8066',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <Download size={18} color="#4ade80" />
          <h3 style={{ margin: 0, fontSize: 16, color: 'var(--text-primary)' }}>Flash & Backup</h3>
          <span style={{ fontSize: 10, color: '#4ade80', marginLeft: 'auto', padding: '2px 8px', borderRadius: 4, background: '#1a3a2a' }}>
            REAL esptool · mpremote · ampy
          </span>
        </div>

        {/* Device select */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
          <select value={flashDevice} onChange={e => setFlashDevice(e.target.value)}
            style={{
              background: 'var(--bg-input)', color: 'var(--text-primary)',
              border: '1px solid var(--border-color)', borderRadius: 6, padding: '6px 10px',
              fontSize: 12, minWidth: 220, fontFamily: 'monospace',
            }}>
            <option value="">-- Select device port --</option>
            {flashableDevices.map(d => (
              <option key={d.id} value={d.port || d.id}>
                {d.port || d.id} {d.chip ? `(${d.chip})` : ''}
              </option>
            ))}
          </select>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>or</span>
          <input value={flashDevice} onChange={e => setFlashDevice(e.target.value)}
            placeholder="COM3 or /dev/ttyUSB0"
            style={{
              background: 'var(--bg-input)', color: 'var(--text-primary)',
              border: '1px solid var(--border-color)', borderRadius: 6, padding: '6px 10px',
              fontSize: 12, fontFamily: 'monospace', width: 160, outline: 'none',
            }} />
          {flashDevice && (
            <span style={{ fontSize: 11, color: '#4ade80', display: 'flex', alignItems: 'center', gap: 4 }}>
              <CheckCircle size={12} /> {flashDevice}
            </span>
          )}
        </div>

        {/* Action buttons row */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button onClick={handleDetect} disabled={!flashDevice || detecting}
            style={{
              background: flashDevice ? '#58a6ff' : 'var(--bg-tertiary)',
              border: 'none', borderRadius: 6, padding: '8px 16px',
              cursor: flashDevice && !detecting ? 'pointer' : 'default',
              color: flashDevice ? '#fff' : 'var(--text-muted)',
              fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6,
            }}>
            {detecting ? <RefreshCw size={14} style={{animation:'spin 1s linear infinite'}} /> : <Cpu size={14} />}
            {detecting ? 'Detecting...' : 'Detect Chip'}
          </button>

          <button onClick={handleBackup} disabled={!flashDevice || backingUp}
            style={{
              background: flashDevice ? '#d29922' : 'var(--bg-tertiary)',
              border: 'none', borderRadius: 6, padding: '8px 16px',
              cursor: flashDevice && !backingUp ? 'pointer' : 'default',
              color: flashDevice ? '#000' : 'var(--text-muted)',
              fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6,
            }}>
            {backingUp ? <RefreshCw size={14} style={{animation:'spin 1s linear infinite'}} /> : <Upload size={14} />}
            {backingUp ? 'Backing up...' : 'Backup Firmware'}
          </button>

          <button onClick={triggerFlash} disabled={!flashDevice || flashing}
            style={{
              background: flashDevice ? (flashing ? '#d29922' : '#ef4444') : 'var(--bg-tertiary)',
              border: 'none', borderRadius: 6, padding: '8px 16px',
              cursor: flashDevice && !flashing ? 'pointer' : 'default',
              color: '#fff', fontSize: 12, fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
            {flashing ? <RefreshCw size={14} style={{animation:'spin 1s linear infinite'}} /> : <Send size={14} />}
            {flashing ? 'Flashing...' : 'Flash Firmware'}
          </button>

          <button onClick={refreshAll} style={{
            background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)',
            borderRadius: 6, padding: '8px 12px', cursor: 'pointer', color: 'var(--text-secondary)',
          }}><RefreshCw size={14} /></button>
        </div>

        {/* Flash options (advanced) */}
        {flashDevice && (
          <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap', fontSize: 11 }}>
            <label style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
              Path: <input value={fwPath} onChange={e => setFwPath(e.target.value)}
                placeholder="firmware.bin"
                style={{
                  background: 'var(--bg-input)', color: 'var(--text-primary)', border: '1px solid var(--border-color)',
                  borderRadius: 4, padding: '3px 8px', fontSize: 11, fontFamily: 'monospace', width: 180, outline: 'none',
                }} />
            </label>
            <label style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
              Offset: <input value={flashOffset}
                onChange={e => setFlashOffset(e.target.value)}
                style={{
                  background: 'var(--bg-input)', color: 'var(--text-primary)', border: '1px solid var(--border-color)',
                  borderRadius: 4, padding: '3px 6px', fontSize: 11, fontFamily: 'monospace', width: 70, outline: 'none',
                }} />
            </label>
            <label style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
              Baud: <select value={baudRate} onChange={e => setBaudRate(e.target.value)}
                style={{
                  background: 'var(--bg-input)', color: 'var(--text-primary)', border: '1px solid var(--border-color)',
                  borderRadius: 4, padding: '3px 6px', fontSize: 11,
                }}>
                {['921600','460800','230400','115200'].map(b => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </select>
            </label>
          </div>
        )}
      </div>

      {/* ── CONFIRM DIALOG ── */}
      {showConfirm && (
        <div style={{
          padding: 16, borderRadius: 10, background: 'rgba(239,68,68,0.08)',
          border: '2px solid #ef4444', animation: 'fadeIn 0.2s',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <AlertCircle size={20} color="#ef4444" />
            <h4 style={{ margin: 0, fontSize: 15, color: '#ef4444' }}>Confirm Flash</h4>
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '0 0 6px' }}>
            You are about to <strong style={{color:'#ef4444'}}>flash firmware</strong> to <code style={{background:'var(--bg-input)',padding:'2px 6px',borderRadius:3}}>{flashDevice}</code>.
          </p>
          <p style={{ fontSize: 11, color: '#d29922', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 4 }}>
            <CheckCircle size={12} /> A backup will be created automatically before flashing.
          </p>
          {!fwPath && (
            <p style={{ fontSize: 11, color: '#f87171', margin: '0 0 12px' }}>
              ⚠ No firmware path specified — this will fail. Enter a firmware .bin path above.
            </p>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={confirmFlash}
              style={{
                background: '#ef4444', border: 'none', borderRadius: 6, padding: '8px 20px',
                cursor: 'pointer', color: '#fff', fontSize: 13, fontWeight: 700,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
              <Send size={14} /> Flash Now (with backup)
            </button>
            <button onClick={cancelAction}
              style={{
                background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)',
                borderRadius: 6, padding: '8px 20px', cursor: 'pointer',
                color: 'var(--text-secondary)', fontSize: 13,
              }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ── Chip Info Result ── */}
      {chipInfo && (
        <div style={{
          padding: 12, borderRadius: 8,
          background: chipInfo.success ? 'rgba(74,222,128,0.05)' : 'rgba(248,81,73,0.05)',
          border: `1px solid ${chipInfo.success ? '#4ade8044' : '#f8514944'}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            {chipInfo.success ? <CheckCircle size={14} color="#4ade80" /> : <XCircle size={14} color="#f85149" />}
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              {chipInfo.success ? 'Chip Detected' : 'Detection Failed'}
            </span>
            <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 'auto' }}>
              {chipInfo.timestamp}
            </span>
          </div>
          <pre style={{
            fontSize: 10, fontFamily: 'monospace', color: 'var(--text-secondary)',
            margin: 0, padding: '8px', background: 'var(--bg-input)', borderRadius: 6,
            maxHeight: 200, overflowY: 'auto', whiteSpace: 'pre-wrap',
          }}>
            {chipInfo.output || chipInfo.error || 'No output'}
          </pre>
        </div>
      )}

      {/* ── Backup Result ── */}
      {backupResult && (
        <div style={{
          padding: 12, borderRadius: 8,
          background: backupResult.success ? 'rgba(210,153,34,0.05)' : 'rgba(248,81,73,0.05)',
          border: `1px solid ${backupResult.success ? '#d2992244' : '#f8514944'}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {backupResult.success ? <CheckCircle size={14} color="#d29922" /> : <XCircle size={14} color="#f85149" />}
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              {backupResult.success
                ? `Backup saved: ${backupResult.backup_size_mb || '?'} MB`
                : 'Backup Failed'}
            </span>
          </div>
          {backupResult.backup_path && (
            <code style={{ fontSize: 10, color: 'var(--text-muted)', display: 'block', marginTop: 4 }}>
              {backupResult.backup_path}
            </code>
          )}
          {backupResult.error && (
            <div style={{ fontSize: 11, color: '#f87171', marginTop: 4 }}>{backupResult.error}</div>
          )}
        </div>
      )}

      {/* ── Flash Result ── */}
      {flashResult && (
        <div style={{
          padding: 12, borderRadius: 8,
          background: flashResult.success ? 'rgba(74,222,128,0.05)' : 'rgba(248,81,73,0.05)',
          border: `1px solid ${flashResult.success ? '#4ade8044' : '#f8514944'}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: flashResult.output ? 8 : 0 }}>
            {flashResult.success ? <CheckCircle size={16} color="#4ade80" /> : <XCircle size={16} color="#f85149" />}
            <span style={{ fontSize: 14, fontWeight: 700, color: flashResult.success ? '#4ade80' : '#f85149' }}>
              {flashResult.success ? '✓ Flash Complete!' : '✗ Flash Failed'}
            </span>
            {flashResult.backup?.success && (
              <span style={{ fontSize: 10, color: '#d29922', marginLeft: 8 }}>
                Backup: {flashResult.backup.backup_size_mb} MB
              </span>
            )}
          </div>
          {flashResult.output && (
            <pre style={{
              fontSize: 10, fontFamily: 'monospace', color: 'var(--text-secondary)',
              margin: 0, padding: '8px', background: 'var(--bg-input)', borderRadius: 6,
              maxHeight: 200, overflowY: 'auto', whiteSpace: 'pre-wrap',
            }}>
              {flashResult.output}
            </pre>
          )}
          {flashResult.error && (
            <div style={{ fontSize: 11, color: '#f87171', marginTop: 4 }}>{flashResult.error}</div>
          )}
        </div>
      )}

      {/* ── Backup List ── */}
      <div>
        <h4 style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8, marginTop: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Upload size={14} color="#d29922" />
          Saved Backups ({backups.length})
        </h4>
        {backups.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 12px' }}>
            No backups yet. Connect a device and click "Backup Firmware".
          </div>
        ) : (
          backups.slice(0, 10).map(b => (
            <div key={b.name} style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
              marginBottom: 4, borderRadius: 6, fontSize: 11,
              background: 'var(--bg-card)', border: '1px solid var(--border-color)',
            }}>
              <Upload size={12} color="#d29922" />
              <code style={{ color: 'var(--text-primary)', flex: 1 }}>{b.name}</code>
              <span style={{ color: 'var(--text-muted)' }}>{b.size_mb} MB</span>
              <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>{new Date(b.created).toLocaleDateString()}</span>
            </div>
          ))
        )}
      </div>

      {/* ── Templates list ── */}
      <div>
        <h4 style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8, marginTop: 0 }}>
          <Zap size={14} style={{verticalAlign:'middle',marginRight:4}} />
          Firmware Templates ({templates.length})
        </h4>
        {loading && <div className="spinner" style={{margin:'20px auto'}} />}
        {categories.map(cat => (
          <div key={cat}>
            <h5 style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6, marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
              {catIcons[cat] || <Zap size={12} />}
              {cat} ({templates.filter(t => t.category_label === cat).length})
            </h5>
            {templates.filter(t => t.category_label === cat).map(t => (
              <div key={t.id} style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
                marginBottom: 4, borderRadius: 6, fontSize: 12, cursor: 'pointer',
                background: selectedTemplate === t.id ? 'rgba(74,222,128,0.1)' : 'var(--bg-card)',
                border: selectedTemplate === t.id ? '1px solid #4ade80' : '1px solid var(--border-color)',
              }}
              onClick={() => { setSelectedTemplate(selectedTemplate === t.id ? null : t.id); }}>
                <Download size={14} color={t.category === 'firmware' ? '#d29922' : '#4ade80'} />
                <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{t.name}</span>
                <span style={{ color: 'var(--text-muted)', fontSize: 10, flex: 1 }}>{t.description?.substring(0, 50)}</span>
                {t.boards && (
                  <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>{t.boards.length} boards</span>
                )}
              </div>
            ))}
          </div>
        ))}
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
        fetch(API_BASE + '/esp/idf/projects').then(r => r.json()),
        fetch(API_BASE + '/esp/idf/status').then(r => r.json()),
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
      const r = await fetch(API_BASE + `/esp/idf/projects?name=${encodeURIComponent(newName.trim())}&template=${template}`, { method: 'POST' });
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
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [fleetDevices, setFleetDevices] = useState([]);

  return (
    <div style={{ padding: 24, maxWidth: 1100, display: 'flex', flexDirection: 'column', gap: 16, height: 'calc(100vh - 80px)' }}>
      <div>
        <h2 style={{ margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Cpu size={22} color="#4ade80" />
          ESP Development Console
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: 12, margin: 0 }}>
          Devices · Serial Terminal · ESP-NOW · IDF Projects
          {selectedDevice && <span style={{ color: '#4ade80' }}> — Target: {selectedDevice}</span>}
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
        {activeTab === 'devices' && (
          <DevicesPanel
            selectedDevice={selectedDevice}
            onSelectDevice={setSelectedDevice}
            fleetDevices={fleetDevices}
            setFleetDevices={setFleetDevices}
          />
        )}
        {activeTab === 'terminal' && <SerialTerminal />}
        {activeTab === 'espnow' && <EspNowPanel selectedDevice={selectedDevice} />}
        {activeTab === 'firmware' && <FirmwarePanel selectedDevice={selectedDevice} fleetDevices={fleetDevices} />}
        {activeTab === 'projects' && <ProjectsPanel />}
      </div>
    </div>
  );
}
