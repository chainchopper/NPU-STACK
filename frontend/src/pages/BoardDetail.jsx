import React, { useMemo, useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  Cpu, ArrowLeft, ExternalLink, Wifi, WifiOff, Zap, Terminal, MessageSquare,
  Box, ListChecks, LayoutGrid, Images, Cable, Info, CheckCircle2, Circle,
  RefreshCw, FileText, Boxes, Camera, Mic,
} from 'lucide-react';
import { API_BASE } from '../api/client';

const MANUFACTURER_COLORS = {
  raspberrypi: '#cd2355', espressif: '#e7352c', arduino: '#00979d',
  adafruit: '#1a1a1a', seedstudio: '#3cb371', waveshare: '#0066cc',
  sparkfun: '#e04e2b', google: '#4285f4',
};

const IMG_EXT = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg']);

// Convert a stored board asset path to an API URL. The backend serves both
// backend/data/boards/assets/<id>/... and backend/data/boards/<id>/... .
function assetUrl(boardId, storedPath) {
  if (!storedPath) return null;
  if (/^https?:\/\//.test(storedPath)) return storedPath;
  if (storedPath.startsWith('/api')) return storedPath;
  const rel = storedPath
    .replace(`backend/data/boards/assets/${boardId}/`, '')
    .replace(`backend/data/boards/${boardId}/`, '');
  return `${API_BASE}/boards/${boardId}/assets/${rel}`;
}

const TABS = [
  { id: 'overview', label: 'Overview', icon: Info },
  { id: 'features', label: 'Features', icon: ListChecks },
  { id: 'compatibility', label: 'Compatibility', icon: Boxes },
  { id: 'connection', label: 'Connection', icon: Wifi },
  { id: 'requirements', label: 'Requirements', icon: CheckCircle2 },
  { id: 'pinouts', label: 'Pinouts', icon: Cable },
  { id: 'photos', label: 'Photos', icon: Images },
  { id: 'agent', label: 'Agent', icon: MessageSquare },
];

function Section({ title, children, icon: Icon }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        {Icon && <Icon size={14} color="#d29922" />}
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</span>
      </div>
      {children}
    </div>
  );
}

function Pill({ children, color = '#d29922', background }) {
  return (
    <span style={{
      fontSize: 11, padding: '3px 10px', borderRadius: 12,
      background: background || `${color}18`, color, fontWeight: 600,
      border: `1px solid ${color}33`, display: 'inline-flex', alignItems: 'center', gap: 5,
    }}>
      {children}
    </span>
  );
}

function SpecTable({ specs }) {
  if (!specs || !Object.keys(specs).length) return null;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
      {Object.entries(specs).map(([k, v]) => (
        <div key={k} style={{ display: 'flex', gap: 8, padding: '8px 10px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)' }}>
          <span style={{ fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'capitalize', minWidth: 56 }}>{k}</span>
          <span style={{ color: 'var(--text-primary)' }}>{v}</span>
        </div>
      ))}
    </div>
  );
}

function DeviceCard({ device, color }) {
  const paired = device.paired;
  const available = device.available;
  return (
    <div style={{
      padding: 12, borderRadius: 10, background: 'var(--bg-input)',
      border: `1px solid ${paired ? color : 'var(--border-color)'}44`,
      display: 'flex', flexDirection: 'column', gap: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', wordBreak: 'break-all' }}>
          {device.nickname || device.id}
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 5 }}>
          <Pill color={paired ? '#3cb371' : '#888'}>{paired ? 'paired' : 'detected'}</Pill>
          <Pill color={available ? '#3cb371' : '#888'}>
            {available ? <Wifi size={10} /> : <WifiOff size={10} />} {available ? 'online' : (device.status || 'offline')}
          </Pill>
        </span>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {device.chip && <span><b style={{ color: 'var(--text-secondary)' }}>chip</b> {device.chip}</span>}
        {device.ip && <span><b style={{ color: 'var(--text-secondary)' }}>ip</b> {device.ip}</span>}
        {device.firmware_version && <span><b style={{ color: 'var(--text-secondary)' }}>fw</b> {device.firmware_version}</span>}
        {device.connection && <span><b style={{ color: 'var(--text-secondary)' }}>link</b> {device.connection}</span>}
      </div>
    </div>
  );
}

