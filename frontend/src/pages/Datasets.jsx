import React, { useState, useEffect, useRef } from 'react';
import { Database, Upload, FolderSearch, Trash2, File, FileImage, FileText, FileSpreadsheet, RefreshCw, HardDrive } from 'lucide-react';
import { API_BASE } from '../api/client';

const TYPE_ICONS = {
    image: FileImage,
    tabular: FileSpreadsheet,
    csv: FileSpreadsheet,
    json: FileText,
    text: FileText,
    parquet: Database,
};

export default function Datasets() {
    const [datasets, setDatasets] = useState([]);
    const [datasetsFolder, setDatasetsFolder] = useState('');
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [scanning, setScanning] = useState(false);
    const [error, setError] = useState(null);
    const fileRef = useRef(null);

    const loadDatasets = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/datasets`);
            const data = await res.json();
            setDatasets(data.datasets || []);
            setDatasetsFolder(data.datasets_folder || '');
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { loadDatasets(); }, []);

    const handleUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        setUploading(true);
        setError(null);
        try {
            const fd = new FormData();
            fd.append('file', file);
            const res = await fetch(`${API_BASE}/datasets/upload`, { method: 'POST', body: fd });
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || 'Upload failed');
            }
            await loadDatasets();
        } catch (e) {
            setError(e.message);
        } finally {
            setUploading(false);
            if (fileRef.current) fileRef.current.value = '';
        }
    };

    const scanFolder = async () => {
        setScanning(true);
        try {
            const res = await fetch(`${API_BASE}/datasets/scan`, { method: 'POST' });
            const data = await res.json();
            setDatasets(data.datasets || []);
        } catch (e) {
            setError(e.message);
        } finally {
            setScanning(false);
        }
    };

    const deleteDataset = async (name) => {
        if (!confirm(`Delete dataset "${name}"?`)) return;
        try {
            const res = await fetch(`${API_BASE}/datasets/${encodeURIComponent(name)}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Delete failed');
            await loadDatasets();
        } catch (e) {
            setError(e.message);
        }
    };

    const formatSize = (mb) => {
        if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GB';
        if (mb >= 1) return mb.toFixed(1) + ' MB';
        return (mb * 1024).toFixed(0) + ' KB';
    };

    return (
        <div>
            <div className="page-header">
                <h2>Datasets</h2>
                <p>Manage training and evaluation datasets — upload or drop files into the datasets folder</p>
            </div>

            {/* Info Banner */}
            <div className="card" style={{ marginBottom: '24px', background: 'var(--accent-blue-glow)', border: '1px solid rgba(59,130,246,0.2)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                    <HardDrive size={20} style={{ color: 'var(--accent-blue)' }} />
                    <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 600 }}>
                            Physical dataset folder: <code className="text-mono" style={{ color: 'var(--accent-blue)' }}>{datasetsFolder || 'datasets/'}</code>
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                            Drop dataset folders or files here and click "Scan" to detect them
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <button className="btn btn-secondary btn-sm" onClick={scanFolder} disabled={scanning}>
                            {scanning ? <RefreshCw size={14} className="spinner" /> : <FolderSearch size={14} />}
                            Scan Folder
                        </button>
                        <button className="btn btn-primary btn-sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
                            {uploading ? <RefreshCw size={14} className="spinner" /> : <Upload size={14} />}
                            Upload
                        </button>
                        <input ref={fileRef} type="file" accept=".zip,.csv,.tsv,.json,.jsonl,.parquet,.tar,.gz,.txt" onChange={handleUpload} style={{ display: 'none' }} />
                    </div>
                </div>
            </div>

            {error && (
                <div style={{ padding: '14px 18px', background: 'var(--accent-red-glow)', borderRadius: 'var(--radius-md)', color: 'var(--accent-red)', fontSize: '14px', marginBottom: '20px' }}>
                    {error}
                    <button onClick={() => setError(null)} style={{ float: 'right', background: 'none', border: 'none', color: 'var(--accent-red)', cursor: 'pointer' }}>×</button>
                </div>
            )}

            {loading ? (
                <div className="loading-overlay">
                    <div className="spinner"></div>
                    <p>Scanning datasets...</p>
                </div>
            ) : datasets.length === 0 ? (
                <div className="empty-state">
                    <Database size={48} />
                    <h3>No Datasets Found</h3>
                    <p>Upload a dataset or place files in the <code>datasets/</code> folder and click "Scan"</p>
                </div>
            ) : (
                <div className="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Type</th>
                                <th>Files</th>
                                <th>Size</th>
                                <th>Source</th>
                                <th>Modified</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {datasets.map((d, i) => {
                                const TypeIcon = TYPE_ICONS[d.type] || File;
                                return (
                                    <tr key={i}>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                <TypeIcon size={18} style={{ color: 'var(--accent-blue)', flexShrink: 0 }} />
                                                <span style={{ fontWeight: 600 }}>{d.name}</span>
                                            </div>
                                        </td>
                                        <td><span className="badge badge-info">{d.type}</span></td>
                                        <td className="text-mono">{d.file_count?.toLocaleString()}</td>
                                        <td className="text-mono">{formatSize(d.total_size_mb)}</td>
                                        <td>
                                            <span className={`badge ${d.source === 'local_folder' ? 'badge-success' : 'badge-warning'}`}>
                                                {d.source === 'local_folder' ? 'Local' : 'Cache'}
                                            </span>
                                        </td>
                                        <td style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                                            {d.modified ? new Date(d.modified).toLocaleDateString() : '—'}
                                        </td>
                                        <td>
                                            {d.source === 'local_folder' && (
                                                <button className="btn-icon" onClick={() => deleteDataset(d.name)} title="Delete">
                                                    <Trash2 size={16} />
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
