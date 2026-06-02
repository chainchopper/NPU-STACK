import React, { useEffect, useState } from 'react';
import { Bot, ExternalLink, RefreshCw, Sparkles, Wrench } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getNirvanaRuntimeDetails, getNirvanaStatus, launchNirvana, prepareNirvanaRuntime } from '../api/client';

export default function SystemAgent() {
    const navigate = useNavigate();
    const [status, setStatus] = useState(null);
    const [runtime, setRuntime] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');

    const refresh = async () => {
        try {
            const [nextStatus, nextRuntime] = await Promise.all([
                getNirvanaStatus(),
                getNirvanaRuntimeDetails(),
            ]);
            setStatus(nextStatus || null);
            setRuntime(nextRuntime || null);
            setError('');
        } catch (err) {
            setError(err.message || 'Failed to load Nirvana status');
        }
    };

    useEffect(() => {
        refresh();
    }, []);

    const prepare = async () => {
        setBusy(true);
        setError('');
        setNotice('');
        try {
            const result = await prepareNirvanaRuntime();
            setNotice(result?.message || 'Prepared isolated Nirvana runtime.');
            await refresh();
        } catch (err) {
            setError(err.message || 'Failed to prepare Nirvana runtime');
        } finally {
            setBusy(false);
        }
    };

    const launch = async () => {
        setBusy(true);
        setError('');
        setNotice('');
        try {
            const result = await launchNirvana();
            setNotice(result?.message || 'Nirvana WebUI launched.');
            await refresh();
        } catch (err) {
            setError(err.message || 'Failed to launch Nirvana WebUI');
        } finally {
            setBusy(false);
        }
    };

    const openWebUi = () => {
        const target = runtime?.webui_url || status?.webui_url;
        if (!target) {
            setError('Nirvana WebUI URL is not available yet.');
            return;
        }
        window.open(target, '_blank', 'noopener,noreferrer');
    };

    return (
        <div className="card mt-6" style={{ border: '1px solid var(--accent-blue)', background: 'linear-gradient(135deg, rgba(88,166,255,0.08) 0%, rgba(88,166,255,0.03) 100%)' }}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 42, height: 42, borderRadius: 12, display: 'grid', placeItems: 'center', background: 'rgba(88,166,255,0.16)' }}>
                        <Bot size={20} />
                    </div>
                    <div>
                        <h3 className="card-title" style={{ marginBottom: 2 }}>Nirvana</h3>
                        <div className="text-muted" style={{ fontSize: 12 }}>
                            Permanent orchestration agent with absorbed upstream CLI/WebUI wiring
                        </div>
                    </div>
                </div>
                <button className="btn btn-secondary" type="button" onClick={refresh} disabled={busy}>
                    <RefreshCw size={14} /> Refresh
                </button>
            </div>

            {notice && <div style={{ color: 'var(--accent-green)', fontSize: 12, marginBottom: 10 }}>{notice}</div>}
            {error && <div style={{ color: 'var(--accent-red)', fontSize: 12, marginBottom: 10 }}>{error}</div>}

            <div className="grid-2" style={{ gap: 12, alignItems: 'start' }}>
                <div style={{ display: 'grid', gap: 8, fontSize: 12 }}>
                    <div><strong>Status:</strong> {runtime?.webui_running ? 'running' : runtime?.prepared ? 'prepared, not started' : 'not prepared'}</div>
                    <div><strong>Setup state:</strong> {runtime?.setup_state || 'not started'}</div>
                    <div><strong>Onboarding:</strong> {runtime?.completed ? 'complete' : 'pending'}</div>
                    <div><strong>Provider:</strong> {runtime?.current_provider || 'not configured yet'}</div>
                    <div><strong>Model:</strong> {runtime?.current_model || 'upstream-managed'}</div>
                    <div><strong>Chat ready:</strong> {runtime?.chat_ready ? 'yes' : 'no'}</div>
                </div>

                <div style={{ display: 'grid', gap: 8 }}>
                    <button className="btn btn-primary" type="button" onClick={() => navigate('/agents')}>
                        <Sparkles size={14} /> Open Nirvana Control Center
                    </button>
                    <button className="btn btn-secondary" type="button" onClick={prepare} disabled={busy}>
                        <Wrench size={14} /> Prepare Nirvana Runtime
                    </button>
                    <button className="btn btn-secondary" type="button" onClick={launch} disabled={busy}>
                        <Bot size={14} /> Launch Nirvana UI
                    </button>
                    <button className="btn btn-secondary" type="button" onClick={openWebUi} disabled={!runtime?.webui_url && !status?.webui_url}>
                        <ExternalLink size={14} /> Open Upstream Nirvana UI
                    </button>
                </div>
            </div>

            {runtime?.log_excerpt && (
                <div style={{ marginTop: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Latest bridge log excerpt</div>
                    <pre style={{ margin: 0, maxHeight: 140, overflow: 'auto', fontSize: 11, whiteSpace: 'pre-wrap' }}>{runtime.log_excerpt}</pre>
                </div>
            )}
        </div>
    );
}
