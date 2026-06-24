import React, { useState, useEffect, useRef } from 'react';
import { Database, Upload, FolderSearch, Trash2, File, FileImage, FileText, FileSpreadsheet, RefreshCw, HardDrive, DownloadCloud, Search, Package, ArrowRight, CheckCircle, ExternalLink, Layers, FileJson, BookOpen } from 'lucide-react';
import { API_BASE } from '../api/client';

const TYPE_ICONS = {
    image: FileImage, tabular: FileSpreadsheet, csv: FileSpreadsheet,
    json: FileJson, jsonl: FileJson, text: FileText, parquet: Database,
};

const TABS = [
    { id: 'local', label: 'Local', icon: HardDrive },
    { id: 'catalog', label: 'Catalog', icon: Package },
    { id: 'search', label: 'HF Search', icon: Search },
];

export default function Datasets() {
    const [datasets, setDatasets] = useState([]);
    const [catalog, setCatalog] = useState([]);
    const [datasetsFolder, setDatasetsFolder] = useState('');
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [scanning, setScanning] = useState(false);
    const [hqRepoId, setHqRepoId] = useState('');
    const [hfDownloading, setHfDownloading] = useState(false);
    const [hfSearchQuery, setHfSearchQuery] = useState('');
    const [hfResults, setHfResults] = useState([]);
    const [hfSearching, setHfSearching] = useState(false);
    const [activeTab, setActiveTab] = useState('local');
    const [importMsg, setImportMsg] = useState(null);
    const [error, setError] = useState(null);
    const fileRef = useRef(null);

    const loadDatasets = async () => {
        setLoading(true);
        try { const r = await fetch(`${API_BASE}/datasets`); const d = await r.json(); setDatasets(d.datasets || []); setDatasetsFolder(d.datasets_folder || ''); }
        catch (e) { setError(e.message); } finally { setLoading(false); }
    };

    const loadCatalog = async () => {
        try { const r = await fetch(`${API_BASE}/datasets/catalog`); const d = await r.json(); setCatalog(d.catalog || []); setDatasetsFolder(d.datasets_folder || ''); }
        catch {}
    };

    useEffect(() => { loadDatasets(); loadCatalog(); }, []);

    const handleUpload = async (e) => {
        const file = e.target.files[0]; if (!file) return;
        setUploading(true); setError(null);
        try {
            const fd = new FormData(); fd.append('file', file);
            const r = await fetch(`${API_BASE}/datasets/upload`, { method: 'POST', body: fd });
            if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Upload failed'); }
            await loadDatasets();
        } catch (e) { setError(e.message); } finally { setUploading(false); if (fileRef.current) fileRef.current.value = ''; }
    };

    const scanFolder = async () => { setScanning(true); try { const r = await fetch(`${API_BASE}/datasets/scan`, { method: 'POST' }); const d = await r.json(); setDatasets(d.datasets || []); } catch (e) { setError(e.message); } finally { setScanning(false); } };

    const handleHfDownload = async (repoId) => {
        const rid = repoId || hfRepoId; if (!rid?.trim()) return;
        setHfDownloading(true); setError(null); setImportMsg(null);
        try {
            const fd = new FormData(); fd.append('repo_id', rid.trim());
            const r = await fetch(`${API_BASE}/datasets/huggingface/download`, { method: 'POST', body: fd });
            if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Download failed'); }
            const d = await r.json();
            setImportMsg({ type: 'success', text: d.message });
            setHfRepoId(''); await loadDatasets(); await loadCatalog();
        } catch (e) { setError(e.message); } finally { setHfDownloading(false); }
    };

    const handleHfSearch = async () => {
        if (!hfSearchQuery.trim()) return; setHfSearching(true);
        try { const r = await fetch(`${API_BASE}/datasets/search/huggingface?q=${encodeURIComponent(hfSearchQuery)}&limit=15`); const d = await r.json(); setHfResults(d.results || []); }
        catch (e) { setError(e.message); } finally { setHfSearching(false); }
    };

    const deleteDataset = async (name) => { if (!confirm(`Delete "${name}"?`)) return; try { await fetch(`${API_BASE}/datasets/${encodeURIComponent(name)}`, { method: 'DELETE' }); await loadDatasets(); await loadCatalog(); } catch (e) { setError(e.message); } };

    const formatSize = (mb) => { if (mb >= 1024) return (mb/1024).toFixed(1)+' GB'; if (mb >= 1) return mb.toFixed(1)+' MB'; return (mb*1024).toFixed(0)+' KB'; };
    const formatNum = (n) => n?.toLocaleString?.() ?? n ?? '—';

    return (
        <div>
            <div className="page-header"><h2>Datasets</h2><p>Browse, search, import, and manage training datasets — local files, HuggingFace catalog, or sample collections</p></div>

            {/* Folder banner */}
            <div className="card" style={{ marginBottom: 20, background: 'var(--accent-blue-glow)', border: '1px solid rgba(59,130,246,0.2)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                    <HardDrive size={20} style={{ color: 'var(--accent-blue)' }} />
                    <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>Dataset folder: <code style={{ color: 'var(--accent-blue)' }}>{datasetsFolder || 'datasets/'}</code></div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>Drop files here, scan to detect, or import from the Catalog / HuggingFace</div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-secondary btn-sm" onClick={scanFolder} disabled={scanning}>{scanning ? <RefreshCw size={14} /> : <FolderSearch size={14} />} Scan</button>
                        <button className="btn btn-primary btn-sm" onClick={() => fileRef.current?.click()} disabled={uploading}>{uploading ? <RefreshCw size={14} /> : <Upload size={14} />} Upload</button>
                        <input ref={fileRef} type="file" accept=".zip,.csv,.tsv,.json,.jsonl,.parquet,.tar,.gz,.txt" onChange={handleUpload} style={{ display: 'none' }} />
                    </div>
                </div>
            </div>

            {error && <div style={{ padding: '14px 18px', background: 'var(--accent-red-glow)', borderRadius: 8, color: 'var(--accent-red)', fontSize: 14, marginBottom: 20 }}>{error}<button onClick={() => setError(null)} style={{ float: 'right', background: 'none', border: 'none', color: 'var(--accent-red)', cursor: 'pointer' }}>×</button></div>}
            {importMsg && <div style={{ padding: '12px 18px', background: importMsg.type==='success' ? 'rgba(74,222,128,0.1)' : 'var(--accent-red-glow)', borderRadius: 8, color: importMsg.type==='success' ? '#4ade80' : 'var(--accent-red)', fontSize: 14, marginBottom: 20 }}>{importMsg.text}<button onClick={() => setImportMsg(null)} style={{ float: 'right', background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>×</button></div>}

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid var(--border-color)', paddingBottom: 12 }}>
                {TABS.map(t => (
                    <button key={t.id} onClick={() => setActiveTab(t.id)}
                        style={{ padding: '8px 16px', borderRadius: 8, border: activeTab===t.id ? '1px solid var(--accent-blue)' : '1px solid transparent', background: activeTab===t.id ? 'var(--accent-blue-glow)' : 'transparent', color: activeTab===t.id ? 'var(--accent-blue)' : 'var(--text-muted)', fontSize: 13, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
                        <t.icon size={14} />{t.label}
                    </button>
                ))}
            </div>

            {/* ── LOCAL TAB ── */}
            {activeTab === 'local' && (
                loading ? <div className="loading-overlay"><div className="spinner" /><p>Scanning datasets...</p></div> :
                datasets.length === 0 ? <div className="empty-state"><Database size={48} /><h3>No Datasets Found</h3><p>Upload a file, import from catalog, or place files in <code>datasets/</code> and Scan</p></div> :
                <div className="table-container"><table><thead><tr><th>Name</th><th>Type</th><th>Entries</th><th>Size</th><th>Source</th><th>Modified</th><th></th></tr></thead><tbody>
                    {datasets.map((d, i) => { const TypeIcon = TYPE_ICONS[d.type] || File;
                        return <tr key={i}>
                            <td><div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><TypeIcon size={18} style={{ color: 'var(--accent-blue)', flexShrink: 0 }} /><span style={{ fontWeight: 600 }}>{d.name}</span></div></td>
                            <td><span className="badge badge-info">{d.type}</span></td>
                            <td className="text-mono">{formatNum(d.entries || d.file_count)}</td>
                            <td className="text-mono">{formatSize(d.total_size_mb)}</td>
                            <td><span className={`badge ${d.source==='local_folder' ? 'badge-success' : 'badge-warning'}`}>{d.source==='local_folder' ? 'Local' : 'Cache'}</span></td>
                            <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{d.modified ? new Date(d.modified).toLocaleDateString() : '—'}</td>
                            <td>{d.source==='local_folder' && <button className="btn-icon" onClick={() => deleteDataset(d.name)} title="Delete"><Trash2 size={16} /></button>}</td>
                        </tr>;
                    })}</tbody></table></div>
            )}

            {/* ── CATALOG TAB ── */}
            {activeTab === 'catalog' && (
                <div>
                    <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>Curated datasets ready for training — one click import from HuggingFace or use local files</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
                        {catalog.map(ds => (
                            <div key={ds.id} style={{ padding: 16, borderRadius: 12, background: 'var(--bg-card)', border: ds.available_local ? '1px solid rgba(74,222,128,0.3)' : '1px solid var(--border-color)', position: 'relative' }}>
                                {ds.available_local && <div style={{ position: 'absolute', top: 10, right: 14, background: '#1a3a2a', color: '#4ade80', fontSize: 11, padding: '2px 8px', borderRadius: 12, display: 'flex', alignItems: 'center', gap: 4 }}><CheckCircle size={12} /> Available</div>}
                                <div style={{ fontSize: 24, marginBottom: 8 }}>{ds.icon}</div>
                                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{ds.name}</div>
                                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8, lineHeight: 1.5 }}>{ds.description}</div>
                                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                                    <span className="badge badge-info">{ds.type}</span>
                                    <span className="badge">{ds.size}</span>
                                    <span className="badge">{formatNum(ds.entries)} entries</span>
                                    {ds.tags?.map(t => <span key={t} className="badge badge-secondary" style={{ fontSize: 10 }}>{t}</span>)}
                                </div>
                                {ds.source === 'huggingface' ? (
                                    <button className="btn btn-primary btn-sm" onClick={() => handleHfDownload(ds.hf_repo)} disabled={hfDownloading} style={{ width: '100%' }}>
                                        {hfDownloading ? <RefreshCw size={14} /> : <DownloadCloud size={14} />} Import from HF
                                    </button>
                                ) : (
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <CheckCircle size={14} color="#4ade80" /> Already at <code>{ds.path}</code>
                                    </div>
                                )}
                            </div>
                        ))}</div>
                </div>
            )}

            {/* ── HF SEARCH TAB ── */}
            {activeTab === 'search' && (
                <div>
                    <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
                        <input type="text" className="form-input" placeholder="Search HuggingFace datasets (e.g. 'alpaca', 'code', 'math')" value={hfSearchQuery}
                            onChange={e => setHfSearchQuery(e.target.value)} onKeyDown={e => e.key==='Enter' && handleHfSearch()}
                            style={{ flex: 1, padding: '10px 14px', borderRadius: 8, background: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 13 }} />
                        <button className="btn btn-primary" onClick={handleHfSearch} disabled={hfSearching}>{hfSearching ? <RefreshCw size={14} /> : <Search size={14} />} Search</button>
                    </div>

                    <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center' }}>
                        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Or paste a repo ID:</span>
                        <input type="text" className="form-input" placeholder="org/dataset-name" value={hqRepoId}
                            onChange={e => setHqRepoId(e.target.value)} onKeyDown={e => e.key==='Enter' && handleHfDownload()}
                            disabled={hfDownloading}
                            style={{ flex: 1, padding: '8px 14px', borderRadius: 8, background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 13 }} />
                        <button className="btn btn-primary btn-sm" onClick={() => handleHfDownload()} disabled={!hqRepoId.trim() || hfDownloading}>
                            {hfDownloading ? <RefreshCw size={14} /> : <DownloadCloud size={14} />} Import
                        </button>
                    </div>

                    {hfSearching ? <div className="loading-overlay"><div className="spinner" /></div> :
                     hfResults.length === 0 ? <div className="empty-state"><Search size={48} /><h3>Search HuggingFace</h3><p>Type a keyword and search for datasets</p></div> :
                     <div><div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>{hfResults.length} results for "{hfSearchQuery}"</div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 12 }}>
                            {hfResults.map(ds => (
                                <div key={ds.id} style={{ padding: 14, borderRadius: 10, background: 'var(--bg-card)', border: '1px solid var(--border-color)' }}>
                                    <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4, wordBreak: 'break-all' }}>{ds.id}</div>
                                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>{ds.author} · ⬇ {formatNum(ds.downloads)} · ❤ {formatNum(ds.likes)}</div>
                                    {ds.tags?.length > 0 && <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 10 }}>{ds.tags.slice(0,6).map(t => <span key={t} className="badge badge-secondary" style={{ fontSize: 10 }}>{t}</span>)}</div>}
                                    <div style={{ display: 'flex', gap: 8 }}>
                                        <button className="btn btn-primary btn-sm" onClick={() => handleHfDownload(ds.id)} disabled={hfDownloading} style={{ flex: 1 }}>{hfDownloading ? <RefreshCw size={12} /> : <DownloadCloud size={12} />} Import</button>
                                    </div>
                                </div>
                            ))}</div>
                     </div>}
                </div>
            )}
        </div>
    );
}
