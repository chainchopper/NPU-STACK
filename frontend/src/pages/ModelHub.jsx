import React, { useState, useEffect } from 'react';
import {
    Search, Download, ExternalLink, Globe, Tag, Heart, ArrowDown,
    Check, Loader2, Filter, LayoutGrid, List, Info, Image as ImageIcon,
    DownloadCloud, Layers
} from 'lucide-react';

const API_BASE = 'http://localhost:8000/api';

const TASK_FILTERS = [
    { label: 'All Tasks', value: '' },
    { label: 'Text Generation', value: 'text-generation' },
    { label: 'Image Classification', value: 'image-classification' },
    { label: 'Object Detection', value: 'object-detection' },
    { label: 'Text-to-Image', value: 'text-to-image' },
    { label: 'Image-to-Text', value: 'image-to-text' },
];

const FRAMEWORK_TAGS = [
    { label: 'ONNX', value: 'onnx' },
    { label: 'GGUF', value: 'gguf' },
    { label: 'LoRA', value: 'loRA' },
    { label: 'PyTorch', value: 'pytorch' },
    { label: 'SafeTensors', value: 'safetensors' },
    { label: 'TensorRT', value: 'tensorrt' },
];

export default function ModelHub() {
    const [source, setSource] = useState('huggingface'); // 'huggingface' | 'civitai'
    const [query, setQuery] = useState('');
    const [task, setTask] = useState('');
    const [tags, setTags] = useState('');
    const [results, setResults] = useState([]);
    const [searching, setSearching] = useState(false);
    const [downloading, setDownloading] = useState({});
    const [downloaded, setDownloaded] = useState({});
    const [snapshotDownloading, setSnapshotDownloading] = useState(false);
    const [detail, setDetail] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [error, setError] = useState(null);

    // Initial search
    useEffect(() => {
        searchModels();
    }, [source]);

    const searchModels = async () => {
        setSearching(true);
        setError(null);
        setResults([]);
        try {
            let res;
            if (source === 'huggingface') {
                const params = new URLSearchParams({ q: query, limit: '24' });
                if (task) params.set('task', task);
                if (tags) params.set('tags', tags);
                res = await fetch(`${API_BASE}/huggingface/search?${params}`);
            } else {
                const params = new URLSearchParams({ q: query, limit: '24' });
                if (tags) params.set('type', tags.split(',')[0]); // Civitai uses 'types' for major category
                res = await fetch(`${API_BASE}/civitai/search?${params}`);
            }

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Search failed');
            setResults(data.models || []);
        } catch (e) {
            setError(e.message);
        } finally {
            setSearching(false);
        }
    };

    const getDetails = async (m) => {
        setDetailLoading(true);
        setError(null);
        try {
            let res;
            if (source === 'huggingface') {
                res = await fetch(`${API_BASE}/huggingface/model/${encodeURIComponent(m.id)}`);
            } else {
                res = await fetch(`${API_BASE}/civitai/model/${m.id}`);
            }
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to fetch details');
            setDetail(data);
        } catch (e) {
            setError(e.message);
        } finally {
            setDetailLoading(false);
        }
    };

    const downloadHF = async (repoId, filename) => {
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

    const downloadHFSnapshot = async (repoId) => {
        setSnapshotDownloading(true);
        try {
            const fd = new FormData();
            fd.append('repo_id', repoId);
            const res = await fetch(`${API_BASE}/huggingface/snapshot`, { method: 'POST', body: fd });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Snapshot download failed');
            setDownloaded(prev => ({ ...prev, [repoId]: data }));
            alert(`Completed full import of ${repoId}`);
        } catch (e) {
            setError(e.message);
        } finally {
            setSnapshotDownloading(false);
        }
    };

    const downloadCivitai = async (versionId, modelName) => {
        const key = `civitai-${versionId}`;
        setDownloading(prev => ({ ...prev, [key]: true }));
        try {
            const fd = new FormData();
            fd.append('version_id', versionId);
            fd.append('model_name', modelName);
            const res = await fetch(`${API_BASE}/civitai/download`, { method: 'POST', body: fd });
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
        if (!n) return '0';
        if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
        return n.toString();
    };

    const toggleTag = (tag) => {
        setTags(prev => {
            const current = prev ? prev.split(',') : [];
            if (current.includes(tag)) {
                return current.filter(t => t !== tag).join(',');
            } else {
                return [...current, tag].join(',');
            }
        });
    };

    return (
        <div className="page-container">
            <header className="page-header" style={{ marginBottom: '32px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                    <div>
                        <h1 className="page-title">Model Hub</h1>
                        <p className="page-subtitle">Discover and import state-of-the-art models from top repositories.</p>
                    </div>

                    <div className="btn-group" style={{ background: 'var(--bg-tertiary)', padding: '4px', borderRadius: 'var(--radius-lg)' }}>
                        <button
                            className={`btn ${source === 'huggingface' ? 'btn-primary' : 'btn-ghost'}`}
                            onClick={() => setSource('huggingface')}
                        >
                            <Globe size={18} /> HuggingFace
                        </button>
                        <button
                            className={`btn ${source === 'civitai' ? 'btn-primary' : 'btn-ghost'}`}
                            onClick={() => setSource('civitai')}
                        >
                            <ImageIcon size={18} /> Civitai
                        </button>
                    </div>
                </div>
            </header>

            {/* Search & Filter Bar */}
            <div className="card" style={{ marginBottom: '24px', background: 'linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        <div style={{ flex: 1, minWidth: '240px' }}>
                            <div style={{ position: 'relative' }}>
                                <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                                <input
                                    className="form-input"
                                    style={{ paddingLeft: '40px' }}
                                    placeholder={source === 'huggingface' ? "Search HF Hub — llama, resnet, bert..." : "Search Civitai — SDXL, LoRA, Realistic..."}
                                    value={query}
                                    onChange={e => setQuery(e.target.value)}
                                    onKeyDown={e => e.key === 'Enter' && searchModels()}
                                />
                            </div>
                        </div>

                        {source === 'huggingface' && (
                            <select className="form-select" value={task} onChange={e => setTask(e.target.value)} style={{ width: '180px' }}>
                                {TASK_FILTERS.map(f => (
                                    <option key={f.value} value={f.value}>{f.label}</option>
                                ))}
                            </select>
                        )}

                        <button className="btn btn-primary" onClick={searchModels} disabled={searching} style={{ padding: '0 24px' }}>
                            {searching ? <Loader2 size={16} className="spinner" /> : <Filter size={16} />}
                            Search
                        </button>
                    </div>

                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                        <span style={{ fontSize: '13px', color: 'var(--text-muted)', marginRight: '8px' }}>
                            {source === 'huggingface' ? 'Frameworks:' : 'Categories:'}
                        </span>
                        {source === 'huggingface' ? FRAMEWORK_TAGS.map(f => (
                            <button
                                key={f.value}
                                className={`btn btn-sm ${tags.includes(f.value) ? 'btn-primary' : 'btn-secondary'}`}
                                onClick={() => toggleTag(f.value)}
                            >
                                {f.label}
                            </button>
                        )) : (
                            // For CivitAI, only show relevant types instead of "Frameworks"
                            [
                                { label: 'Checkpoint', value: 'Checkpoint' },
                                { label: 'LoRA', value: 'LORA' },
                                { label: 'Textual Inversion', value: 'TextualInversion' },
                                { label: 'Hypernetwork', value: 'Hypernetwork' },
                                { label: 'Controlnet', value: 'Controlnet' },
                                { label: 'DoRA', value: 'DoRA' }
                            ].map(f => (
                                <button
                                    key={f.value}
                                    className={`btn btn-sm ${tags.includes(f.value) ? 'btn-primary' : 'btn-secondary'}`}
                                    onClick={() => toggleTag(f.value)}
                                >
                                    {f.label}
                                </button>
                            ))
                        )}
                    </div>
                </div>
            </div>

            {error && (
                <div className="alert alert-error" style={{ marginBottom: '24px' }}>
                    <p>{error}</p>
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: (detail || detailLoading) ? '1fr 350px' : '1fr', gap: '24px', transition: 'all 0.3s ease' }}>

                {/* Results Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '20px' }}>
                    {searching ? (
                        Array(8).fill(0).map((_, i) => (
                            <div key={i} className="card skeleton" style={{ height: '180px', borderRadius: 'var(--radius-lg)' }}></div>
                        ))
                    ) : results.map(m => (
                        <div
                            key={m.id}
                            className={`card model-card ${detail?.id === m.id ? 'active' : ''}`}
                            onClick={() => getDetails(m)}
                            style={{
                                cursor: 'pointer',
                                padding: '0',
                                overflow: 'hidden',
                                border: detail?.id === m.id ? '1px solid var(--primary)' : '1px solid var(--border-subtle)',
                                boxShadow: detail?.id === m.id ? '0 0 0 2px var(--primary-alpha)' : 'none'
                            }}
                        >
                            {source === 'civitai' && m.thumbnail && (
                                <div style={{ height: '140px', overflow: 'hidden', position: 'relative' }}>
                                    <img src={m.thumbnail} alt={m.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                    <div style={{ position: 'absolute', top: '8px', right: '8px' }}>
                                        <span className="badge badge-blue">{m.type}</span>
                                    </div>
                                </div>
                            )}
                            <div style={{ padding: '16px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                                    <h3 className="card-title truncate" style={{ fontSize: '15px', marginBottom: '4px' }} title={m.name || m.id}>
                                        {m.name || m.id.split('/').pop()}
                                    </h3>
                                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{m.author || m.creator}</span>
                                </div>

                                <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', flexWrap: 'wrap' }}>
                                    {source === 'huggingface' ? (
                                        <>
                                            {m.task && <span className="badge badge-purple" style={{ fontSize: '10px' }}>{m.task}</span>}
                                            {m.private && <span className="badge badge-red" style={{ fontSize: '10px' }}>Private</span>}
                                        </>
                                    ) : (
                                        m.tags.slice(0, 2).map(t => <span key={t} className="badge badge-secondary" style={{ fontSize: '10px' }}>{t}</span>)
                                    )}
                                </div>

                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: 'var(--text-muted)' }}>
                                    <div style={{ display: 'flex', gap: '12px' }}>
                                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <ArrowDown size={12} /> {formatNum(m.downloads || m.stats?.downloadCount)}
                                        </span>
                                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <Heart size={12} /> {formatNum(m.likes || m.stats?.favoriteCount)}
                                        </span>
                                    </div>
                                    <div className="btn-icon-sm"><Info size={14} /></div>
                                </div>
                            </div>
                        </div>
                    ))}
                    {!searching && results.length === 0 && (
                        <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)' }}>
                            <Globe size={48} style={{ opacity: 0.2, marginBottom: '16px' }} />
                            <p>No models found matching your query.</p>
                        </div>
                    )}
                </div>

                {/* Detail Panel */}
                {(detail || detailLoading) && (
                    <div className="card" style={{ position: 'sticky', top: '20px', alignSelf: 'start', maxHeight: 'calc(100vh - 40px)', overflowY: 'auto', padding: '24px' }}>
                        {detailLoading ? (
                            <div style={{ textAlign: 'center', padding: '40px 0' }}>
                                <Loader2 size={32} className="spinner" style={{ margin: '0 auto 16px', color: 'var(--primary)' }} />
                                <p>Loading model details...</p>
                            </div>
                        ) : detail && (
                            <>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
                                    <div style={{ overflow: 'hidden' }}>
                                        <h3 className="card-title truncate" title={detail.id || detail.name}>{detail.name || detail.id.split('/').pop()}</h3>
                                        <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>by {detail.author || detail.creator?.username}</p>
                                    </div>
                                    <button className="btn-icon" onClick={() => setDetail(null)}>×</button>
                                </div>

                                {source === 'huggingface' ? (
                                    <>
                                        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
                                            {detail.task && <span className="badge badge-purple">{detail.task}</span>}
                                            {detail.library_name && <span className="badge badge-blue">{detail.library_name}</span>}
                                        </div>

                                        <div style={{ display: 'flex', gap: '20px', fontSize: '13px', marginBottom: '24px', color: 'var(--text-secondary)', background: 'var(--bg-tertiary)', padding: '12px', borderRadius: 'var(--radius-md)' }}>
                                            <span><ArrowDown size={14} /> {formatNum(detail.downloads)}</span>
                                            <span><Heart size={14} /> {formatNum(detail.likes)}</span>
                                            <span><Tag size={14} /> {detail.tags?.length || 0}</span>
                                        </div>

                                        <div style={{ marginBottom: '24px' }}>
                                            <button
                                                className={`btn btn-primary w-full ${downloaded[detail.id] ? 'btn-success' : ''}`}
                                                onClick={() => downloadHFSnapshot(detail.id)}
                                                disabled={snapshotDownloading || downloaded[detail.id]}
                                            >
                                                {snapshotDownloading ? <Loader2 size={16} className="spinner" /> : <DownloadCloud size={16} />}
                                                {downloaded[detail.id] ? 'Full Import Complete' : 'Import Full Repository'}
                                            </button>
                                        </div>

                                        {detail.readme && (
                                            <div style={{ marginBottom: '24px' }}>
                                                <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '10px' }}>README PREVIEW</h4>
                                                <div style={{ background: 'var(--bg-secondary)', padding: '12px', borderRadius: 'var(--radius-md)', fontSize: '11px', maxHeight: '150px', overflowY: 'auto', border: '1px solid var(--border-subtle)', whiteSpace: 'pre-wrap' }}>
                                                    {detail.readme}
                                                </div>
                                            </div>
                                        )}

                                        {detail.files && (
                                            <div>
                                                <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '10px' }}>WEIGHT FILES</h4>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                                    {detail.files.filter(f => f.is_model).map(f => {
                                                        const key = `${detail.id}/${f.name}`;
                                                        return (
                                                            <div key={f.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', fontSize: '11px' }}>
                                                                <span className="text-mono truncate" style={{ flex: 1, marginRight: '10px' }}>{f.name}</span>
                                                                <button
                                                                    className={`btn btn-sm ${downloaded[key] ? 'btn-success' : 'btn-secondary'}`}
                                                                    onClick={() => downloadHF(detail.id, f.name)}
                                                                    disabled={downloading[key]}
                                                                >
                                                                    {downloading[key] ? <Loader2 size={12} className="spinner" /> : downloaded[key] ? <Check size={12} /> : <Download size={12} />}
                                                                </button>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        )}
                                    </>
                                ) : (
                                    <>
                                        {/* Civitai Detail */}
                                        <div style={{ borderRadius: 'var(--radius-md)', overflow: 'hidden', marginBottom: '20px' }}>
                                            <img src={detail.modelVersions?.[0]?.images?.[0]?.url} alt="" style={{ width: '100%', maxHeight: '200px', objectFit: 'cover' }} />
                                        </div>

                                        <div style={{ display: 'flex', gap: '20px', fontSize: '13px', marginBottom: '24px', color: 'var(--text-secondary)', background: 'var(--bg-tertiary)', padding: '12px', borderRadius: 'var(--radius-md)' }}>
                                            <span><ArrowDown size={14} /> {formatNum(detail.stats?.downloadCount)}</span>
                                            <span><Heart size={14} /> {formatNum(detail.stats?.favoriteCount)}</span>
                                            <span><span className="badge badge-blue">{detail.type}</span></span>
                                        </div>

                                        <div>
                                            <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '10px' }}>VERSIONS</h4>
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                                {detail.modelVersions?.map(v => {
                                                    const key = `civitai-${v.id}`;
                                                    return (
                                                        <div key={v.id} style={{ padding: '12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                                                <strong style={{ fontSize: '13px' }}>{v.name}</strong>
                                                                <span className="badge badge-secondary" style={{ fontSize: '10px' }}>{v.baseModel}</span>
                                                            </div>
                                                            <button
                                                                className={`btn btn-sm w-full ${downloaded[key] ? 'btn-success' : 'btn-primary'}`}
                                                                onClick={() => downloadCivitai(v.id, `${detail.name}_${v.name}`)}
                                                                disabled={downloading[key] || downloaded[key]}
                                                            >
                                                                {downloading[key] ? <Loader2 size={12} className="spinner" /> : downloaded[key] ? <Check size={12} /> : <Download size={12} />}
                                                                {downloaded[key] ? 'Imported' : 'Download Version'}
                                                            </button>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    </>
                                )}

                                <div style={{ marginTop: '24px', padding: '16px', background: 'var(--primary-alpha)', borderRadius: 'var(--radius-md)', border: '1px solid var(--primary-subtle)' }}>
                                    <h5 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--primary)', marginBottom: '4px' }}>Storage Info</h5>
                                    <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                                        Models will be downloaded to <code>backend/data/models/</code> and registered for use in the Platform.
                                    </p>
                                </div>
                            </>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
