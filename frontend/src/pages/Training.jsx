import React, { useState, useEffect, useRef } from 'react';
import { Play, Square, GraduationCap, Clock } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { startTraining, listJobs, stopJob, connectTrainingWS } from '../api/client';

export default function Training() {
    const [jobs, setJobs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [activeJob, setActiveJob] = useState(null);
    const [liveMetrics, setLiveMetrics] = useState([]);
    const [liveLogs, setLiveLogs] = useState([]);
    const wsRef = useRef(null);

    const [form, setForm] = useState({
        name: 'my-training-job',
        architecture: 'simple_cnn',
        dataset: 'cifar10',
        epochs: 5,
        batch_size: 64,
        learning_rate: 0.001,
        optimizer: 'adam',
        weight_decay: 0.0001,
    });

    const loadJobs = () => {
        listJobs().then(setJobs).catch(() => setJobs([])).finally(() => setLoading(false));
    };

    useEffect(() => { loadJobs(); }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSubmitting(true);
        try {
            const result = await startTraining(form);
            setActiveJob(result.job_id);
            setLiveMetrics([]);
            setLiveLogs([]);

            // Connect WebSocket for live updates
            wsRef.current = connectTrainingWS(result.job_id, (data) => {
                if (data.type === 'epoch_complete') {
                    setLiveMetrics(prev => [...prev, data]);
                } else if (data.type === 'log' || data.type === 'status') {
                    setLiveLogs(prev => [...prev.slice(-50), { time: new Date().toLocaleTimeString(), ...data }]);
                } else if (data.type === 'batch_progress') {
                    // Update batch progress indicator — we can use the latest one
                    setLiveLogs(prev => {
                        const updated = prev.filter(l => l.type !== 'batch_progress');
                        return [...updated, { time: new Date().toLocaleTimeString(), ...data }];
                    });
                }

                if (data.status === 'completed' || data.status === 'failed' || data.status === 'stopped') {
                    loadJobs();
                }
            });

            loadJobs();
        } catch (e) {
            alert('Failed to start training: ' + e.message);
        }
        setSubmitting(false);
    };

    const handleStop = async (jobId) => {
        try {
            await stopJob(jobId);
            loadJobs();
        } catch (e) {
            alert('Failed to stop: ' + e.message);
        }
    };

    useEffect(() => {
        return () => { if (wsRef.current) wsRef.current.close(); };
    }, []);

    const statusBadge = (status) => {
        const cls = {
            completed: 'badge-success',
            running: 'badge-warning',
            failed: 'badge-error',
            stopped: 'badge-purple',
            pending: 'badge-info',
        }[status] || 'badge-info';
        return (
            <span className={`badge ${cls}`}>
                {status === 'running' && <span className="badge-dot" />}
                {status}
            </span>
        );
    };

    return (
        <div>
            <div className="page-header">
                <h2>Training Console</h2>
                <p>Train models with real PyTorch and export to NPU-compatible formats</p>
            </div>

            <div className="grid-2">
                {/* Configuration Form */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">New Training Job</h3>
                    </div>
                    <form onSubmit={handleSubmit}>
                        <div className="form-group">
                            <label className="form-label">Job Name</label>
                            <input className="form-input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
                        </div>
                        <div className="form-row">
                            <div className="form-group">
                                <label className="form-label">Architecture</label>
                                <select className="form-select" value={form.architecture} onChange={e => setForm({ ...form, architecture: e.target.value })}>
                                    <option value="simple_cnn">Simple CNN</option>
                                    <option value="resnet18">ResNet-18</option>
                                    <option value="mobilenet_v2">MobileNet V2</option>
                                    <option value="efficientnet_b0">EfficientNet B0</option>
                                </select>
                            </div>
                            <div className="form-group">
                                <label className="form-label">Dataset</label>
                                <select className="form-select" value={form.dataset} onChange={e => setForm({ ...form, dataset: e.target.value })}>
                                    <option value="cifar10">CIFAR-10</option>
                                    <option value="mnist">MNIST</option>
                                    <option value="fashion_mnist">Fashion MNIST</option>
                                </select>
                            </div>
                        </div>
                        <div className="form-row">
                            <div className="form-group">
                                <label className="form-label">Epochs</label>
                                <input type="number" className="form-input" value={form.epochs} min={1} max={500} onChange={e => setForm({ ...form, epochs: Number(e.target.value) })} />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Batch Size</label>
                                <input type="number" className="form-input" value={form.batch_size} min={1} max={512} onChange={e => setForm({ ...form, batch_size: Number(e.target.value) })} />
                            </div>
                        </div>
                        <div className="form-row">
                            <div className="form-group">
                                <label className="form-label">Learning Rate</label>
                                <input type="number" className="form-input" value={form.learning_rate} step={0.0001} min={0.00001} max={1} onChange={e => setForm({ ...form, learning_rate: Number(e.target.value) })} />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Optimizer</label>
                                <select className="form-select" value={form.optimizer} onChange={e => setForm({ ...form, optimizer: e.target.value })}>
                                    <option value="adam">Adam</option>
                                    <option value="adamw">AdamW</option>
                                    <option value="sgd">SGD</option>
                                </select>
                            </div>
                        </div>
                        <button type="submit" className="btn btn-primary" disabled={submitting} style={{ width: '100%', justifyContent: 'center' }}>
                            <Play size={16} />
                            {submitting ? 'Starting...' : 'Start Training'}
                        </button>
                    </form>
                </div>

                {/* Live Training Chart */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Live Training Progress</h3>
                        {activeJob && <span className="badge badge-warning"><span className="badge-dot" /> Job #{activeJob}</span>}
                    </div>
                    {liveMetrics.length > 0 ? (
                        <ResponsiveContainer width="100%" height={280}>
                            <LineChart data={liveMetrics}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                                <XAxis dataKey="epoch" stroke="var(--text-muted)" fontSize={12} />
                                <YAxis stroke="var(--text-muted)" fontSize={12} />
                                <Tooltip
                                    contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '8px' }}
                                    labelStyle={{ color: 'var(--text-primary)' }}
                                />
                                <Legend />
                                <Line type="monotone" dataKey="train_loss" stroke="var(--accent-blue)" name="Train Loss" strokeWidth={2} dot={false} />
                                <Line type="monotone" dataKey="val_loss" stroke="var(--accent-cyan)" name="Val Loss" strokeWidth={2} dot={false} />
                                <Line type="monotone" dataKey="val_accuracy" stroke="var(--accent-green)" name="Val Accuracy %" strokeWidth={2} dot={false} />
                            </LineChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="empty-state" style={{ padding: '32px' }}>
                            <GraduationCap size={36} />
                            <p className="text-secondary">Start a training job to see live progress</p>
                        </div>
                    )}

                    {/* Logs */}
                    {liveLogs.length > 0 && (
                        <div className="log-viewer mt-4">
                            {liveLogs.slice(-15).map((log, i) => (
                                <div key={i} className="log-entry">
                                    <span className="log-time">{log.time}</span>
                                    <span className={`log-message ${log.status === 'failed' ? 'error' : log.status === 'completed' ? 'success' : ''}`}>
                                        {log.message || (log.type === 'batch_progress' ? `Epoch ${log.epoch} — Batch ${log.batch}/${log.total_batches} — Loss: ${log.loss?.toFixed(4)} — Acc: ${log.accuracy?.toFixed(1)}%` : JSON.stringify(log))}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Job History */}
            <div className="card mt-6">
                <div className="card-header">
                    <h3 className="card-title">Job History</h3>
                    <button className="btn btn-secondary btn-sm" onClick={loadJobs}><Clock size={14} /> Refresh</button>
                </div>
                {loading ? (
                    <div className="loading-overlay"><div className="spinner" /></div>
                ) : jobs.length === 0 ? (
                    <p className="text-secondary" style={{ padding: '16px 0' }}>No training jobs yet</p>
                ) : (
                    <div className="table-container" style={{ border: 'none' }}>
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Name</th>
                                    <th>Architecture</th>
                                    <th>Dataset</th>
                                    <th>Progress</th>
                                    <th>Loss</th>
                                    <th>Accuracy</th>
                                    <th>Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {jobs.map((j) => (
                                    <tr key={j.id}>
                                        <td className="text-mono text-muted">{j.id}</td>
                                        <td style={{ fontWeight: 500 }}>{j.name}</td>
                                        <td className="text-mono">{j.architecture}</td>
                                        <td>{j.dataset}</td>
                                        <td className="text-mono">{j.current_epoch}/{j.total_epochs}</td>
                                        <td className="text-mono">{j.val_loss?.toFixed(4) ?? '—'}</td>
                                        <td className="text-mono">{j.val_accuracy ? j.val_accuracy.toFixed(1) + '%' : '—'}</td>
                                        <td>{statusBadge(j.status)}</td>
                                        <td>
                                            {j.status === 'running' && (
                                                <button className="btn btn-danger btn-sm" onClick={() => handleStop(j.id)}>
                                                    <Square size={14} /> Stop
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}
