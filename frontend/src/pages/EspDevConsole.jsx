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

// ── Firmware Templates Tab ─────────────────────────────────────────────────
function FirmwarePanel() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(API_BASE + '/esp/firmware-templates')
      .then(r => r.ok ? r.json() : { templates: [] })
      .then(d => setTemplates(d.templates || []))
      .catch(() => setTemplates([]))
      .finally(() => setLoading(false));
  }, []);

  const categories = [...new Set(templates.map(t => t.category_label))];

  const catIcons = {
    'ESP-NOW': <Radio size={14} color="#4ade80" />,
    'Firmware': <Download size={14} color="#d29922" />,
    'Template': <Zap size={14} color="#58a6ff" />,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Download size={18} color="#4ade80" />
        <h3 style={{ margin: 0, fontSize: 16, color: 'var(--text-primary)' }}>Firmware Templates</h3>
      </div>

      {loading && <div className="spinner" style={{margin:'20px auto'}} />}

      {categories.map(cat => (
        <div key={cat}>
          <h4 style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8, marginTop: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
            {catIcons[cat] || <Zap size={14} />}
            {cat} ({templates.filter(t => t.category_label === cat).length})
          </h4>
          {templates.filter(t => t.category_label === cat).map(t => (
            <div key={t.id} style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
              marginBottom: 6, borderRadius: 8,
              background: 'var(--bg-card)', border: '1px solid var(--border-color)',
            }}>
              <Download size={16} color={t.category === 'firmware' ? '#d29922' : '#4ade80'} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                  {t.name}
                  {t.category === 'firmware' && (
                    <span style={{ fontSize: 10, marginLeft: 8, padding: '1px 6px', borderRadius: 4, background: '#3a2a1a', color: '#d29922' }}>
                      {t.modes} modes
                    </span>
                  )}
                  {t.license && (
                    <span style={{ fontSize: 10, marginLeft: 4, padding: '1px 6px', borderRadius: 4, background: '#1a2a3a', color: '#58a6ff' }}>
                      {t.license}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                  {t.description}
                </div>
                {t.boards && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                    {t.boards.slice(0, 5).map(b => (
                      <span key={b} style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'var(--bg-tertiary)', color: 'var(--text-muted)' }}>
                        {b}
                      </span>
                    ))}
                    {t.boards.length > 5 && (
                      <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>+{t.boards.length - 5} more</span>
                    )}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 4, flexDirection: 'column', alignItems: 'flex-end' }}>
                {t.wiki && (
                  <a href={t.wiki} target="_blank" rel="noopener noreferrer" style={{ fontSize: 10, color: '#58a6ff', textDecoration: 'none' }}>
                    Wiki →
                  </a>
                )}
                <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                  {t.actions?.map(a => (
                    <span key={a} style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: '#1a3a2a', color: '#4ade80' }}>
                      {a}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      ))}

      {!loading && templates.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>
          No firmware templates available. Add firmware sources to libraries/ or use ESP-IDF projects.
        </div>
      )}
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
        {activeTab === 'firmware' && <FirmwarePanel />}
        {activeTab === 'projects' && <ProjectsPanel />}
      </div>
    </div>
  );
}
