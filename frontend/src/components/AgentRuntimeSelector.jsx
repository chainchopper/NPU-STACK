import React, { useState } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import { useAgentRuntime } from '../context/AgentRuntimeContext';

function runtimeStatus(runtime) {
    if (!runtime) return 'unknown';
    if (runtime.status === 'ready') return 'ready';
    if (runtime.status === 'offline') return 'offline';
    if (runtime.status === 'unconfigured') return 'needs setup';
    return runtime.status || 'unknown';
}

export default function AgentRuntimeSelector({
    label = 'Agent runtime',
    compact = false,
    showActions = true,
}) {
    const {
        runtimes,
        selectedRuntime,
        selectedRuntimeId,
        loading,
        busy,
        error,
        select,
        discover,
        probe,
    } = useAgentRuntime();
    const [actionError, setActionError] = useState('');

    const run = async (action) => {
        setActionError('');
        try {
            await action();
        } catch (err) {
            setActionError(err.message || 'Runtime action failed');
        }
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: compact ? 4 : 7 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <label className="form-label" htmlFor="agent-runtime-selector" style={{ margin: 0 }}>
                    {label}
                </label>
                {selectedRuntime && (
                    <span className="text-muted" style={{ fontSize: 11 }}>
                        {runtimeStatus(selectedRuntime)}
                    </span>
                )}
            </div>
            <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
                <select
                    id="agent-runtime-selector"
                    className="form-select"
                    value={selectedRuntimeId}
                    disabled={loading || busy || runtimes.length === 0}
                    onChange={(event) => run(() => select(event.target.value))}
                    aria-label={label}
                    style={{ flex: 1, minWidth: 0 }}
                >
                    {runtimes.length === 0 && <option value={selectedRuntimeId}>No runtimes discovered</option>}
                    {runtimes.map((runtime) => (
                        <option key={runtime.runtime_id} value={runtime.runtime_id}>
                            {runtime.display_name} · {runtimeStatus(runtime)}
                        </option>
                    ))}
                </select>
                {showActions && (
                    <>
                        <button
                            className="btn btn-secondary"
                            type="button"
                            title="Discover configured runtimes"
                            aria-label="Discover configured runtimes"
                            disabled={busy}
                            onClick={() => run(() => discover())}
                            style={{ padding: compact ? '7px 8px' : undefined }}
                        >
                            <Search size={14} />
                        </button>
                        <button
                            className="btn btn-secondary"
                            type="button"
                            title="Probe selected runtime"
                            aria-label="Probe selected runtime"
                            disabled={busy || !selectedRuntimeId}
                            onClick={() => run(() => probe(selectedRuntimeId))}
                            style={{ padding: compact ? '7px 8px' : undefined }}
                        >
                            <RefreshCw size={14} />
                        </button>
                    </>
                )}
            </div>
            {(actionError || error) && (
                <div className="text-muted" style={{ color: 'var(--accent-red)', fontSize: 11 }}>
                    {actionError || error}
                </div>
            )}
        </div>
    );
}
