import React, { useState, useEffect, useRef } from 'react';
import { Upload, Trash2, Download, FileText, Box, Search } from 'lucide-react';
import { listModels, uploadModel, deleteModel } from '../api/client';

export default function Models() {
    const [models, setModels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [filter, setFilter] = useState('');
    const fileRef = useRef(null);

    const loadModels = () => {
        setLoading(true);
        listModels().then(setModels).catch(() => setModels([])).finally(() => setLoading(false));
    };

    useEffect(() => { loadModels(); }, []);

    const handleUpload = async (files) => {
        if (!files?.length) return;
        setUploading(true);
        try {
            for (const file of files) {
                await uploadModel(file);
            }
            loadModels();
        } catch (e) {
            alert('Upload failed: ' + e.message);
        }
        setUploading(false);
    };

    const handleDelete = async (id, name) => {
        if (!confirm(`Delete model "${name}"?`)) return;
        try {
            await deleteModel(id);
            loadModels();
        } catch (e) {
            alert('Delete failed: ' + e.message);
        }
    };

    const formatSize = (bytes) => {
        if (!bytes) return 'N/A';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    };

    const filtered = models.filter(m =>
        m.name.toLowerCase().includes(filter.toLowerCase()) ||
        m.framework.toLowerCase().includes(filter.toLowerCase())
    );

    return (
        <div>
            <div className="page-header">
                <h2>Model Registry</h2>
                <p>Upload, manage, and inspect your ML models</p>
            </div>

            {/* Upload Zone */}
            <div
                className={`file-upload-zone ${dragOver ? 'drag-over' : ''}`}
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(false);
                    handleUpload(e.dataTransfer.files);
                }}
                style={{ marginBottom: '24px' }}
            >
                <Upload size={40} />
                {uploading ? (
                    <p>Uploading...</p>
                ) : (
                    <>
                        <p><span className="highlight">Click to upload</span> or drag and drop</p>
                        <p className="text-muted" style={{ fontSize: '12px', marginTop: '4px' }}>
                            Supports: .onnx, .pt, .pth, .xml, .tflite, .pb
                        </p>
                    </>
                )}
                <input
                    ref={fileRef}
                    type="file"
                    multiple
                    accept=".onnx,.pt,.pth,.xml,.bin,.tflite,.pb"
                    style={{ display: 'none' }}
                    onChange={(e) => handleUpload(e.target.files)}
                />
            </div>

            {/* Search / Filter */}
            <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', alignItems: 'center' }}>
                <div style={{ position: 'relative', flex: 1, maxWidth: '400px' }}>
                    <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                    <input
                        type="text"
                        className="form-input"
                        placeholder="Search models..."
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                        style={{ paddingLeft: '36px' }}
                    />
                </div>
                <span className="text-secondary" style={{ fontSize: '14px' }}>
                    {filtered.length} model{filtered.length !== 1 ? 's' : ''}
                </span>
            </div>

            {/* Models Table */}
            {loading ? (
                <div className="loading-overlay"><div className="spinner" /><span>Loading models...</span></div>
            ) : filtered.length === 0 ? (
                <div className="empty-state">
                    <Box size={48} />
                    <h3>No models yet</h3>
                    <p>Upload your first model to get started</p>
                </div>
            ) : (
                <div className="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>Framework</th>
                                <th>Format</th>
                                <th>Size</th>
                                <th>Input Shape</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((m) => (
                                <tr key={m.id}>
                                    <td className="text-mono text-muted">{m.id}</td>
                                    <td style={{ fontWeight: 500 }}>{m.name}</td>
                                    <td>
                                        <span className={`badge ${m.framework === 'onnx' ? 'badge-info' :
                                                m.framework === 'pytorch' ? 'badge-purple' :
                                                    m.framework === 'openvino' ? 'badge-success' : 'badge-warning'
                                            }`}>
                                            {m.framework}
                                        </span>
                                    </td>
                                    <td className="text-mono">{m.format}</td>
                                    <td className="text-mono">{formatSize(m.file_size)}</td>
                                    <td className="text-mono text-secondary">{m.input_shape || '—'}</td>
                                    <td className="text-secondary">{new Date(m.created_at).toLocaleDateString()}</td>
                                    <td>
                                        <div style={{ display: 'flex', gap: '8px' }}>
                                            <a href={`/api/models/${m.id}/download`} className="btn btn-secondary btn-sm" title="Download">
                                                <Download size={14} />
                                            </a>
                                            <button className="btn btn-danger btn-sm" onClick={() => handleDelete(m.id, m.name)} title="Delete">
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
