import React, { lazy, Suspense, useState, useEffect } from 'react';
import { GraduationCap, Zap, Wrench, CloudUpload, Play, RefreshCw, CheckCircle, XCircle, AlertCircle, Cpu, Activity } from 'lucide-react';
import { API_BASE } from '../api/client';

const BasicTraining = lazy(() => import('./Training'));
const AdvancedTraining = lazy(() => import('./AdvancedTraining'));
const HubPublisher = lazy(() => import('./HubPublisher'));

const PRESET_MODELS = [
  // ── Multimodal Vision Models (priority — thinking, tool use, audio/visual) ──
  { value: 'unsloth/Qwen3.6-27B', label: 'Qwen3.6 27B (vision, MTP)', vram: '~18GB 4-bit', vision: true },
  { value: 'unsloth/Qwen3.5-9B-Base', label: 'Qwen3.5 9B (vision)', vram: '~8GB 4-bit', vision: true },
  { value: 'unsloth/gemma-4-E4B-it-unsloth-bnb-4bit', label: 'Gemma 4 E4B (vision, MoE)', vram: '~4GB 4-bit', vision: true },
  { value: 'unsloth/gemma-4-12b-it', label: 'Gemma 4 12B (vision, unified)', vram: '~20GB 4-bit', vision: true },
  // ── Text-Only (kept for fast testing) ──
  { value: 'unsloth/tinyllama-bnb-4bit', label: 'TinyLlama 1B (fast test)', vram: '~2GB' },
];