export default function BoardDetail() {
  const { boardId } = useParams();
  const navigate = useNavigate();
  const [board, setBoard] = useState(null);
  const [devices, setDevices] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('overview');

  const load = () => {
    setLoading(true);
    fetch(`${API_BASE}/boards/${boardId}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(d => {
        setBoard(d.board || null);
        setDevices(d.devices || []);
        setStatus(d.status || null);
        setError('');
        setLoading(false);
      })
      .catch(e => { setError(e.message); setLoading(false); });
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [boardId]);

  const color = useMemo(
    () => (board ? (MANUFACTURER_COLORS[board.manufacturer] || '#667eea') : '#667eea'),
    [board],
  );

  // Build the gallery from the asset manifest + legacy image refs.
  const gallery = useMemo(() => {
    if (!board) return [];
    const seen = new Set();
    const out = [];
    const add = (url, label, category, ext) => {
      if (!url || seen.has(url)) return;
      seen.add(url);
      if (ext && !IMG_EXT.has(ext)) return; // PDFs/STLs/ZIPs go in the docs list
      out.push({ url, label: label || '', category: category || '' });
    };
    const manifest = board.assets;
    if (Array.isArray(manifest)) {
      manifest.forEach(a => add(assetUrl(boardId, a.path), a.label, a.category, a.ext));
    }
    (board.pinout_image_urls || []).forEach(u => add(assetUrl(boardId, u), 'Pinout', 'pinout'));
    (board.image_urls || []).forEach(u => add(assetUrl(boardId, u), '', 'photos'));
    if (board.screenshot) add(assetUrl(boardId, board.screenshot), 'Screenshot', 'photos');
    return out;
  }, [board, boardId]);

  const docs = useMemo(() => {
    if (!board || !Array.isArray(board.assets)) return [];
    return board.assets
      .filter(a => !IMG_EXT.has(a.ext))
      .map(a => ({ ...a, url: assetUrl(boardId, a.path) }));
  }, [board, boardId]);

  const pinImages = useMemo(
    () => (board?.pinout_image_urls || []).map(u => ({ url: assetUrl(boardId, u) })),
    [board, boardId],
  );

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
        <div className="spinner" style={{ margin: '0 auto 12px' }} /> Loading board…
      </div>
    );
  }

  if (error || !board) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <div style={{ color: 'var(--text-primary)', fontSize: 15, marginBottom: 8 }}>
          Board not found
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 16 }}>
          {error || `No board with id "${boardId}"`}
        </div>
        <Link to="/boards" style={{ color, fontSize: 12, textDecoration: 'none' }}>← Back to Board Explorer</Link>
      </div>
    );
  }

  const pairedCount = status?.paired_count || 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', maxWidth: '100%' }}>
      {/* Header */}
      <div style={{ padding: '14px 20px 12px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-secondary)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <button onClick={() => navigate('/boards')} title="Back"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}>
            <ArrowLeft size={18} />
          </button>
          <Cpu size={22} color={color} />
          <div style={{ flex: 1, minWidth: 200 }}>
            <h2 style={{ margin: 0, fontSize: 16, color: 'var(--text-primary)' }}>{board.name}</h2>
            <div style={{ fontSize: 11, color, fontWeight: 600, textTransform: 'uppercase', marginTop: 2 }}>
              {board.manufacturer} · {board.chip} · {board.architecture}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {pairedCount > 0
              ? <Pill color="#3cb371"><Wifi size={10} /> {pairedCount} paired</Pill>
              : <Pill color="#888"><WifiOff size={10} /> not paired</Pill>}
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: 2, overflowX: 'auto', padding: '6px 12px',
        borderBottom: '1px solid var(--border-color)', background: 'var(--bg-card)',
      }}>
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
                padding: '8px 12px', borderRadius: 8, fontSize: 12, fontWeight: active ? 700 : 500,
                background: active ? `${color}22` : 'transparent',
                color: active ? color : 'var(--text-muted)',
                border: active ? `1px solid ${color}55` : '1px solid transparent',
                cursor: 'pointer',
              }}>
              <Icon size={13} /> {t.label}
            </button>
          );
        })}
      </div>

      {/* Body */}
      <div style={{ overflow: 'auto', padding: '16px 20px', flex: 1 }}>
        {tab === 'overview' && (
          <div>
            <Section title="Specifications" icon={Cpu}><SpecTable specs={board.specs} /></Section>
            <Section title="Tags" icon={LayoutGrid}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {(board.tags || []).map(t => <Pill key={t} color={color}>{t}</Pill>)}
              </div>
            </Section>
            <Section title="Links" icon={ExternalLink}>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                {board.docs_url && (
                  <a href={board.docs_url} target="_blank" rel="noopener noreferrer"
                    style={{ fontSize: 12, color, display: 'flex', alignItems: 'center', gap: 5, textDecoration: 'none' }}>
                    <ExternalLink size={13} /> Documentation
                  </a>
                )}
                {board.product_url && (
                  <a href={board.product_url} target="_blank" rel="noopener noreferrer"
                    style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 5, textDecoration: 'none' }}>
                    <ExternalLink size={13} /> Product page
                  </a>
                )}
              </div>
            </Section>
          </div>
        )}

        {tab === 'features' && (
          <Section title="Capabilities" icon={ListChecks}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
              {(board.features || []).map((f, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '10px 12px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)' }}>
                  <CheckCircle2 size={14} color={color} />
                  <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>{f}</span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {tab === 'compatibility' && (
          <Section title="Works with" icon={Boxes}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {(board.compatibility || board.tags || []).map((c, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '10px 12px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)' }}>
                  <Box size={13} color={color} />
                  <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>{c}</span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {tab === 'connection' && (
          <div>
            <Section title={`Fleet devices (${devices.length})`} icon={Wifi}>
              {devices.length === 0 ? (
                <div style={{ padding: '24px 16px', textAlign: 'center', background: 'var(--bg-input)', borderRadius: 10, border: '1px dashed var(--border-color)' }}>
                  <div style={{ color: 'var(--text-primary)', fontSize: 13, marginBottom: 6 }}>No devices detected for this board</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.7 }}>
                    Plug the board in via USB-C or power it on Wi-Fi — NPU-STACK auto-detects
                    and registers it by stable unique id (heartbeat at <code>/api/health</code>).
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {devices.map(d => <DeviceCard key={d.id} device={d} color={color} />)}
                </div>
              )}
            </Section>
          </div>
        )}

        {tab === 'requirements' && (
          <Section title="To run this board" icon={CheckCircle2}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {(board.requirements || []).map((r, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '10px 12px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)' }}>
                  <CheckCircle2 size={14} color={color} style={{ marginTop: 2 }} />
                  <span style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.6 }}>{r}</span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {tab === 'pinouts' && (
          <div>
            {board.pinout?.rows?.length > 0 && (
              <Section title="Pin map" icon={Cable}>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead>
                      <tr>
                        {(board.pinout.headers || ['Pin', 'Chip Pin', 'Functions']).map(h => (
                          <th key={h} style={{ textAlign: 'left', padding: '8px 10px', borderBottom: '2px solid var(--border-color)', color: 'var(--text-secondary)' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {board.pinout.rows.map((row, i) => (
                        <tr key={i} style={{ background: i % 2 ? 'var(--bg-input)' : 'transparent' }}>
                          {row.map((cell, j) => (
                            <td key={j} style={{ padding: '7px 10px', borderBottom: '1px solid var(--border-color)', color: j === 0 ? color : 'var(--text-primary)', fontWeight: j === 0 ? 600 : 400 }}>{cell}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            )}
            {board.pinout?.special?.length > 0 && (
              <Section title="Special function pins" icon={Cpu}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {board.pinout.special.map((row, i) => (
                    <div key={i} style={{ display: 'flex', gap: 10, padding: '8px 12px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 700, color, minWidth: 140 }}>{row[0]}</span>
                      <span style={{ color: 'var(--text-secondary)', minWidth: 100 }}>{row[1]}</span>
                      <span style={{ color: 'var(--text-muted)' }}>{row[2]}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}
            {board.round_display && (
              <Section title="Round Display carrier wiring" icon={Box}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 6 }}>
                  {Object.entries(board.round_display.wiring || {}).map(([k, v]) => (
                    <div key={k} style={{ padding: '8px 10px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', fontSize: 12 }}>
                      <b style={{ color: 'var(--text-secondary)' }}>{k}</b>
                      <div style={{ color }}>{v}</div>
                    </div>
                  ))}
                  {board.round_display.touch && (
                    <div style={{ padding: '8px 10px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', fontSize: 12 }}>
                      <b style={{ color: 'var(--text-secondary)' }}>Touch</b>
                      <div style={{ color }}>{board.round_display.touch.controller}</div>
                      <div style={{ color: 'var(--text-muted)' }}>INT {board.round_display.touch.INT} · RST {board.round_display.touch.RST}</div>
                    </div>
                  )}
                </div>
              </Section>
            )}
            {pinImages.length > 0 && (
              <Section title="Pinout diagrams" icon={Images}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
                  {pinImages.map((img, i) => (
                    <a key={i} href={img.url} target="_blank" rel="noopener noreferrer" style={{ display: 'block' }}>
                      <img src={img.url} alt={`pinout ${i}`} style={{ width: '100%', borderRadius: 10, border: '1px solid var(--border-color)', background: 'var(--bg-input)' }} />
                    </a>
                  ))}
                </div>
              </Section>
            )}
          </div>
        )}

        {tab === 'photos' && (
          <div>
            <Section title={`Gallery (${gallery.length})`} icon={Images}>
              {gallery.length === 0 ? (
                <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', background: 'var(--bg-input)', borderRadius: 10, border: '1px dashed var(--border-color)' }}>
                  No photos available for this board yet.
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
                  {gallery.map((g, i) => (
                    <a key={i} href={g.url} target="_blank" rel="noopener noreferrer"
                      style={{ textDecoration: 'none', borderRadius: 10, overflow: 'hidden', border: '1px solid var(--border-color)', background: 'var(--bg-input)' }}>
                      <img src={g.url} alt={g.label || `photo ${i}`} loading="lazy"
                        style={{ width: '100%', height: 140, objectFit: 'cover', display: 'block' }} />
                      <div style={{ padding: '6px 8px', fontSize: 11, color: 'var(--text-muted)' }}>
                        {g.label || g.category || `photo ${i}`}
                      </div>
                    </a>
                  ))}
                </div>
              )}
            </Section>
            {docs.length > 0 && (
              <Section title="Datasheets & schematics" icon={FileText}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 8 }}>
                  {docs.map((a, i) => (
                    <a key={i} href={a.url} target="_blank" rel="noopener noreferrer"
                      style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', textDecoration: 'none' }}>
                      <FileText size={15} color={color} />
                      <span style={{ fontSize: 12, color: 'var(--text-primary)', flex: 1 }}>{a.label}</span>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>{a.ext}</span>
                    </a>
                  ))}
                </div>
              </Section>
            )}
          </div>
        )}

        {tab === 'agent' && (
          <div>
            <Section title="Quick use — no connection required" icon={MessageSquare}>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <Link to="/agents" style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 14px', borderRadius: 8, background: `${color}22`, border: `1px solid ${color}44`, color, textDecoration: 'none', fontSize: 12, fontWeight: 600 }}>
                  <MessageSquare size={14} /> Ask Nirvana about {board.chip}
                </Link>
                <Link to="/device-playground" style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 14px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', textDecoration: 'none', fontSize: 12 }}>
                  <Zap size={14} /> Emulator (write & preview firmware)
                </Link>
                <Link to="/esp-dev" style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 14px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', textDecoration: 'none', fontSize: 12 }}>
                  <Terminal size={14} /> ESP console / flash
                </Link>
                <Link to="/boards" style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 14px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-muted)', textDecoration: 'none', fontSize: 12 }}>
                  <Cpu size={14} /> All boards
                </Link>
              </div>
            </Section>

            <Section title={pairedCount > 0 ? 'Paired device actions' : 'Pair this board'} icon={Wifi}>
              {pairedCount > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {devices.filter(d => d.paired).map(d => (
                    <div key={d.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 8, background: 'var(--bg-input)', border: `1px solid ${color}44`, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 600 }}>{d.nickname || d.id}</span>
                      <Link to="/edge-fleet" style={{ marginLeft: 'auto', fontSize: 11, color, textDecoration: 'none' }}>Manage →</Link>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ padding: '16px', borderRadius: 10, background: 'var(--bg-input)', border: '1px dashed var(--border-color)', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.7 }}>
                  This board isn't paired yet. To pair: plug it in via USB-C or power it on
                  Wi-Fi — it registers automatically on boot (heartbeat to <code>/api/health</code>).
                  You can still write firmware, run the emulator, and chat with the agent without a
                  physical connection.
                </div>
              )}
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}
