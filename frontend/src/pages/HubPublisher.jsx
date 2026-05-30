import React, { useState, useEffect, useRef } from 'react';
import { CloudUpload, Share2, Tag } from 'lucide-react';
import ActivityLogCard from '../components/ActivityLogCard';
import OperationNotice from '../components/OperationNotice';
import { apiUrl, diagnoseBackendError } from '../api/client';

export default function HubPublisher() {
    const [status, setStatus] = useState(null);
    const [jobs, setJobs] = useState([]);
    const [notice, setNotice] = useState(null);
    const [activityLog, setActivityLog] = useState([]);
    const hasLoadedRef = useRef(false);

    const addLog = (line) => {
        const timestamp = new Date().toLocaleTimeString();
        setActivityLog((prev) => [...prev.slice(-49), `${timestamp} — ${line}`]);
    };

    useEffect(() => {
        if (hasLoadedRef.current) return;
        hasLoadedRef.current = true;

        addLog('Fetching publisher ecosystem status');
        Promise.all([
            fetch(apiUrl('/finetune/status')).then(res => res.json()),
            fetch(apiUrl('/finetune/jobs')).then(res => res.json()),
        ])
            .then(([statusData, jobsData]) => {
                setStatus(statusData);
                setJobs(jobsData?.jobs || []);
                addLog('Publisher ecosystem status loaded');
            })
            .catch(err => {
                setNotice({
                    tone: 'warning',
                    title: 'Publisher status unavailable',
                    message: diagnoseBackendError(err, 'Hub publisher status'),
                    details: err?.message || null,
                });
                addLog(`Publisher status fetch failed: ${diagnoseBackendError(err, 'Hub publisher status')}`);
            });
    }, []);

    return (
        <div className="page-container">
            <header className="page-header">
                <h1><CloudUpload className="icon-lg" /> HuggingFace Publisher</h1>
                <p>Fine-tune with Unsloth and publish models, datasets, and GGUF files to the Hub.</p>
            </header>

            <OperationNotice
                tone={notice?.tone || 'info'}
                title={notice?.title}
                message={notice?.message}
                details={notice?.details}
            />

            <div className="card">
                <h3>Ecosystem Status</h3>
                {status ? (
                    <>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
                            <div className="status-card" style={{ padding: '0.8rem', border: '1px solid var(--border)', borderRadius: 8 }}>
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Unsloth Ready</div>
                                <div style={{ fontWeight: 700, color: status?.unsloth?.ready ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                                    {status?.unsloth?.ready ? 'Yes' : 'No'}
                                </div>
                            </div>
                            <div className="status-card" style={{ padding: '0.8rem', border: '1px solid var(--border)', borderRadius: 8 }}>
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Unsloth Installed</div>
                                <div style={{ fontWeight: 700 }}>{status?.unsloth?.unsloth_available ? 'Yes' : 'No'}</div>
                            </div>
                            <div className="status-card" style={{ padding: '0.8rem', border: '1px solid var(--border)', borderRadius: 8 }}>
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>CUDA Available</div>
                                <div style={{ fontWeight: 700 }}>{status?.unsloth?.cuda_available ? 'Yes' : 'No'}</div>
                            </div>
                            <div className="status-card" style={{ padding: '0.8rem', border: '1px solid var(--border)', borderRadius: 8 }}>
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>HF Authenticated</div>
                                <div style={{ fontWeight: 700 }}>{status?.hub?.authenticated ? 'Yes' : 'No'}</div>
                            </div>
                        </div>

                        <pre className="code-block" style={{ maxHeight: '400px', overflowY: 'auto' }}>{JSON.stringify(status, null, 2)}</pre>
                    </>
                ) : (
                    <p>Loading...</p>
                )}
            </div>

            <div className="card">
                <h3>Fine-Tune Jobs</h3>
                {jobs.length === 0 ? (
                    <p style={{ color: 'var(--text-secondary)' }}>No in-memory fine-tune jobs currently active.</p>
                ) : (
                    <pre className="code-block" style={{ maxHeight: '260px', overflowY: 'auto' }}>{JSON.stringify(jobs, null, 2)}</pre>
                )}
            </div>

            <div className="card">
                <h3>Actions</h3>
                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                    <button className="btn btn-primary" onClick={() => addLog('Action clicked: Start QLoRA Training (placeholder)')}>Start QLoRA Training</button>
                    <button className="btn btn-outline" onClick={() => addLog('Action clicked: Publish Model (placeholder)')}>Publish Model</button>
                    <button className="btn btn-outline" onClick={() => addLog('Action clicked: Upload GGUF (placeholder)')}>Upload GGUF</button>
                    <button className="btn btn-outline" onClick={() => addLog('Action clicked: Generate Model Card (placeholder)')}>Generate Model Card</button>
                </div>
                <p style={{ marginTop: '1rem', color: 'var(--text-secondary)' }}>
                    Full interactive UI forms for training and publishing are coming soon. The backend APIs are fully operational.
                </p>
            </div>

            <ActivityLogCard
                title="Publisher Activity"
                lines={activityLog}
                emptyMessage="No publisher activity recorded yet."
                onClear={() => setActivityLog([])}
                style={{ marginTop: 16 }}
            />
        </div>
    );
}
