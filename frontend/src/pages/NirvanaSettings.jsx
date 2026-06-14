import { useState, useEffect } from 'react';
import { apiUrl } from '../api/client';

/**
 * NirvanaSettings — native React settings panel reading/writing directly
 * from the shared Nirvana state via /api/nirvana/settings.
 * No iframe, no proxy — pure React.
 */
export default function NirvanaSettings() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch(apiUrl('/nirvana/settings'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { setSettings(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const update = async (key, value) => {
    setSaving(true); setSaved(false);
    try {
      const r = await fetch(apiUrl('/nirvana/settings'), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const updated = await r.json();
      setSettings(updated);
      setSaved(true);
    } catch (e) {
      setError(e.message);
    }
    setSaving(false);
  };

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading settings...</span></div>;
  if (error) return <div className="page-card" style={{color:'var(--text-secondary)'}}>Error: {error}</div>;
  if (!settings) return null;

  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <h2 style={{ marginBottom: 4 }}>Nirvana Settings</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 24 }}>
        Native settings panel — reads and writes directly to the shared Nirvana state.
      </p>

      {/* Appearance */}
      <Section title="Appearance">
        <SelectRow label="Theme" value={settings.theme}
          options={['dark','light','system']} onChange={v => update('theme', v)} />
        <SelectRow label="Skin" value={settings.skin}
          options={['default','slate','mono','ares','poseidon','sisyphus','charizard','sienna','catppuccin','hepburn','nous','geist-contrast','neon']}
          onChange={v => update('skin', v)} />
        <SelectRow label="Font Size" value={settings.font_size}
          options={['default','small','large']} onChange={v => update('font_size', v)} />
      </Section>

      {/* Agent */}
      <Section title="Agent Identity">
        <TextRow label="Bot Name" value={settings.bot_name}
          onChange={v => update('bot_name', v)} />
        <SelectRow label="Model Provider" value={settings.default_model_provider}
          options={['deepseek','copilot','openai','anthropic','custom']}
          onChange={v => update('default_model_provider', v)} />
        <TextRow label="Language" value={settings.language}
          onChange={v => update('language', v)} />
      </Section>

      {/* Preferences */}
      <Section title="Preferences">
        <ToggleRow label="Send on Enter" value={settings.send_key === 'enter'}
          onChange={v => update('send_key', v ? 'enter' : 'shift-enter')} />
        <ToggleRow label="Show Token Usage" value={settings.show_token_usage}
          onChange={v => update('show_token_usage', v)} />
        <ToggleRow label="Show Thinking" value={settings.show_thinking}
          onChange={v => update('show_thinking', v)} />
        <ToggleRow label="Notifications" value={settings.notifications_enabled}
          onChange={v => update('notifications_enabled', v)} />
        <ToggleRow label="Sound" value={settings.sound_enabled}
          onChange={v => update('sound_enabled', v)} />
      </Section>

      {/* Status */}
      {saving && <div style={{ color: '#facc15', fontSize: 13, marginTop: 16 }}>Saving...</div>}
      {saved && <div style={{ color: '#4ade80', fontSize: 13, marginTop: 16 }}>✓ Saved</div>}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)',
        textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12,
        borderBottom: '1px solid var(--border-color)', paddingBottom: 6 }}>
        {title}
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>{children}</div>
    </div>
  );
}

function SelectRow({ label, value, options, onChange }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <span style={{ color: 'var(--text-primary)', fontSize: 13 }}>{label}</span>
      <select value={value || ''} onChange={e => onChange(e.target.value)}
        style={selectStyle}>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

function TextRow({ label, value, onChange }) {
  const [edit, setEdit] = useState(false);
  const [val, setVal] = useState(value);

  if (!edit) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <span style={{ color: 'var(--text-primary)', fontSize: 13 }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <code style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{value}</code>
        <button onClick={() => setEdit(true)} style={miniBtn}>Edit</button>
      </div>
    </div>
  );

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <span style={{ color: 'var(--text-primary)', fontSize: 13 }}>{label}</span>
      <div style={{ display: 'flex', gap: 6 }}>
        <input value={val} onChange={e => setVal(e.target.value)}
          style={{ ...selectStyle, width: 160 }} />
        <button onClick={() => { onChange(val); setEdit(false); }} style={{ ...miniBtn, color: '#4ade80' }}>✓</button>
        <button onClick={() => { setVal(value); setEdit(false); }} style={miniBtn}>✕</button>
      </div>
    </div>
  );
}

function ToggleRow({ label, value, onChange }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <span style={{ color: 'var(--text-primary)', fontSize: 13 }}>{label}</span>
      <button onClick={() => onChange(!value)}
        style={{
          ...toggleBase,
          background: value ? 'var(--accent, #4ade80)' : 'var(--bg-tertiary)',
        }}>
        <div style={{
          ...toggleKnob,
          transform: value ? 'translateX(18px)' : 'translateX(2px)',
        }}/>
      </button>
    </div>
  );
}

const selectStyle = {
  background: 'var(--bg-input, #0a0a1a)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-color)',
  borderRadius: 6,
  padding: '4px 10px',
  fontSize: 12,
  outline: 'none',
};

const miniBtn = {
  background: 'var(--bg-tertiary)',
  border: '1px solid var(--border-color)',
  color: 'var(--text-secondary)',
  borderRadius: 4,
  padding: '2px 8px',
  fontSize: 11,
  cursor: 'pointer',
};

const toggleBase = {
  width: 38, height: 22, borderRadius: 11, border: 'none',
  cursor: 'pointer', position: 'relative', transition: 'background 0.2s',
};

const toggleKnob = {
  width: 16, height: 16, borderRadius: '50%', background: '#fff',
  position: 'absolute', top: 3, transition: 'transform 0.2s',
};
