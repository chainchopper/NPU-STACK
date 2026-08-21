import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Cpu, Search, Zap, Terminal, Wifi, FlaskConical, MessageSquare, RefreshCw, ExternalLink, Filter, X, Maximize2 } from 'lucide-react';
import { API_BASE } from '../api/client';

const MANUFACTURER_COLORS = {
  raspberrypi: '#cd2355', espressif: '#e7352c', arduino: '#00979d',
  adafruit: '#1a1a1a', seedstudio: '#3cb371', waveshare: '#0066cc',
  sparkfun: '#e04e2b', google: '#4285f4',
};

export default function BoardExplorer() {
  const navigate = useNavigate();
  const [boards, setBoards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [tagFilter, setTagFilter] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/boards`).then(r => r.json()).then(d => {
      setBoards(d.boards || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const filtered = boards.filter(b => {
    if (search && !b.name.toLowerCase().includes(search.toLowerCase()) &&
        !b.chip?.toLowerCase().includes(search.toLowerCase())) return false;
    if (tagFilter && !b.tags?.includes(tagFilter)) return false;
    return true;
  });

  const allTags = [...new Set(boards.flatMap(b => b.tags || []))].sort();

  const opIcons = {
    pair: Wifi, terminal: Terminal, 'flash-esptool': Zap, 'flash-uf2': Zap,
    'flash-sd': Zap, blink: Zap, 'fleet-enroll': Wifi, benchmark: FlaskConical,
    'nirvana-chat': MessageSquare, 'gpio-control': Cpu, 'esp-now': Wifi,
    'display-test': Cpu, 'benchmark-tpu': FlaskConical,
  };

  const opLabels = {
    pair: 'Pair', terminal: 'Terminal', 'flash-esptool': 'Flash ESP', 'flash-uf2': 'Flash UF2',
    'flash-sd': 'Flash SD', blink: 'Blink LED', 'fleet-enroll': 'Fleet Enroll',
    benchmark: 'Benchmark', 'nirvana-chat': 'Ask Nirvana', 'gpio-control': 'GPIO',
    'esp-now': 'ESP-NOW', 'display-test': 'Display', 'benchmark-tpu': 'TPU Benchmark',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', maxWidth: '100%' }}>
      <div style={{ padding: '16px 20px 12px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-secondary)' }}>
        <h2 style={{ margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Cpu size={22} color="#d29922" /> Board Explorer
        </h2>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)' }}>
          {boards.length} supported boards · Click a board to see operations
        </p>
      </div>

      <div style={{ padding: '12px 20px', display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-card)' }}>
        <div style={{ position: 'relative', flex: '1 1 200px', maxWidth: 300 }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search boards or chips..."
            style={{ width: '100%', padding: '8px 10px 8px 32px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 12 }} />
        </div>
        <select value={tagFilter} onChange={e => setTagFilter(e.target.value)}
          style={{ padding: '8px 10px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 12 }}>
          <option value="">All tags</option>
          {allTags.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        {tagFilter && <button onClick={() => setTagFilter('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}><X size={14} /></button>}
        <button onClick={() => { setLoading(true); fetch(`${API_BASE}/boards`).then(r => r.json()).then(d => { setBoards(d.boards || []); setLoading(false); }); }}
          style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }} title="Refresh">
          <RefreshCw size={14} />
        </button>
      </div>

      <div style={{ overflow: 'auto', padding: '16px 20px', flex: 1 }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
            <div className="spinner" style={{ margin: '0 auto 12px' }} /> Loading boards...
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
            No boards found. Try a different search or tag filter.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
            {filtered.map(board => {
              const color = MANUFACTURER_COLORS[board.manufacturer] || '#667eea';
              return (
                <div key={board.id} style={{
                  padding: 20, borderRadius: 12, background: 'var(--bg-card)',
                  border: `1px solid ${color}33`, transition: 'box-shadow 0.2s',
                  cursor: 'pointer',
                }} onClick={() => navigate(`/boards/${board.id}`)}
                   onMouseEnter={e => e.currentTarget.style.boxShadow = `0 0 20px ${color}22`}
                   onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}>
                  {/* Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{board.name}</div>
                      <div style={{ fontSize: 11, color, fontWeight: 600, textTransform: 'uppercase', marginTop: 2 }}>
                        {board.manufacturer} · {board.chip}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 12, background: `${color}18`, color, fontWeight: 600 }}>
                        {board.architecture}
                      </span>
                      <span title="Open full view" style={{ fontSize: 10, padding: '3px 8px', borderRadius: 12, background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border-color)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <Maximize2 size={11} /> View
                      </span>
                    </div>
                  </div>

                  {/* Specs */}
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.8, marginBottom: 12 }}>
                    {Object.entries(board.specs || {}).map(([k, v]) => (
                      <div key={k} style={{ display: 'flex', gap: 8 }}>
                        <span style={{ fontWeight: 600, minWidth: 50, color: 'var(--text-secondary)' }}>{k}:</span>
                        <span>{v}</span>
                      </div>
                    ))}
                  </div>

                  {/* Tags */}
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 12 }}>
                    {(board.tags || []).slice(0, 6).map(t => (
                      <span key={t} onClick={(e) => { e.stopPropagation(); setTagFilter(t); }} style={{
                        fontSize: 10, padding: '2px 8px', borderRadius: 10,
                        background: 'var(--bg-input)', color: 'var(--text-muted)',
                        cursor: 'pointer', border: '1px solid var(--border-color)',
                      }}>{t}</span>
                    ))}
                  </div>

                  {/* Operations */}
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                    {(board.npu_stack_ops || []).map(op => {
                      const Icon = opIcons[op] || Zap;
                      return (
                        <button key={op} onClick={async (e) => {
                          e.stopPropagation();
                          const btn = e.target.closest('button');
                          const origText = btn.textContent;
                          btn.textContent = '...';
                          btn.disabled = true;
                          try {
                            const r = await fetch(`${API_BASE}/fleet/command/device/${board.id}`, {
                              method: 'POST',
                              headers: {'Content-Type': 'application/json'},
                              body: JSON.stringify({command: op.toUpperCase().replace('-','_'), params: {}}),
                            });
                            const d = await r.json();
                            btn.textContent = d.sent ? '✓' : '✗';
                            setTimeout(() => { btn.textContent = origText; btn.disabled = false; }, 1500);
                          } catch {
                            btn.textContent = '✗';
                            setTimeout(() => { btn.textContent = origText; btn.disabled = false; }, 1500);
                          }
                        }} style={{
                          display: 'flex', alignItems: 'center', gap: 4,
                          padding: '4px 10px', borderRadius: 6, fontSize: 11,
                          background: `${color}18`, border: `1px solid ${color}33`,
                          color, cursor: 'pointer', fontWeight: 500,
                        }} title={opLabels[op] || op}>
                          <Icon size={12} /> {opLabels[op] || op}
                        </button>
                      );
                    })}
                  </div>

                  {/* Docs link */}
                  {board.docs_url && (
                    <a href={board.docs_url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
                      style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4, textDecoration: 'none' }}>
                      <ExternalLink size={12} /> Documentation
                    </a>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
