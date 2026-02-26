import { useState, useEffect } from 'react';
import { Wrench, Play, Loader, Square, ChevronDown, ChevronRight } from 'lucide-react';

const API_BASE = 'http://localhost:8000';

export default function FineTuning() {
    const [models, setModels] = useState([]);
    const [datasets, setDatasets] = useState([]);
    const [jobs, setJobs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [starting, setStarting] = useState(false);
    const [expandedJob, setExpandedJob] = useState(null);
    const [jobDetails, setJobDetails] = useState({});

    // Form state
    const [selectedModel, setSelectedModel] = useState('');
    const [selectedDataset, setSelectedDataset] = useState('');
    const [epochs, setEpochs] = useState(3);
    const [batchSize, setBatchSize] = useState(4);
    const [lr, setLr] = useState(0.0002);
    const [useLora, setUseLora] = useState(true);
    const [loraR, setLoraR] = useState(16);
    const [loraAlpha, setLoraAlpha] = useState(32);
    const [outputName, setOutputName] = useState('');

    const humanSize = (bytes) => {
        if (!bytes) return '—';
        if (bytes > 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
        if (bytes > 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
        return `${(bytes / 1e3).toFixed(0)} KB`;
    };

    // Auto-generate output name when model/dataset/config changes
    const selectedModelObj = models.find(m => m.id === parseInt(selectedModel));
    React.useEffect(() => {
        if (selectedModelObj && selectedDataset) {
            const base = selectedModelObj.name.replace(/[^a-zA-Z0-9_-]/g, '_');
            const suffix = useLora ? `lora_r${loraR}_e${epochs}` : `full_e${epochs}`;
            setOutputName(`${base}_${suffix}`);
        }
    }, [selectedModel, selectedDataset, useLora, loraR, epochs]);

    const fetchData = async () => {
        try {
            const [modelsRes, datasetsRes, jobsRes] = await Promise.all([
                fetch(`${API_BASE}/api/models`).then(r => r.json()),
                fetch(`${API_BASE}/api/datasets`).then(r => r.json()),
                fetch(`${API_BASE}/api/finetune/jobs`).then(r => r.json()),
            ]);
            setModels(modelsRes.models || []);
            setDatasets(datasetsRes.datasets || []);
            setJobs(jobsRes.jobs || []);
        } catch (e) { console.error(e); }
        setLoading(false);
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`${API_BASE}/api/finetune/jobs`);
                const data = await res.json();
                setJobs(data.jobs || []);
            } catch (e) { }
        }, 3000);
        return () => clearInterval(interval);
    }, []);

    const startJob = async () => {
        if (!selectedModel || !selectedDataset) return;
        setStarting(true);
        try {
            const form = new FormData();
            form.append('model_id', selectedModel);
            form.append('dataset', selectedDataset);
            form.append('epochs', epochs);
            form.append('batch_size', batchSize);
            form.append('learning_rate', lr);
            form.append('use_lora', useLora);
            form.append('lora_r', loraR);
            form.append('lora_alpha', loraAlpha);

            await fetch(`${API_BASE}/api/finetune/start`, { method: 'POST', body: form });
            await fetchData();
        } catch (e) { console.error(e); }
        setStarting(false);
    };

    const stopJob = async (jobId) => {
        try {
            await fetch(`${API_BASE}/api/finetune/stop/${jobId}`, { method: 'POST' });
            await fetchData();
        } catch (e) { console.error(e); }
    };

    const toggleJob = async (jobId) => {
        if (expandedJob === jobId) {
            setExpandedJob(null);
            return;
        }
        setExpandedJob(jobId);
        try {
            const res = await fetch(`${API_BASE}/api/finetune/jobs/${jobId}`);
            const data = await res.json();
            setJobDetails(prev => ({ ...prev, [jobId]: data }));
        } catch (e) { console.error(e); }
    };

    const statusColor = (status) => {
        switch (status) {
            case 'running': return 'var(--accent-blue)';
            case 'completed': return 'var(--accent-green)';
            case 'failed': return 'var(--accent-red)';
            case 'stopping': return 'var(--accent-amber)';
            default: return 'var(--text-muted)';
        }
    };

    return (
        <div>
            <div className="section-header">
                <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <Wrench size={24} /> Fine-Tuning
                </h2>
                <p className="text-secondary">LoRA / QLoRA parameter-efficient fine-tuning</p>
            </div>

            <div className="grid-2">
                {/* Start New Job */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">New Fine-Tuning Job</h3>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, marginBottom: '4px', display: 'block' }}>Base Model</label>
                            <select value={selectedModel} onChange={e => setSelectedModel(e.target.value)} className="form-select">
                                <option value="">Select a model ({models.length} available)…</option>
                                {models.map(m => <option key={m.id} value={m.id}>{m.name} ({m.format?.toUpperCase()} — {humanSize(m.file_size)})</option>)}
                            </select>
                            {selectedModelObj && (
                                <div style={{ marginTop: 6, padding: '6px 10px', borderRadius: 6, background: 'var(--bg-input)', fontSize: 11, color: 'var(--text-muted)', display: 'flex', gap: 12 }}>
                                    <span>{selectedModelObj.format?.toUpperCase()}</span>
                                    <span>{selectedModelObj.framework}</span>
                                    <span>{humanSize(selectedModelObj.file_size)}</span>
                                </div>
                            )}
                        </div>
                        <div>
                            <label style={{ fontSize: '13px', fontWeight: 600, marginBottom: '4px', display: 'block' }}>Dataset</label>
                            <select value={selectedDataset} onChange={e => setSelectedDataset(e.target.value)} className="form-select">
                                <option value="">Select a dataset…</option>
                                {datasets.map(d => <option key={d.name} value={d.name}>{d.name} ({d.type})</option>)}
                            </select>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                            <div>
                                <label style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Epochs</label>
                                <input type="number" value={epochs} onChange={e => setEpochs(Number(e.target.value))} className="form-input" min={1} max={100} />
                            </div>
                            <div>
                                <label style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Batch Size</label>
                                <input type="number" value={batchSize} onChange={e => setBatchSize(Number(e.target.value))} className="form-input" min={1} max={128} />
                            </div>
                            <div>
                                <label style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Learning Rate</label>
                                <input type="number" value={lr} onChange={e => setLr(Number(e.target.value))} className="form-input" step={0.0001} />
                            </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '12px', background: 'var(--bg-input)', borderRadius: 'var(--radius-md)' }}>
                            <input type="checkbox" checked={useLora} onChange={e => setUseLora(e.target.checked)} id="use-lora" />
                            <label htmlFor="use-lora" style={{ fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>Use LoRA</label>
                            {useLora && (
                                <div style={{ display: 'flex', gap: '8px', marginLeft: 'auto' }}>
                                    <div style={{ fontSize: '12px' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>r=</span>
                                        <input type="number" value={loraR} onChange={e => setLoraR(Number(e.target.value))} style={{ width: '50px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '6px', padding: '2px 6px', color: 'var(--text-primary)', fontSize: '12px' }} />
                                    </div>
                                    <div style={{ fontSize: '12px' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>α=</span>
                                        <input type="number" value={loraAlpha} onChange={e => setLoraAlpha(Number(e.target.value))} style={{ width: '50px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '6px', padding: '2px 6px', color: 'var(--text-primary)', fontSize: '12px' }} />
                                    </div>
                                </div>
                            )}
                        </div>

                        <div>
                            <label style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Output Model Name</label>
                            <input type="text" className="form-input" style={{ width: '100%' }}
                                value={outputName} onChange={e => setOutputName(e.target.value)}
                                placeholder="Auto-generated" />
                        </div>

                        <button className="btn btn-primary" onClick={startJob} disabled={starting || !selectedModel || !selectedDataset}>
                            {starting ? <><Loader size={14} className="spin" /> Starting…</> : <><Play size={14} /> Start Fine-Tuning</>}
                        </button>

                        <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            Requires: pip install peft datasets transformers torch
                        </p>
                    </div>
                </div>

                {/* Jobs List */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Jobs ({jobs.length})</h3>
                    </div>
                    {loading ? (
                        <div className="loading"><Loader className="spin" size={20} /> Loading…</div>
                    ) : jobs.length === 0 ? (
                        <p className="text-secondary" style={{ padding: '24px 0', textAlign: 'center' }}>No fine-tuning jobs yet</p>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            {jobs.map(job => (
                                <div key={job.id}>
                                    <div
                                        onClick={() => toggleJob(job.id)}
                                        style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '12px 14px', background: 'var(--bg-input)', borderRadius: 'var(--radius-md)', cursor: 'pointer', transition: 'background 0.2s' }}
                                    >
                                        {expandedJob === job.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: statusColor(job.status), flexShrink: 0 }} />
                                        <span style={{ fontWeight: 600, flex: 1, fontSize: '14px' }}>{job.model_name}</span>
                                        <span className="badge">{job.status}</span>
                                        {job.status === 'running' && (
                                            <button className="btn btn-sm btn-danger" onClick={e => { e.stopPropagation(); stopJob(job.id); }}>
                                                <Square size={12} /> Stop
                                            </button>
                                        )}
                                    </div>
                                    {expandedJob === job.id && jobDetails[job.id] && (
                                        <div style={{ padding: '12px 14px', marginTop: '4px', background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--radius-md)', fontSize: '13px' }}>
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '12px' }}>
                                                <div><span style={{ color: 'var(--text-muted)' }}>Dataset:</span> {jobDetails[job.id].dataset}</div>
                                                <div><span style={{ color: 'var(--text-muted)' }}>Step:</span> {jobDetails[job.id].current_step}</div>
                                                <div><span style={{ color: 'var(--text-muted)' }}>Epoch:</span> {jobDetails[job.id].current_epoch}</div>
                                                <div><span style={{ color: 'var(--text-muted)' }}>LoRA:</span> {jobDetails[job.id].config?.use_lora ? `r=${jobDetails[job.id].config.lora_r}` : 'Full'}</div>
                                            </div>
                                            {jobDetails[job.id].metrics?.length > 0 && (
                                                <div style={{ marginBottom: '8px' }}>
                                                    <span style={{ fontWeight: 600 }}>Latest Loss: </span>
                                                    <span style={{ color: 'var(--accent-green)' }}>
                                                        {jobDetails[job.id].metrics[jobDetails[job.id].metrics.length - 1]?.loss?.toFixed(4) || '—'}
                                                    </span>
                                                </div>
                                            )}
                                            {jobDetails[job.id].log?.length > 0 && (
                                                <div style={{ background: 'var(--bg-input)', padding: '8px 12px', borderRadius: '8px', fontFamily: 'var(--font-mono)', fontSize: '11px', maxHeight: '120px', overflowY: 'auto' }}>
                                                    {jobDetails[job.id].log.map((line, i) => (
                                                        <div key={i} style={{ color: line.startsWith('Error') ? 'var(--accent-red)' : 'var(--text-secondary)' }}>{line}</div>
                                                    ))}
                                                </div>
                                            )}
                                            {jobDetails[job.id].error && (
                                                <div style={{ color: 'var(--accent-red)', marginTop: '8px', padding: '8px', background: 'rgba(239,68,68,0.1)', borderRadius: '8px', fontSize: '12px' }}>
                                                    {jobDetails[job.id].error}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
