import { useState, useEffect } from 'react';
import { CheckSquare, Plus, Trash2, Clock } from 'lucide-react';
import { API_BASE } from '../api/client';

export default function NirvanaTodos() {
    const [todos, setTodos] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const r = await fetch(`${API_BASE}/todos`);
            const d = await r.json();
            setTodos(d.todos || []);
        } catch (e) { setError(e.message); }
        finally { setLoading(false); }
    };

    useEffect(() => { load(); }, []);

    const add = async () => {
        if (!input.trim()) return;
        try {
            await fetch(`${API_BASE}/todos`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: input.trim() })
            });
            setInput('');
            load();
        } catch (e) { setError(e.message); }
    };

    const toggle = async (id, completed) => {
        try { await fetch(`${API_BASE}/todos/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ completed: !completed }) }); load(); } catch (e) { setError(e.message); }
    };

    const remove = async (id) => {
        try { await fetch(`${API_BASE}/todos/${id}`, { method: 'DELETE' }); load(); } catch (e) { setError(e.message); }
    };

    if (loading) return <div className="loading-overlay"><div className="spinner" /><p>Loading todos...</p></div>;

    return (
        <div>
            <div className="page-header"><h2>Todos</h2><p>Task tracking — part of the Nirvana agent workspace</p></div>
            {error && <div style={{ padding: 12, borderRadius: 8, marginBottom: 16, background: 'var(--accent-red-glow)', color: 'var(--accent-red)', fontSize: 13 }}>{error}</div>}
            <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
                <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && add()}
                    placeholder="New task..." style={{ flex: 1, padding: '10px 14px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 14 }} />
                <button onClick={add} className="btn btn-primary" disabled={!input.trim()}><Plus size={16} /> Add</button>
            </div>
            {todos.length === 0 ? <div className="empty-state"><CheckSquare size={48} /><h3>No todos</h3><p>Create a task to get started</p></div> :
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {todos.map(t => (
                        <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 12, borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--border-color)' }}>
                            <input type="checkbox" checked={t.completed} onChange={() => toggle(t.id, t.completed)}
                                style={{ width: 18, height: 18, accentColor: 'var(--accent-blue)', cursor: 'pointer' }} />
                            <span style={{ flex: 1, fontSize: 14, textDecoration: t.completed ? 'line-through' : 'none', color: t.completed ? 'var(--text-muted)' : 'var(--text-primary)' }}>{t.content || t.text || t.title}</span>
                            <button onClick={() => remove(t.id)} className="btn-icon" style={{ color: 'var(--accent-red)' }}><Trash2 size={14} /></button>
                        </div>
                    ))}</div>}
        </div>
    );
}