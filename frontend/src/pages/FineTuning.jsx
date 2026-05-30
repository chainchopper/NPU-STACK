import React, { useState, useEffect } from 'react';
import { Wrench, Play, Loader, Square, ChevronDown, ChevronRight } from 'lucide-react';
import ActivityLogCard from '../components/ActivityLogCard';
import CapabilityPill from '../components/CapabilityPill';
import ContextWizard from '../components/ContextWizard';
import OperationNotice from '../components/OperationNotice';
import { apiUrl, diagnoseBackendError, inferBackendOrigin } from '../api/client';

const FINETUNE_WIZARD_STEPS = [
    {
        title: 'Fine-Tuning Overview',
        body: 'Fine-tuning adapts a pre-trained base model to your specific domain or task using your own dataset, dramatically outperforming general-purpose models at a fraction of the training cost.',
    },
    {
        title: 'LoRA vs Full Fine-Tuning',
        body: <>Enable <strong>LoRA</strong> to train only a small set of adapter weights (typical r=8-64). This uses 10-30× less VRAM than full fine-tuning and is sufficient for most domain-adaptation tasks. Disable LoRA only for task-critical accuracy gains.</>,
    },
    {
        title: 'Dataset Format',
        body: <>Your dataset should be a <code>.jsonl</code> file with rows like: <code>{'{"text": "..."}'}</code> for causal LM, or <code>{'{"prompt": "...", "response": "..."}'}</code> for instruction tuning. Upload via the Datasets tab.</>,
    },
    {
        title: 'Hyperparameter Guidance',
        body: 'Start with Epochs=3, Batch Size=4, LR=2e-4. Increase batch size if VRAM allows. Lower LR (e.g. 5e-5) if training loss oscillates. LoRA r=16 is a solid default — increase to 64 for harder tasks.',
    },
];

