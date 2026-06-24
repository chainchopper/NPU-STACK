import { useState, useEffect } from 'react';
import { BarChart3, TrendingUp, Activity } from 'lucide-react';
import { API_BASE } from '../api/client';

export default function NirvanaInsights() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch(`${API_BASE}/insights?days=30`).then(r => r.json()).then(setData).catch(() => {}).finally(() => setLoading(false));
    }, []);

    if (loading) return <div className="loading-overlay"><div className="spinner" /><p>Loading insights...</p></div>;

    return (
        <div>
            <div className="page-header"><h2>Insights</h2><p>Usage analytics and activity trends — part of the Nirvana agent workspace</p></div>
            {data ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 14 }}>
                    {data.summary ? Object.entries(data.summary).map(([k, v]) => (
                        <div key={k} className="card" style={{ padding: 16, textAlign: 'center' }}>
                            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--accent-blue)' }}>{v}</div>
                            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{k}</div>
                        </div>
                    )) : <div className="empty-state"><BarChart3 size={48} /><h3>No data yet</h3><p>Activity will appear here as you use Nirvana</p></div>}
                </div>
            ) : <div className="empty-state"><Activity size={48} /><h3>Insights loading</h3><p>Connect to see usage data</p></div>}
        </div>
    );
}