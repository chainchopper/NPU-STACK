import React from 'react';
import { Terminal } from 'lucide-react';

export default function ActivityLogCard({
    title = 'Activity Log',
    lines = [],
    emptyMessage = 'No activity recorded yet.',
    onClear,
    style,
}) {
    return (
        <div className="card" style={style}>
            <div className="card-header">
                <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Terminal size={18} /> {title}
                </div>
                {onClear && (
                    <button className="btn btn-secondary" style={{ padding: '6px 14px', fontSize: 12 }} onClick={onClear}>
                        Clear
                    </button>
                )}
            </div>
            <div className="fleet-log">
                {lines.length > 0
                    ? lines.map((line, index) => <div key={`${title}-${index}`} className="fleet-log-line">{line}</div>)
                    : <div className="fleet-log-line" style={{ color: 'var(--text-muted)' }}>{emptyMessage}</div>}
            </div>
        </div>
    );
}
