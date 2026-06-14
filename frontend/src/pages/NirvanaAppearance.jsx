import { useState } from 'react';
import { apiUrl } from '../api/client';

const SKINS = [
  { id: 'default', label: 'Default', desc: 'Clean dark with green accents' },
  { id: 'slate', label: 'Slate', desc: 'Muted grays and blues' },
  { id: 'mono', label: 'Mono', desc: 'Minimal black and white' },
  { id: 'ares', label: 'Ares', desc: 'Warm reds and oranges' },
  { id: 'poseidon', label: 'Poseidon', desc: 'Ocean blues' },
  { id: 'sisyphus', label: 'Sisyphus', desc: 'Earthy browns' },
  { id: 'charizard', label: 'Charizard', desc: 'Fiery orange and red' },
  { id: 'sienna', label: 'Sienna', desc: 'Rustic warm tones' },
  { id: 'catppuccin', label: 'Catppuccin', desc: 'Soft pastel palette' },
  { id: 'hepburn', label: 'Hepburn', desc: 'Classic black & white film' },
  { id: 'nous', label: 'Nous', desc: 'Nous Research branded' },
  { id: 'geist-contrast', label: 'Geist Contrast', desc: 'High contrast mode' },
  { id: 'neon', label: 'Neon', desc: 'Vibrant neon colors' },
];

export default function NirvanaAppearance() {
  const [saveMsg, setSaveMsg] = useState(null);

  const apply = async (key, value) => {
    setSaveMsg(null);
    try {
      const r = await fetch(apiUrl('/nirvana/settings'), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSaveMsg(`✓ ${key} set to "${value}"`);
      setTimeout(() => setSaveMsg(null), 2000);
    } catch (e) {
      setSaveMsg(`✗ Error: ${e.message}`);
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 900 }}>
      <h2 style={{ marginBottom: 4 }}>Appearance</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16 }}>
        Configure Nirvana's visual appearance — native settings panel.
      </p>

      {saveMsg && (
        <div style={{
          padding: '8px 14px', marginBottom: 16, borderRadius: 8, fontSize: 13,
          background: saveMsg.startsWith('✓') ? '#1a3a2a' : '#3a1a1a',
          color: saveMsg.startsWith('✓') ? '#4ade80' : '#f87171',
        }}>{saveMsg}</div>
      )}

      {/* Theme */}
      <div style={{ marginBottom: 20 }}>
        <h3 style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 10 }}>Theme</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          {['dark','light','system'].map(t => (
            <button key={t} onClick={() => apply('theme', t)}
              style={chipStyle(t === 'dark', '#6366f1')}>{t}</button>
          ))}
        </div>
      </div>

      {/* Skins */}
      <div style={{ marginBottom: 20 }}>
        <h3 style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 10 }}>
          Skins ({SKINS.length})
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 10 }}>
          {SKINS.map(s => (
            <div key={s.id}
              onClick={() => apply('skin', s.id)}
              style={{
                padding: '12px 14px', borderRadius: 10, cursor: 'pointer',
                background: 'var(--bg-card)', border: '1px solid var(--border-color)',
                transition: 'background 0.15s',
              }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)', marginBottom: 2 }}>
                {s.label}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const chipStyle = (active, color) => ({
  padding: '6px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600,
  border: `1px solid ${active ? color : 'var(--border-color)'}`,
  background: active ? color + '22' : 'var(--bg-card)',
  color: active ? color : 'var(--text-secondary)',
  cursor: 'pointer', transition: 'all 0.15s',
});
