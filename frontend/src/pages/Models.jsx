import React, { useState, useEffect, useRef } from 'react';
import { Upload, Trash2, Download, FileText, Box, Search, ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';
import { diagnoseBackendError, listModels, uploadModel, deleteModel } from '../api/client';
import ActivityLogCard from '../components/ActivityLogCard';
import OperationNotice from '../components/OperationNotice';

export default function Models() {
    const [models, setModels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [filter, setFilter] = useState('');
    const [sortConfig, setSortConfig] = useState({ key: 'created_at', direction: 'desc' });
    const [notice, setNotice] = useState(null);
    const [activityLog, setActivityLog] = useState([]);
    const fileRef = useRef(null);

    const addLog = (line) => {
        const timestamp = new Date().toLocaleTimeString();
        setActivityLog((prev) => [...prev.slice(-49), `${timestamp} — ${line}`]);
    };

    const loadModels = () => {
        setLoading(true);
        listModels()
            .then((data) => {
                setModels(data);
                setNotice(null);
            })
            .catch((error) => {
                setModels([]);
                const message = diagnoseBackendError(error, 'Model registry');
                setNotice({ tone: 'warning', title: 'Backend attention needed', message });
                addLog(`Load failed: ${message}`);
            })
            .finally(() => setLoading(false));
    };

    useEffect(() => { loadModels(); }, []);

    const handleUpload = async (files) => {
        if (!files?.length) return;
        setUploading(true);
        setNotice(null);
        addLog(`Uploading ${files.length} model file(s)...`);
        try {
            for (const file of files) {
                await uploadModel(file);
                addLog(`Uploaded ${file.name}`);
            }
            setNotice({ tone: 'success', title: 'Upload complete', message: `${files.length} file(s) uploaded to the model registry.` });
            loadModels();
        } catch (e) {
            const message = diagnoseBackendError(e, 'Model upload');
            setNotice({ tone: 'danger', title: 'Upload failed', message, details: e.message });
            addLog(`Upload failed: ${message}`);
        }
        setUploading(false);
    };

    const handleDelete = async (id, name) => {
        if (!confirm(`Delete model "${name}"?`)) return;
        try {
            await deleteModel(id);
            setNotice({ tone: 'success', title: 'Model removed', message: `Deleted ${name} from the registry.` });
            addLog(`Deleted model ${name}`);
            loadModels();
        } catch (e) {
            const message = diagnoseBackendError(e, 'Model deletion');
            setNotice({ tone: 'danger', title: 'Delete failed', message, details: e.message });
            addLog(`Delete failed for ${name}: ${message}`);
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

    const handleSort = (key) => {
        let direction = 'asc';
        if (sortConfig.key === key && sortConfig.direction === 'asc') {
            direction = 'desc';
        }
        setSortConfig({ key, direction });
    };

    const sortedModels = React.useMemo(() => {
        let sortableItems = [...filtered];
        if (sortConfig.key !== null) {
            sortableItems.sort((a, b) => {
                let aValue = a[sortConfig.key];
                let bValue = b[sortConfig.key];

                if (sortConfig.key === 'file_size') {
                    aValue = Number(aValue) || 0;
                    bValue = Number(bValue) || 0;
                } else if (sortConfig.key === 'created_at') {
                    aValue = new Date(aValue).getTime();
                    bValue = new Date(bValue).getTime();
                } else {
                    aValue = String(aValue || '').toLowerCase();
                    bValue = String(bValue || '').toLowerCase();
                }

                if (aValue < bValue) {
                    return sortConfig.direction === 'asc' ? -1 : 1;
                }
                if (aValue > bValue) {
                    return sortConfig.direction === 'asc' ? 1 : -1;
                }
                return 0;
            });
        }
        return sortableItems;
    }, [filtered, sortConfig]);

    const SortIcon = ({ columnKey }) => {
        if (sortConfig.key !== columnKey) return <ChevronsUpDown size={14} className="text-muted" style={{ marginLeft: 4, opacity: 0.3 }} />;
        return sortConfig.direction === 'asc' ? <ChevronUp size={14} style={{ marginLeft: 4 }} /> : <ChevronDown size={14} style={{ marginLeft: 4 }} />;
    };

    return (
        <div>
            <div className="page-header">
                <h2>Model Registry</h2>
                <p>Upload, manage, and inspect your ML models</p>
            </div>

            <OperationNotice
                tone={notice?.tone || 'info'}
                title={notice?.title}
                message={notice?.message}
                details={notice?.details}
            />

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
                                <th onClick={() => handleSort('name')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                                    <div style={{ display: 'flex', alignItems: 'center' }}>Name <SortIcon columnKey="name" /></div>
                                </th>
                                <th onClick={() => handleSort('framework')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                                    <div style={{ display: 'flex', alignItems: 'center' }}>Framework <SortIcon columnKey="framework" /></div>
                                </th>
                                <th onClick={() => handleSort('format')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                                    <div style={{ display: 'flex', alignItems: 'center' }}>Format <SortIcon columnKey="format" /></div>
                                </th>
                                <th onClick={() => handleSort('file_size')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                                    <div style={{ display: 'flex', alignItems: 'center' }}>Size <SortIcon columnKey="file_size" /></div>
                                </th>
                                <th>Input Shape</th>
                                <th onClick={() => handleSort('created_at')} style={{ cursor: 'pointer', userSelect: 'none' }}>
                                    <div style={{ display: 'flex', alignItems: 'center' }}>Created <SortIcon columnKey="created_at" /></div>
                                </th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sortedModels.map((m) => (
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

            <ActivityLogCard
                title="Model Registry Activity"
                lines={activityLog}
                emptyMessage="No model actions recorded yet."
                onClear={() => setActivityLog([])}
                style={{ marginTop: 24 }}
            />
        </div>
    );
}
