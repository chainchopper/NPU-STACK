import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Play, Square, RefreshCw, Smartphone, MonitorSmartphone } from 'lucide-react';
import { API_BASE } from '../api/client';

// Build a WebSocket URL for the emulator from the current origin + API_BASE.
function emulatorWsUrl() {
    let base = API_BASE; // e.g. http://host:8010/api or /api
    let origin = window.location.origin;
    if (/^https?:/i.test(base)) {
        const u = new URL(base);
        origin = u.origin;
    }
    const wsProto = origin.startsWith('https') ? 'wss' : 'ws';
    const host = origin.replace(/^https?:\/\//, '');
    return `${wsProto}://${host}/api/emulator/ws`;
}

const CANVAS = 240;

function rgb565ToRgba(src) {
    // src: ArrayBuffer of RGB565 bytes (length CANVAS*CANVAS*2)
    const view = new Uint8Array(src);
    const out = new Uint8ClampedArray(CANVAS * CANVAS * 4);
    let i = 0;
    let o = 0;
    for (let p = 0; p < CANVAS * CANVAS; p++) {
        const hi = view[i++];
        const lo = view[i++];
        const c = (hi << 8) | lo;
        const r = ((c >> 11) & 0x1f) << 3;
        const g = ((c >> 5) & 0x3f) << 2;
        const b = (c & 0x1f) << 3;
        out[o++] = r; out[o++] = g; out[o++] = b; out[o++] = 255;
    }
    return new ImageData(out, CANVAS, CANVAS);
}

export default function DevicePlayground() {
    const canvasRef = useRef(null);
    const wsRef = useRef(null);
    const [code, setCode] = useState('');
    const [examples, setExamples] = useState([]);
    const [running, setRunning] = useState(false);
    const [connected, setConnected] = useState(false);
    const [logs, setLogs] = useState([]);
    const [selectedId, setSelectedId] = useState('hello');

    const pushLog = useCallback((text) => {
        setLogs((prev) => [...prev.slice(-200), text]);
    }, []);

    const stop = useCallback(() => {
        if (wsRef.current) {
            try { wsRef.current.send(JSON.stringify({ type: 'stop' })); } catch { /* ignore */ }
            try { wsRef.current.close(); } catch { /* ignore */ }
            wsRef.current = null;
        }
        setRunning(false);
        setConnected(false);
    }, []);

    const run = useCallback(() => {
        stop();
        setLogs([]);
        const ws = new WebSocket(emulatorWsUrl());
        wsRef.current = ws;
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
            setConnected(true);
            setRunning(true);
            ws.send(JSON.stringify({ type: 'run', code }));
        };
        ws.onmessage = (ev) => {
            if (typeof ev.data === 'string') {
                try {
                    const msg = JSON.parse(ev.data);
                    if (msg.type === 'log') pushLog(msg.text);
                } catch { /* ignore */ }
                return;
            }
            // binary frame → render to canvas
            const canvas = canvasRef.current;
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            try {
                const img = rgb565ToRgba(ev.data);
                // Round the corners of the square canvas to mimic the round LCD.
                ctx.putImageData(img, 0, 0);
            } catch (e) {
                pushLog('render error: ' + e.message);
            }
        };
        ws.onclose = () => {
            setRunning(false);
            setConnected(false);
            wsRef.current = null;
        };
        ws.onerror = () => {
            pushLog('emulator connection error (backend running?)');
        };
    }, [code, pushLog, stop]);

    useEffect(() => () => stop(), [stop]);

    useEffect(() => {
        fetch(`${API_BASE}/emulator/examples`)
            .then((r) => r.json())
            .then((data) => {
                const apps = data.apps || [];
                setExamples(apps);
                const sel = apps.find((a) => a.id === selectedId) || apps[0];
                if (sel) setCode(sel.code);
            })
            .catch(() => pushLog('could not load example apps'));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const selectExample = (id) => {
        setSelectedId(id);
        const app = examples.find((a) => a.id === id);
        if (app) setCode(app.code);
    };

    const onCanvasPointer = (ev) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        const scaleX = CANVAS / rect.width;
        const scaleY = CANVAS / rect.height;
        const x = Math.round((ev.clientX - rect.left) * scaleX);
        const y = Math.round((ev.clientY - rect.top) * scaleY);
        if (wsRef.current && connected) {
            wsRef.current.send(JSON.stringify({ type: 'touch', x, y }));
        }
        pushLog(`touch @ ${x},${y}`);
    };

    return (
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <Smartphone size={22} color="#667eea" />
                <div>
                    <h2 style={{ margin: 0, fontSize: 18 }}>Device Playground</h2>
                    <div style={{ fontSize: 12, color: '#718096' }}>
                        Preview & test Nirvana OS apps in a virtual XIAO round display — same code, same pixels.
                    </div>
                </div>
            </div>

            <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                {/* Left: editor + logs */}
                <div style={{ flex: '1 1 420px', minWidth: 320, display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        <select
                            value={selectedId}
                            onChange={(e) => selectExample(e.target.value)}
                            style={{
                                background: '#1a202c', color: '#e2e8f0', border: '1px solid #2d3748',
                                borderRadius: 6, padding: '6px 8px', fontSize: 13,
                            }}
                        >
                            {examples.map((a) => (
                                <option key={a.id} value={a.id}>{a.name}</option>
                            ))}
                        </select>
                        <button onClick={run} disabled={!code} style={btnStyle('#667eea')}>
                            <Play size={14} /> Run
                        </button>
                        <button onClick={stop} style={btnStyle('#2d3748')}>
                            <Square size={14} /> Stop
                        </button>
                        <button onClick={() => fetch(`${API_BASE}/emulator/examples`).then(r => r.json()).then(d => { setExamples(d.apps || []); const s = d.apps.find(a => a.id === selectedId) || d.apps[0]; if (s) setCode(s.code); })} style={btnStyle('#2d3748')}>
                            <RefreshCw size={14} /> Reload apps
                        </button>
                        <span style={{ fontSize: 12, color: connected ? '#38a169' : '#718096' }}>
                            {connected ? '● connected' : '○ idle'}
                        </span>
                    </div>

                    <textarea
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                        spellCheck={false}
                        style={{
                            width: '100%', minHeight: 340, resize: 'vertical',
                            background: '#0d1117', color: '#e6edf3', border: '1px solid #2d3748',
                            borderRadius: 8, padding: 12, fontFamily: 'ui-monospace, Consolas, monospace',
                            fontSize: 13, lineHeight: 1.5,
                        }}
                    />

                    <div style={{
                        background: '#0d1117', border: '1px solid #2d3748', borderRadius: 8,
                        padding: 10, height: 140, overflowY: 'auto', fontFamily: 'ui-monospace, monospace',
                        fontSize: 12, color: '#9ca3af', whiteSpace: 'pre-wrap',
                    }}>
                        {logs.length === 0 ? '// app output appears here' : logs.join('\n')}
                    </div>
                </div>

                {/* Right: virtual device */}
                <div style={{ flex: '0 0 300px', display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'center' }}>
                    <div style={{
                        background: '#111827', borderRadius: 36, padding: 18,
                        border: '1px solid #374151', boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
                    }}>
                        <canvas
                            ref={canvasRef}
                            width={CANVAS}
                            height={CANVAS}
                            onPointerDown={onCanvasPointer}
                            style={{
                                width: 240, height: 240, borderRadius: '50%',
                                background: '#000', cursor: 'crosshair', display: 'block',
                                border: '4px solid #0b0f19',
                            }}
                        />
                    </div>
                    <div style={{ fontSize: 12, color: '#718096', textAlign: 'center' }}>
                        <MonitorSmartphone size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                        Virtual XIAO ESP32-S3 · 240×240 GC9A01
                    </div>
                    <div style={{ fontSize: 12, color: '#718096', textAlign: 'center' }}>
                        Click/tap the screen to send a touch point (0–255).
                    </div>
                </div>
            </div>
        </div>
    );
}

function btnStyle(bg) {
    return {
        display: 'inline-flex', alignItems: 'center', gap: 6,
        background: bg, color: '#fff', border: 'none', borderRadius: 6,
        padding: '7px 12px', fontSize: 13, cursor: 'pointer', fontWeight: 600,
    };
}
