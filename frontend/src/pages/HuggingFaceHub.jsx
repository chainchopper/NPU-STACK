import React, { useState } from 'react';
import { Search, Download, ExternalLink, Tag, Heart, ArrowDown, Loader2, Check, Filter } from 'lucide-react';
import { API_BASE } from '../api/client';

const TASK_FILTERS = [
    { value: '', label: 'All Tasks' },
    { value: 'image-classification', label: 'Image Classification' },
    { value: 'object-detection', label: 'Object Detection' },
    { value: 'text-generation', label: 'Text Generation' },
    { value: 'text2text-generation', label: 'Text-to-Text' },
    { value: 'text-to-image', label: 'Text to Image' },
    { value: 'feature-extraction', label: 'Feature Extraction' },
    { value: 'automatic-speech-recognition', label: 'Speech Recognition' },
    { value: 'image-segmentation', label: 'Segmentation' },
    { value: 'token-classification', label: 'Token Classification' },
];

export default function HuggingFaceHub() {
    const [query, setQuery] = useState('');
    const [task, setTask] = useState('');
    const [results, setResults] = useState([]);
    const [searching, setSearching] = useState(false);
    const [downloading, setDownloading] = useState({});
    const [downloaded, setDownloaded] = useState({});
    const [detail, setDetail] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [error, setError] = useState(null);

    const searchModels = async () => {
        setSearching(true);
        setError(null);
        try {
            const params = new URLSearchParams({ q: query, limit: '20' });
            if (task) params.set('task', task);
            const res = await fetch(`${API_BASE}/huggingface/search?${params}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Search failed');
            setResults(data.models || []);
        } catch (e) {
            setError(e.message);
        } finally {
            setSearching(false);
        }
    };

    const viewDetails = async (repoId) => {
        setDetailLoading(true);
        setDetail(null);
        try {
            const res = await fetch(`${API_BASE}/huggingface/model/${encodeURIComponent(repoId)}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load');
            setDetail(data);
        } catch (e) {
            setError(e.message);
        } finally {
            setDetailLoading(false);
        }
    };

    const downloadModel = async (repoId, filename) => {
        const key = `${repoId}/${filename || 'auto'}`;
        setDownloading(prev => ({ ...prev, [key]: true }));
        try {
            const fd = new FormData();
            fd.append('repo_id', repoId);
            if (filename) fd.append('filename', filename);
            const res = await fetch(`${API_BASE}/huggingface/download`, { method: 'POST', body: fd });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Download failed');
            setDownloaded(prev => ({ ...prev, [key]: data }));
        } catch (e) {
            setError(e.message);
        } finally {
            setDownloading(prev => ({ ...prev, [key]: false }));
        }
    };

    const formatNum = (n) => {
        if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
        return n;
    };

    return (
        <div>
            <div className="page-header">
                <h2>HuggingFace Hub</h2>
                <p>Search, browse, and download models from HuggingFace directly into your model registry</p>
            </div>

            {/* Search Bar */}
            <div className="card" style={{ marginBottom: '24px' }}>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '240px' }}>
                        <input
                            className="form-input"
                            placeholder="Search models — resnet, bert, stable-diffusion..."
                            value={query}
                            onChange={e => setQuery(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && searchModels()}
                        />
                    </div>
                    <select className="form-select" value={task} onChange={e => setTask(e.target.value)} style={{ width: '200px' }}>
                        {TASK_FILTERS.map(f => (
                            <option key={f.value} value={f.value}>{f.label}</option>
                        ))}
                    </select>
                    <button className="btn btn-primary" onClick={searchModels} disabled={searching}>
                        {searching ? <Loader2 size={16} className="spinner" /> : <Search size={16} />}
                        Search
                    </button>
                </div>
            </div>

            {error && (
                <div style={{ padding: '14px 18px', background: 'var(--accent-red-glow)', borderRadius: 'var(--radius-md)', color: 'var(--accent-red)', fontSize: '14px', marginBottom: '20px' }}>
                    {error}
                    <button onClick={() => setError(null)} style={{ float: 'right', background: 'none', border: 'none', color: 'var(--accent-red)', cursor: 'pointer' }}>×</button>
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: detail ? '1fr 1fr' : '1fr', gap: '24px' }}>
                {/* Results Grid */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {results.length === 0 && !searching && (
                        <div className="empty-state">
                            <Search size={48} />
                            <h3>Search HuggingFace</h3>
                            <p>Find models for classification, detection, generation, and more</p>
                        </div>
                    )}

                    {results.map(m => {
                        const dlKey = `${m.id}/auto`;
                        return (
                            <div key={m.id} className="card" style={{ padding: '18px', cursor: 'pointer' }} onClick={() => viewDetails(m.id)}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontWeight: 700, fontSize: '15px', marginBottom: '4px', color: 'var(--accent-blue)' }}>{m.id}</div>
                                        {m.task && <span className="badge badge-purple" style={{ marginBottom: '8px', display: 'inline-flex' }}>{m.task}</span>}
                                        <div style={{ display: 'flex', gap: '16px', fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px' }}>
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><ArrowDown size={12} /> {formatNum(m.downloads)}</span>
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Heart size={12} /> {formatNum(m.likes)}</span>
                                        </div>
                                    </div>
                                    <button
                                        className={`btn btn-sm ${downloaded[dlKey] ? 'btn-success' : 'btn-secondary'}`}
                                        onClick={e => { e.stopPropagation(); downloadModel(m.id); }}
                                        disabled={downloading[dlKey]}
                                    >
                                        {downloading[dlKey] ? <Loader2 size={14} className="spinner" /> : downloaded[dlKey] ? <Check size={14} /> : <Download size={14} />}
                                        {downloaded[dlKey] ? 'Saved' : 'Download'}
                                    </button>
                                </div>
                                {m.tags && m.tags.length > 0 && (
                                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
                                        {m.tags.slice(0, 5).map(t => (
                                            <span key={t} style={{ fontSize: '10px', padding: '2px 8px', borderRadius: 'var(--radius-pill)', background: 'var(--bg-tertiary)', color: 'var(--text-muted)' }}>{t}</span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>

                {/* Detail Panel */}
                {(detail || detailLoading) && (
                    <div className="card" style={{ position: 'sticky', top: '20px', alignSelf: 'start' }}>
                        {detailLoading ? (
                            <div className="loading-overlay"><div className="spinner"></div><p>Loading details...</p></div>
                        ) : detail && (
                            <>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                                    <h3 className="card-title">{detail.id}</h3>
                                    <button className="btn-icon" onClick={() => setDetail(null)}>×</button>
                                </div>
                                {detail.task && <div style={{ marginBottom: '12px' }}><span className="badge badge-purple">{detail.task}</span></div>}
                                <div style={{ display: 'flex', gap: '20px', fontSize: '13px', marginBottom: '16px', color: 'var(--text-secondary)' }}>
                                    <span><ArrowDown size={14} /> {formatNum(detail.downloads)} downloads</span>
                                    <span><Heart size={14} /> {formatNum(detail.likes)} likes</span>
                                </div>
                                {detail.library_name && <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '16px' }}>Library: <strong>{detail.library_name}</strong></p>}

                                {/* Files */}
                                {detail.files && detail.files.length > 0 && (
                                    <div>
                                        <h4 style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '10px' }}>Model Files</h4>
                                        <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                                            {detail.files.filter(f => f.is_model).map(f => {
                                                const key = `${detail.id}/${f.name}`;
                                                return (
                                                    <div key={f.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '13px' }}>
                                                        <span className="text-mono truncate" style={{ flex: 1, marginRight: '10px' }}>{f.name}</span>
                                                        <button
                                                            className={`btn btn-sm ${downloaded[key] ? 'btn-success' : 'btn-secondary'}`}
                                                            onClick={() => downloadModel(detail.id, f.name)}
                                                            disabled={downloading[key]}
                                                        >
                                                            {downloading[key] ? <Loader2 size={12} className="spinner" /> : downloaded[key] ? <Check size={12} /> : <Download size={12} />}
                                                        </button>
                                                    </div>
                                                );
                                            })}
                                            {detail.files.filter(f => f.is_model).length === 0 && (
                                                <p className="text-muted" style={{ fontSize: '13px' }}>No model weight files found</p>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