// ── Unsloth Finetune Tab (inline) ────────────────────────────────────────
function FinetuneTab() {
  const [form, setForm] = useState({
    model_name: 'unsloth/tinyllama-bnb-4bit',
    dataset_source: 'J:/NPU-STACK/datasets/train.jsonl',
    output_name: 'Nirvana/Magneto-FT',
    num_epochs: 1,
    learning_rate: '0.0002',
    lora_r: 8,
    lora_alpha: 16,
  });
  const [submitting, setSubmitting] = useState(false);
  const [activeJob, setActiveJob] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [trainedModels, setTrainedModels] = useState([]);
  const [activeJobs, setActiveJobs] = useState({});

  // Load trained checkpoints
  useEffect(() => {
    fetch(`${API_BASE}/finetune/checkpoints`).then(r => r.json()).then(d => {
      setTrainedModels((d.checkpoints || []).map(c => ({
        value: c.adapter?.dir || c.name,
        label: `📦 ${c.name} (${c.adapter?.size_mb || '?'}MB${c.gguf_files?.length ? ', GGUF' : ''})`,
      })));
    }).catch(() => {});
  }, []);

  // Poll ALL active jobs (not just UI-initiated)
  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const r = await fetch(`${API_BASE}/finetune/jobs`);
        if (!r.ok) return;
        const all = await r.json();
        setActiveJobs(all || {});
      } catch {}
    }, 30000);
    return () => clearInterval(timer);
  }, []);

  // Poll active job details
  useEffect(() => {
    if (!activeJob || jobStatus === 'complete' || jobStatus === 'failed') return;
    const timer = setInterval(async () => {
      try {
        const r = await fetch(`${API_BASE}/finetune/jobs/${activeJob}`);
        if (!r.ok) return;
        const j = await r.json();
        setJobStatus(j.status);
        if (j.output_lines) setLogs(j.output_lines);
        if (j.error) setLogs(prev => [...prev, 'ERROR: ' + j.error.slice(-200)]);
      } catch {}
    }, 30000);  // poll every 30s — training jobs take hours
    return () => clearInterval(timer);
  }, [activeJob, jobStatus]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setLogs([]);
    setJobStatus(null);

    try {
      const fd = new FormData();
      fd.append('model_name', form.model_name);
      fd.append('dataset_source', form.dataset_source);
      fd.append('output_name', form.output_name);
      fd.append('num_epochs', form.num_epochs);
      fd.append('learning_rate', form.learning_rate);
      fd.append('lora_r', form.lora_r);
      fd.append('lora_alpha', form.lora_alpha);

      const r = await fetch(`${API_BASE}/finetune/train`, { method: 'POST', body: fd });
      if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
      const data = await r.json();
      setActiveJob(data.job_id);
      setJobStatus('starting');
      setLogs([`Job ${data.job_id} started — model: ${form.model_name}`]);
    } catch (e) {
      setError(e.message);
    }
    setSubmitting(false);
  };

  const update = (k, v) => setForm(prev => ({ ...prev, [k]: v }));

  return (
    <div style={{ padding: '20px', maxWidth: 700 }}>
      <div style={{
        padding: 14, borderRadius: 10, marginBottom: 16,
        background: 'rgba(102,126,234,0.08)', border: '1px solid rgba(102,126,234,0.2)',
      }}>
        <h4 style={{ margin: '0 0 6px', fontSize: 14 }}><Cpu size={16} style={{verticalAlign:'middle',marginRight:6}}/> Unsloth QLoRA Finetuning</h4>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)' }}>
          Trains in <code>.venv-train</code> (Python 3.12, torch 2.12+cu130). RTX 5090 32GB detected.
          Dataset: 250 Magneto SFT entries.
        </p>
      </div>

      {/* Running Jobs — shows ALL jobs regardless of how they were started */}
      {Object.keys(activeJobs).length > 0 && (
        <div style={{ marginBottom: 16, padding: 14, borderRadius: 10, background: 'var(--bg-card)', border: '1px solid var(--border-color)' }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10, color: 'var(--text-primary)' }}>
            <Activity size={14} style={{verticalAlign:'middle',marginRight:6}} /> 
            Running Jobs ({Object.keys(activeJobs).length})
          </div>
          {Object.entries(activeJobs).map(([jid, job]) => (
            <div key={jid} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--border-color)', fontSize: 12 }}>
              <span style={{ fontWeight: 600, fontFamily: 'monospace', fontSize: 11 }}>{jid}</span>
              <span style={{ padding: '2px 8px', borderRadius: 12, fontSize: 10,
                background: job.status === 'training' ? '#1a3a2a' : job.status === 'complete' ? '#1a2a3a' : job.status === 'failed' ? '#3a1a1a' : '#3a2a1a',
                color: job.status === 'training' ? '#4ade80' : job.status === 'complete' ? '#60a5fa' : job.status === 'failed' ? '#f87171' : '#d29922',
              }}>{job.status || 'starting'}</span>
              <span style={{ color: 'var(--text-muted)', flex: 1 }}>{job.model}</span>
              <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{job.output}</span>
            </div>
          ))}
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>Refreshes every 30s — shows all jobs (UI + console)</div>
        </div>
      )}

      {error && (
        <div style={{ padding: 10, borderRadius: 8, marginBottom: 12, background: 'rgba(248,81,73,0.1)', border: '1px solid #f8514966', fontSize: 13, color: '#f87171' }}>
          <XCircle size={14} style={{verticalAlign:'middle',marginRight:6}}/>{error}
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Model */}
        <div>
          <label style={{ fontSize: 11, color: '#a0aec0', fontWeight: 600, marginBottom: 4, display: 'block' }}>Base Model</label>
          <select value={form.model_name} onChange={e => update('model_name', e.target.value)}
            style={{ width: '100%', padding: '8px 10px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 12 }}>
            <optgroup label="Multimodal Vision Models">
            {PRESET_MODELS.filter(m => m.vision).map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
            </optgroup>
            <optgroup label="Fast Test">
            {PRESET_MODELS.filter(m => !m.vision).map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
            </optgroup>
            {trainedModels.length > 0 && (
              <optgroup label="Trained Checkpoints (G:/TRAINING-GROUNDS)">
                {trainedModels.map(m => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </optgroup>
            )}
          </select>
          </select>
        </div>

        {/* Row: dataset + output */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={{ fontSize: 11, color: '#a0aec0', fontWeight: 600, marginBottom: 4, display: 'block' }}>Dataset Path</label>
            <input value={form.dataset_source} onChange={e => update('dataset_source', e.target.value)}
              placeholder="J:/NPU-STACK/datasets/train.jsonl"
              style={{ width: '100%', boxSizing: 'border-box', padding: '8px 10px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'monospace' }} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#a0aec0', fontWeight: 600, marginBottom: 4, display: 'block' }}>Output Name</label>
            <input value={form.output_name} onChange={e => update('output_name', e.target.value)}
              placeholder="Nirvana/Magneto-FT"
              style={{ width: '100%', boxSizing: 'border-box', padding: '8px 10px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 12 }} />
          </div>
        </div>

        {/* Row: epochs, LR, lora_r, lora_alpha */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 }}>
          {[
            { k: 'num_epochs', label: 'Epochs', type: 'number', min: 1, max: 20 },
            { k: 'learning_rate', label: 'Learning Rate', type: 'text' },
            { k: 'lora_r', label: 'LoRA Rank', type: 'number', min: 1, max: 128 },
            { k: 'lora_alpha', label: 'LoRA Alpha', type: 'number', min: 1, max: 256 },
          ].map(({ k, label, type, min, max }) => (
            <div key={k}>
              <label style={{ fontSize: 10, color: '#a0aec0', fontWeight: 600, marginBottom: 4, display: 'block' }}>{label}</label>
              <input type={type} min={min} max={max}
                value={form[k]} onChange={e => update(k, type === 'number' ? Number(e.target.value) : e.target.value)}
                style={{ width: '100%', boxSizing: 'border-box', padding: '8px 10px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 12, fontFamily: type === 'text' ? 'monospace' : 'inherit' }} />
            </div>
          ))}
        </div>

        <button type="submit" disabled={submitting || !form.dataset_source}
          style={{
            padding: '10px 20px', borderRadius: 8, border: 'none',
            background: submitting ? '#d29922' : '#4ade80',
            color: '#000', fontSize: 14, fontWeight: 700, cursor: submitting ? 'default' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}>
          {submitting ? <RefreshCw size={16} /> : <Play size={16} />}
          {submitting ? 'Launching...' : 'Start Unsloth QLoRA Training'}
        </button>
      </form>

      {/* Job status */}
      {activeJob && (
        <div style={{ marginTop: 16, padding: 14, borderRadius: 10, background: 'var(--bg-card)', border: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            {jobStatus === 'complete' ? <CheckCircle size={16} color="#4ade80" /> :
             jobStatus === 'failed' ? <XCircle size={16} color="#f87171" /> :
             <AlertCircle size={16} color="#d29922" />}
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              Job: {activeJob}
            </span>
            <span style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 12,
              background: jobStatus === 'complete' ? '#1a3a2a' : jobStatus === 'failed' ? '#3a1a1a' : '#3a2a1a',
              color: jobStatus === 'complete' ? '#4ade80' : jobStatus === 'failed' ? '#f87171' : '#d29922',
            }}>
              {jobStatus || 'starting'}
            </span>
          </div>

          {logs.length > 0 && (
            <div style={{
              maxHeight: 300, overflow: 'auto', padding: '8px 10px',
              borderRadius: 6, background: 'var(--bg-input)', border: '1px solid var(--border-color)',
              fontFamily: 'monospace', fontSize: 11, lineHeight: 1.6, color: 'var(--text-muted)',
            }}>
              {logs.map((line, i) => (
                <div key={i} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{line}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── TrainingCenter (main) ────────────────────────────────────────────────

const TABS = [
  { id: 'basic', label: 'Basic Training', icon: GraduationCap, desc: 'Classic PyTorch training with CIFAR-10/MNIST' },
  { id: 'advanced', label: 'Advanced', icon: Zap, desc: 'Multi-source fine-tuning with LoRA adapters' },
  { id: 'finetune', label: 'Fine-Tuning', icon: Wrench, desc: 'Domain-specific model fine-tuning with dataset upload' },
  { id: 'publish', label: 'HF Publisher', icon: CloudUpload, desc: 'Publish models, GGUF files, & model cards to HuggingFace' },
];

export default function TrainingCenter() {
  const [activeTab, setActiveTab] = useState('basic');

  const renderTab = () => {
    switch (activeTab) {
      case 'basic': return <BasicTraining />;
      case 'advanced': return <AdvancedTraining />;
      case 'finetune': return <FinetuneTab />;
      case 'publish': return <HubPublisher />;
      default: return null;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, maxWidth: '100%' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px 12px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-secondary)' }}>
        <h2 style={{ margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <GraduationCap size={22} color="#667eea" />
          Training Center
        </h2>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)' }}>
          Basic training · Advanced fine-tuning · LoRA adapters · HuggingFace publishing — unified workflow
        </p>
      </div>

      {/* Tab Bar */}
      <div style={{
        display: 'flex', gap: 0, borderBottom: '1px solid var(--border-color)',
        padding: '0 16px', background: 'var(--bg-card)', flexWrap: 'wrap',
      }}>
        {TABS.map(tab => (
          <button key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
              padding: '10px 18px', border: 'none', borderBottom: activeTab === tab.id ? '2px solid #667eea' : '2px solid transparent',
              background: 'transparent', cursor: 'pointer',
              color: activeTab === tab.id ? '#667eea' : 'var(--text-muted)',
              fontSize: 12, fontWeight: 500, transition: 'color 0.15s',
              minWidth: 100,
            }}>
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={{ overflow: 'auto' }}>
        <Suspense fallback={<div className="loading-overlay"><div className="spinner"/><span>Loading...</span></div>}>
          {renderTab()}
        </Suspense>
      </div>
    </div>
  );
}
