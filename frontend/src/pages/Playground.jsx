import React, { useState, useRef } from 'react';
import { Play, Upload, Image, MessageSquare, Sparkles, Crosshair, Loader2 } from 'lucide-react';
import { API_BASE } from '../api/client';

const TABS = [
    { id: 'classify', label: 'Image Classification', icon: Image },
    { id: 'detect', label: 'Object Detection', icon: Crosshair },
    { id: 'text', label: 'Text Generation', icon: MessageSquare },
    { id: 'imagegen', label: 'Image Generation', icon: Sparkles },
];

export default function Playground() {
    const [tab, setTab] = useState('classify');
    const [models, setModels] = useState([]);
    const [selectedModel, setSelectedModel] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [preview, setPreview] = useState(null);
    const [prompt, setPrompt] = useState('');
    const fileRef = useRef(null);

    React.useEffect(() => {
        fetch(`${API_BASE}/models`).then(r => r.json()).then(setModels).catch(() => { });
    }, []);

    const handleImageSelect = (e) => {
        const file = e.target.files[0];
        if (file) {
            const url = URL.createObjectURL(file);
            setPreview(url);
            setResult(null);
            setError(null);
        }
    };

    const runInference = async () => {
        if (!selectedModel) { setError('Select a model first'); return; }
        setLoading(true);
        setError(null);
        setResult(null);

        try {
            const fd = new FormData();
            fd.append('model_id', selectedModel);

            if (tab === 'classify' || tab === 'detect') {
                const file = fileRef.current?.files?.[0];
                if (!file) { setError('Upload an image first'); setLoading(false); return; }
                fd.append('image', file);
                if (tab === 'detect') fd.append('confidence_threshold', '0.3');

                const endpoint = tab === 'classify' ? '/inference/classify' : '/inference/detect';
                const res = await fetch(`${API_BASE}${endpoint}`, { method: 'POST', body: fd });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Inference failed');
                setResult(data);
            } else if (tab === 'text') {
                if (!prompt.trim()) { setError('Enter a prompt'); setLoading(false); return; }
                fd.append('prompt', prompt);
                fd.append('max_tokens', '256');
                fd.append('temperature', '0.7');
                const res = await fetch(`${API_BASE}/inference/generate-text`, { method: 'POST', body: fd });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Generation failed');
                setResult(data);
            } else if (tab === 'imagegen') {
                if (!prompt.trim()) { setError('Enter a prompt'); setLoading(false); return; }
                fd.append('prompt', prompt);
                fd.append('width', '512');
                fd.append('height', '512');
                const res = await fetch(`${API_BASE}/inference/generate-image`, { method: 'POST', body: fd });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Generation failed');
                setResult(data);
            }
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>
            <div className="page-header">
                <h2>Playground</h2>
                <p>Test your models interactively — classify images, detect objects, generate text or images</p>
            </div>

            {/* Tabs */}
            <div className="tab-bar">
                {TABS.map(({ id, label, icon: Icon }) => (
                    <button
                        key={id}
                        className={`tab-item ${tab === id ? 'active' : ''}`}
                        onClick={() => { setTab(id); setResult(null); setError(null); }}
                    >
                        <Icon size={16} />
                        {label}
                    </button>
                ))}
            </div>

            <div className="grid-2">
                {/* Input Panel */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Input</h3>
                    </div>

                    {/* Model Selector */}
                    <div className="form-group">
                        <label className="form-label">Model</label>
                        <select className="form-select" value={selectedModel} onChange={e => setSelectedModel(e.target.value)}>
                            <option value="">Select a model...</option>
                            {models.map(m => (
                                <option key={m.id} value={m.id}>{m.name} ({m.framework})</option>
                            ))}
                        </select>
                    </div>

                    {/* Image input for classify/detect */}
                    {(tab === 'classify' || tab === 'detect') && (
                        <div className="form-group">
                            <label className="form-label">Image</label>
                            <div
                                className={`file-upload-zone ${preview ? '' : ''}`}
                                onClick={() => fileRef.current?.click()}
                            >
                                {preview ? (
                                    <img src={preview} alt="Preview" style={{ maxWidth: '100%', maxHeight: '260px', borderRadius: '8px' }} />
                                ) : (
                                    <>
                                        <Upload size={40} />
                                        <p>Click to upload an image</p>
                                        <p className="text-muted" style={{ fontSize: '12px' }}>JPG, PNG, or WebP</p>
                                    </>
                                )}
                                <input
                                    ref={fileRef}
                                    type="file"
                                    accept="image/*"
                                    onChange={handleImageSelect}
                                    style={{ display: 'none' }}
                                />
                            </div>
                        </div>
                    )}

                    {/* Text input for text/imagegen */}
                    {(tab === 'text' || tab === 'imagegen') && (
                        <div className="form-group">
                            <label className="form-label">
                                {tab === 'text' ? 'Prompt' : 'Image Description'}
                            </label>
                            <textarea
                                className="form-input"
                                rows={4}
                                value={prompt}
                                onChange={e => setPrompt(e.target.value)}
                                placeholder={tab === 'text' ? 'Once upon a time...' : 'A beautiful sunset over mountains...'}
                                style={{ resize: 'vertical', fontFamily: 'inherit' }}
                            />
                        </div>
                    )}

                    <button className="btn btn-primary btn-lg w-full" onClick={runInference} disabled={loading}>
                        {loading ? <><Loader2 size={18} className="spinner" /> Running...</> : <><Play size={18} /> Run Inference</>}
                    </button>
                </div>

                {/* Output Panel */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Output</h3>
                    </div>

                    {error && (
                        <div style={{ padding: '14px 18px', background: 'var(--accent-red-glow)', borderRadius: 'var(--radius-md)', color: 'var(--accent-red)', fontSize: '14px', marginBottom: '16px' }}>
                            {error}
                        </div>
                    )}

                    {loading && (
                        <div className="loading-overlay">
                            <div className="spinner"></div>
                            <p>Running inference...</p>
                        </div>
                    )}

                    {!loading && !result && !error && (
                        <div className="empty-state">
                            <Play size={48} />
                            <h3>Ready to Test</h3>
                            <p>Select a model, provide input, and click "Run Inference"</p>
                        </div>
                    )}

                    {/* Classification Results */}
                    {result && tab === 'classify' && result.predictions && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            {result.predictions.map((p, i) => (
                                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                                    <span style={{ minWidth: '24px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', fontSize: '12px' }}>#{i + 1}</span>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                                            <span style={{ fontWeight: 600, fontSize: '14px' }}>{p.label}</span>
                                            <span className="text-mono" style={{ color: 'var(--accent-blue)', fontWeight: 700 }}>{p.confidence}%</span>
                                        </div>
                                        <div className="progress-bar">
                                            <div className="progress-bar-fill" style={{ width: `${p.confidence}%` }}></div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Detection Results */}
                    {result && tab === 'detect' && (
                        <div>
                            <div style={{ marginBottom: '12px', color: 'var(--accent-green)', fontWeight: 600 }}>
                                {result.num_detections} object{result.num_detections !== 1 ? 's' : ''} detected
                            </div>
                            {result.detections?.map((d, i) => (
                                <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '13px' }}>
                                    <span className="badge badge-info">Class {d.class_id}</span>
                                    <span style={{ marginLeft: '10px', fontFamily: 'var(--font-mono)' }}>{d.confidence}%</span>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Text Results */}
                    {result && tab === 'text' && (
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', lineHeight: 1.8, whiteSpace: 'pre-wrap', color: 'var(--text-primary)', padding: '16px', background: 'var(--bg-input)', borderRadius: 'var(--radius-md)' }}>
                            {result.generated_text}
                        </div>
                    )}

                    {/* Image Generation Results */}
                    {result && tab === 'imagegen' && result.image_base64 && (
                        <img
                            src={`data:image/png;base64,${result.image_base64}`}
                            alt="Generated"
                            style={{ width: '100%', borderRadius: 'var(--radius-md)' }}
                        />
                    )}
                </div>
            </div>
        </div>
    );
}