export default function FineTuning() {
    const [models, setModels] = useState([]);
    const [datasets, setDatasets] = useState([]);
    const [jobs, setJobs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [starting, setStarting] = useState(false);
    const [expandedJob, setExpandedJob] = useState(null);
    const [jobDetails, setJobDetails] = useState({});
    const [ecosystem, setEcosystem] = useState(null);
    const [notice, setNotice] = useState(null);
    const [activityLog, setActivityLog] = useState([]);
    const [copyHint, setCopyHint] = useState('');
    const [checkingEcosystem, setCheckingEcosystem] = useState(false);
    const [lastEcosystemCheckAt, setLastEcosystemCheckAt] = useState(null);
    const [ecosystemCheckFailures, setEcosystemCheckFailures] = useState(0);
    const [ecosystemCheckError, setEcosystemCheckError] = useState('');

    const addLog = (line) => {
        const timestamp = new Date().toLocaleTimeString();
        setActivityLog((prev) => [...prev.slice(-59), `${timestamp} — ${line}`]);
    };

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

    const refreshEcosystemStatus = async ({ logResult = false } = {}) => {
        setCheckingEcosystem(true);
        try {
            const ecosystemRes = await fetch(apiUrl('/finetune/status'));
            if (!ecosystemRes.ok) {
                throw new Error(`Ecosystem status HTTP ${ecosystemRes.status}`);
            }

            const ecosystemData = await ecosystemRes.json();
            setEcosystem(ecosystemData);
            setEcosystemCheckFailures(0);
            setEcosystemCheckError('');

            const now = new Date();
            setLastEcosystemCheckAt(now);

            if (logResult) {
                const unslothState = ecosystemData?.unsloth || {};
                const missing = [
                    !unslothState.unsloth_available ? 'unsloth' : null,
                    !unslothState.peft_available ? 'peft' : null,
                    !unslothState.trl_available ? 'trl' : null,
                    !unslothState.bitsandbytes_available ? 'bitsandbytes' : null,
                ].filter(Boolean);

                addLog(`Environment check @ ${now.toLocaleString()}: ready=${unslothState.ready ? 'yes' : 'no'}, cuda=${unslothState.cuda_available ? 'yes' : 'no'}, missing=${missing.length ? missing.join(',') : 'none'}`);
            }
        } catch (statusErr) {
            const reason = diagnoseBackendError(statusErr, 'Fine-tune ecosystem status');
            setEcosystemCheckFailures((prev) => prev + 1);
            setEcosystemCheckError(reason);
            if (logResult) {
                addLog(`Environment check failed @ ${new Date().toLocaleString()}: ${reason}`);
            }
            throw statusErr;
        } finally {
            setCheckingEcosystem(false);
        }
    };

    const fetchData = async () => {
        try {
            const [modelsRes, datasetsRes, jobsRes] = await Promise.all([
                fetch(apiUrl('/models')).then(r => r.json()),
                fetch(apiUrl('/datasets')).then(r => r.json()),
                fetch(apiUrl('/finetune/jobs')).then(r => r.json()),
            ]);
            setModels(modelsRes.models || []);
            setDatasets(datasetsRes.datasets || []);
            setJobs(jobsRes.jobs || []);

            try {
                await refreshEcosystemStatus({ logResult: false });
            } catch (statusErr) {
                addLog(`Ecosystem status unavailable: ${diagnoseBackendError(statusErr, 'Fine-tune ecosystem status')}`);
            }
        } catch (e) {
            setNotice({
                tone: 'warning',
                title: 'Fine-tuning data unavailable',
                message: diagnoseBackendError(e, 'Fine-tuning setup'),
                details: e?.message || null,
            });
            addLog(`Fine-tuning setup failed: ${diagnoseBackendError(e, 'Fine-tuning setup')}`);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(async () => {
            try {
                const res = await fetch(apiUrl('/finetune/jobs'));
                const data = await res.json();
                setJobs(data.jobs || []);
            } catch (e) { }
        }, 3000);
        return () => clearInterval(interval);
    }, []);

    const startJob = async () => {
        if (!selectedModel || !selectedDataset) return;
        setStarting(true);
        addLog(`Starting fine-tuning job (model ${selectedModel}, dataset ${selectedDataset})`);
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

            await fetch(apiUrl('/finetune/start'), { method: 'POST', body: form });
            await fetchData();
            setNotice({ tone: 'success', title: 'Fine-tuning started', message: 'New fine-tuning job has been submitted.' });
            addLog('Fine-tuning job submitted');
        } catch (e) {
            setNotice({
                tone: 'danger',
                title: 'Failed to start fine-tuning',
                message: diagnoseBackendError(e, 'Fine-tuning start'),
                details: e?.message || null,
            });
            addLog(`Fine-tuning start failed: ${diagnoseBackendError(e, 'Fine-tuning start')}`);
        }
        setStarting(false);
    };

    const stopJob = async (jobId) => {
        addLog(`Stop requested for fine-tuning job ${jobId}`);
        try {
            await fetch(apiUrl(`/finetune/stop/${jobId}`), { method: 'POST' });
            await fetchData();
            setNotice({ tone: 'info', title: 'Stop requested', message: `Stop requested for job ${jobId}.` });
            addLog(`Stop request submitted for job ${jobId}`);
        } catch (e) {
            setNotice({
                tone: 'danger',
                title: 'Failed to stop job',
                message: diagnoseBackendError(e, 'Fine-tuning stop'),
                details: e?.message || null,
            });
            addLog(`Stop failed for job ${jobId}: ${diagnoseBackendError(e, 'Fine-tuning stop')}`);
        }
    };

    const toggleJob = async (jobId) => {
        if (expandedJob === jobId) {
            setExpandedJob(null);
            return;
        }
        setExpandedJob(jobId);
        addLog(`Loading details for fine-tuning job ${jobId}`);
        try {
            const res = await fetch(apiUrl(`/finetune/status/${jobId}`));
            const data = await res.json();
            setJobDetails(prev => ({ ...prev, [jobId]: data }));
            addLog(`Loaded details for job ${jobId}`);
        } catch (e) {
            setNotice({
                tone: 'warning',
                title: 'Job details unavailable',
                message: diagnoseBackendError(e, 'Fine-tuning job details'),
                details: e?.message || null,
            });
            addLog(`Job detail fetch failed for ${jobId}: ${diagnoseBackendError(e, 'Fine-tuning job details')}`);
        }
    };

    const statusColor = (status) => {
        switch (status) {
            case 'running': return 'var(--accent-blue)';
            case 'completed': return 'var(--accent-green)';
            case 'failed': return 'var(--accent-red)';
            case 'stopping': return 'var(--accent-amber)';
            case 'stopped': return 'var(--accent-amber)';
            default: return 'var(--text-muted)';
        }
    };

    const unsloth = ecosystem?.unsloth || {};
    const hub = ecosystem?.hub || {};
    const backendOrigin = inferBackendOrigin();
    const missingDeps = [
        !unsloth.unsloth_available ? 'unsloth' : null,
        !unsloth.peft_available ? 'peft' : null,
        !unsloth.trl_available ? 'trl' : null,
        !unsloth.bitsandbytes_available ? 'bitsandbytes' : null,
    ].filter(Boolean);

    const installCommand = (() => {
        if (missingDeps.length === 0) return '';

        const deps = [];
        if (missingDeps.includes('peft')) deps.push('peft');
        if (missingDeps.includes('trl')) deps.push('trl');
        if (missingDeps.includes('bitsandbytes')) deps.push('bitsandbytes');

        const pieces = [];
        if (missingDeps.includes('unsloth')) {
            pieces.push("pip install \"unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git\"");
        }
        if (deps.length > 0) {
            pieces.push(`pip install ${deps.join(' ')}`);
        }
        return pieces.join(' && ');
    })();

    const copyInstallCommand = async () => {
        if (!installCommand) return;
        try {
            await navigator.clipboard.writeText(installCommand);
            setCopyHint('Install command copied. Running environment check...');
            addLog('Copied Unsloth dependency install command');

            try {
                await refreshEcosystemStatus({ logResult: true });
                setCopyHint('Install command copied. Environment check refreshed.');
            } catch {
                setCopyHint('Install command copied. Environment check failed; see notices/log.');
            }
        } catch {
            setCopyHint('Copy failed. Select and copy the command manually.');
            addLog('Clipboard copy failed for Unsloth dependency command');
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

            <OperationNotice
                tone={notice?.tone || 'info'}
                title={notice?.title}
                message={notice?.message}
                details={notice?.details}
            />

            <div className="card" style={{ marginBottom: 16 }}>
                <div className="card-header">
                    <h3 className="card-title">Unsloth Ecosystem Readiness</h3>
                    <button className="btn btn-sm btn-outline" onClick={() => refreshEcosystemStatus({ logResult: true })} disabled={checkingEcosystem}>
                        {checkingEcosystem ? <><Loader size={12} className="spin" /> Checking…</> : 'Run Environment Check'}
                    </button>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
                    <CapabilityPill active={Boolean(unsloth.ready)} label={`Unsloth Ready: ${unsloth.ready ? 'Yes' : 'No'}`} />
                    <CapabilityPill active={Boolean(unsloth.accelerated_available)} label={`Accelerated Mode: ${unsloth.accelerated_available ? 'Yes' : 'No'}`} />
                    <CapabilityPill active={Boolean(unsloth.fallback_available)} label={`CPU Fallback: ${unsloth.fallback_available ? 'Yes' : 'No'}`} />
                    <CapabilityPill active={Boolean(unsloth.unsloth_available)} label={`Unsloth Installed: ${unsloth.unsloth_available ? 'Yes' : 'No'}`} />
                    <CapabilityPill active={Boolean(unsloth.cuda_available)} label={`CUDA: ${unsloth.cuda_available ? 'Yes' : 'No'}`} />
                    <CapabilityPill active={Boolean(unsloth.peft_available)} label={`PEFT: ${unsloth.peft_available ? 'Yes' : 'No'}`} />
                    <CapabilityPill active={Boolean(unsloth.trl_available)} label={`TRL: ${unsloth.trl_available ? 'Yes' : 'No'}`} />
                    <CapabilityPill active={Boolean(unsloth.bitsandbytes_available)} label={`bitsandbytes: ${unsloth.bitsandbytes_available ? 'Yes' : 'No'}`} />
                    <CapabilityPill active={Boolean(hub.authenticated)} label={`HF Auth: ${hub.authenticated ? 'Yes' : 'No'}`} />
                </div>

                <p className="text-secondary" style={{ fontSize: 13, marginBottom: 8 }}>
                    Best mode available: <strong>{unsloth.best_mode === 'cuda-accelerated' ? 'CUDA accelerated' : unsloth.best_mode === 'cpu-fallback' ? 'CPU fallback' : 'missing dependencies'}</strong>
                </p>
                {unsloth.recommendation && (
                    <p className="text-secondary" style={{ fontSize: 12, marginBottom: 12, fontStyle: 'italic' }}>
                        {unsloth.recommendation}
                    </p>
                )}

                {missingDeps.length > 0 ? (
                    <OperationNotice
                        tone="warning"
                        title="Missing optional Unsloth dependencies"
                        message={`Current environment is missing: ${missingDeps.join(', ')}.`}
                        details="This page's classic fine-tuning route can still run with PEFT/Transformers. Unsloth can run in CPU fallback mode when CUDA is unavailable, but acceleration needs CUDA plus the full stack installed portably via pip on the target machine."
                    />
                ) : (
                    <p className="text-secondary" style={{ fontSize: 13 }}>
                        Unsloth stack is available; CUDA will unlock accelerated QLoRA, while CPU fallback remains supported.
                    </p>
                )}

                {ecosystemCheckFailures >= 2 && (
                    <OperationNotice
                        tone="danger"
                        title="Backend environment checks are unstable"
                        message="Repeated readiness checks failed. Backend may be down or on a different port."
                        details={ecosystemCheckError || 'Verify backend availability and configured API port.'}
                        footer={(
                            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
                                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                                    Detected backend origin: <code>{backendOrigin || 'unknown'}</code>
                                </span>
                                <button
                                    className="btn btn-sm btn-outline"
                                    onClick={() => refreshEcosystemStatus({ logResult: true })}
                                    disabled={checkingEcosystem}
                                >
                                    {checkingEcosystem ? 'Retrying…' : 'Retry now'}
                                </button>
                            </div>
                        )}
                    />
                )}

                {lastEcosystemCheckAt && (
                    <p className="text-secondary" style={{ fontSize: 12, marginTop: 8 }}>
                        Last check: {lastEcosystemCheckAt.toLocaleString()}
                    </p>
                )}

                {missingDeps.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>Suggested install command</div>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                            <code style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', padding: '6px 10px', borderRadius: 8, fontSize: 12 }}>
                                {installCommand}
                            </code>
                            <button className="btn btn-sm btn-outline" onClick={copyInstallCommand}>Copy</button>
                        </div>
                        {copyHint && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>{copyHint}</div>}
                        <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
                            Portable install only — no local Unsloth checkout is assumed by this repo.
                        </div>
                    </div>
                )}
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

            <ActivityLogCard
                title="Fine-Tuning Activity"
                lines={activityLog}
                emptyMessage="No fine-tuning activity recorded yet."
                onClear={() => setActivityLog([])}
                style={{ marginTop: 16 }}
            />
            <ContextWizard id="finetune" steps={FINETUNE_WIZARD_STEPS} accentVar="--accent-purple" />
        </div>
    );
}
