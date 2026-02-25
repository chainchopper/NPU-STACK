import React, { useState, useEffect, useRef } from 'react';
import { Upload, FolderOpen, FileText, Database, Trash2, Eye, Play, Settings, ChevronDown, X, Check } from 'lucide-react';
import FolderBrowser from '../components/FolderBrowser';

const API = 'http://localhost:8000';

export default function DataIngestion() {
    const [uploads, setUploads] = useState([]);
    const [extractionResults, setExtractionResults] = useState([]);
    const [formats, setFormats] = useState([]);
    const [supportedTypes, setSupportedTypes] = useState([]);
    const [loading, setLoading] = useState(false);
    const [building, setBuilding] = useState(false);
    const [browseOpen, setBrowseOpen] = useState(false);
    const [buildResult, setBuildResult] = useState(null);
    const [previewData, setPreviewData] = useState(null);
    const [dragOver, setDragOver] = useState(false);
    const fileInputRef = useRef(null);

    // Config
    const [config, setConfig] = useState({
        output_format: 'raw_text',
        dataset_name: 'my_dataset',
        chunk_size: 512,
        chunk_overlap: 64,
        deduplicate: true,
        min_length: 10,
        output_type: 'jsonl',
        ocr: false,
    });

    useEffect(() => {
        fetch(`${API}/api/ingest/dataset-formats`).then(r => r.json()).then(d => setFormats(d.formats || [])).catch(() => { });
        fetch(`${API}/api/ingest/supported-types`).then(r => r.json()).then(d => setSupportedTypes(d.types || [])).catch(() => { });
        refreshUploads();
    }, []);

    const refreshUploads = () => {
        fetch(`${API}/api/ingest/uploads`).then(r => r.json()).then(d => setUploads(d.files || [])).catch(() => { });
    };

    const handleFileDrop = async (e) => {
        e.preventDefault();
        setDragOver(false);
        const files = e.dataTransfer?.files || e.target?.files;
        if (!files?.length) return;
        await uploadFiles(files);
    };

    const uploadFiles = async (files) => {
        setLoading(true);
        const formData = new FormData();
        for (const f of files) formData.append('files', f);
        formData.append('ocr', config.ocr);

        try {
            const res = await fetch(`${API}/api/ingest/upload`, { method: 'POST', body: formData });
            const data = await res.json();
            setExtractionResults(prev => [...prev, ...(data.files || [])]);
            refreshUploads();
        } catch {
            alert('Upload failed');
        }
        setLoading(false);
    };

    const extractFolder = async (path) => {
        setLoading(true);
        const formData = new FormData();
        formData.append('path', path);
        formData.append('recursive', 'true');
        formData.append('ocr', config.ocr);
        try {
            const res = await fetch(`${API}/api/ingest/extract-folder`, { method: 'POST', body: formData });
            const data = await res.json();
            setExtractionResults(prev => [...prev, ...(data.files || [])]);
        } catch {
            alert('Folder extraction failed');
        }
        setLoading(false);
    };

    const buildDataset = async () => {
        setBuilding(true);
        setBuildResult(null);
        const formData = new FormData();
        const filePaths = extractionResults.filter(r => r.success).map(r => r.metadata?.file_path || r.uploaded_path).filter(Boolean);
        formData.append('uploaded_files', JSON.stringify(filePaths));
        formData.append('output_format', config.output_format);
        formData.append('dataset_name', config.dataset_name);
        formData.append('chunk_size', config.chunk_size);
        formData.append('chunk_overlap', config.chunk_overlap);
        formData.append('deduplicate', config.deduplicate);
        formData.append('min_length', config.min_length);
        formData.append('output_type', config.output_type);
        formData.append('ocr', config.ocr);

        try {
            const res = await fetch(`${API}/api/ingest/build-dataset`, { method: 'POST', body: formData });
            const data = await res.json();
            setBuildResult(data);
        } catch {
            setBuildResult({ success: false, error: 'Build request failed' });
        }
        setBuilding(false);
    };

    const clearUploads = async () => {
        await fetch(`${API}/api/ingest/uploads/clear`, { method: 'DELETE' });
        setUploads([]);
        setExtractionResults([]);
        setBuildResult(null);
    };

    const successCount = extractionResults.filter(r => r.success).length;

    return (
        <div style={{ padding: 32, maxWidth: 1200, margin: '0 auto' }}>
            <h1 style={{ fontSize: 28, margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
                <Database size={28} /> Data Ingestion
            </h1>
            <p style={{ color: '#888', marginTop: 6 }}>
                Extract data from documents, images, and audio → build training datasets for fine-tuning.
            </p>

            {/* Supported Types */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '12px 0' }}>
                {supportedTypes.map((t, i) => (
                    <span key={i} style={{
                        padding: '3px 10px', background: '#1a1a2e', border: '1px solid #333',
                        borderRadius: 12, fontSize: 11, color: '#888',
                    }}>
                        {t.category}: {t.extensions.join(', ')}
                    </span>
                ))}
            </div>

            {/* Upload Zone */}
            <div
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleFileDrop}
                onClick={() => fileInputRef.current?.click()}
                style={{
                    border: `2px dashed ${dragOver ? '#6c63ff' : '#333'}`,
                    borderRadius: 12, padding: 40, textAlign: 'center', cursor: 'pointer',
                    background: dragOver ? '#6c63ff11' : '#0d0d1a', transition: 'all 0.2s',
                    marginTop: 16,
                }}
            >
                <Upload size={36} color="#6c63ff" style={{ marginBottom: 10 }} />
                <p style={{ margin: 0, fontSize: 16 }}>
                    {loading ? 'Uploading & extracting...' : 'Drop files here or click to upload'}
                </p>
                <p style={{ margin: '6px 0 0', color: '#666', fontSize: 13 }}>
                    PDF, DOCX, PPTX, JSON, CSV, images, audio, and more
                </p>
                <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    onChange={e => uploadFiles(e.target.files)}
                    style={{ display: 'none' }}
                />
            </div>

            {/* Folder Browse */}
            <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
                <button onClick={() => setBrowseOpen(true)} style={btnSecondary}>
                    <FolderOpen size={16} /> Browse Folder
                </button>
                {extractionResults.length > 0 && (
                    <button onClick={clearUploads} style={{ ...btnSecondary, color: '#ff6b6b', borderColor: '#ff6b6b33' }}>
                        <Trash2 size={14} /> Clear All
                    </button>
                )}
            </div>

            <FolderBrowser
                open={browseOpen}
                onClose={() => setBrowseOpen(false)}
                onSelect={(path) => extractFolder(path)}
                title="Select Data Folder"
            />

            {/* Extraction Results */}
            {extractionResults.length > 0 && (
                <div style={{ marginTop: 24 }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <FileText size={18} />
                        Extracted: {successCount} of {extractionResults.length} files
                    </h3>
                    <div style={{ maxHeight: 300, overflowY: 'auto', border: '1px solid #222', borderRadius: 8 }}>
                        {extractionResults.map((r, i) => (
                            <div key={i} style={{
                                padding: '10px 14px', borderBottom: '1px solid #1a1a2e',
                                display: 'flex', alignItems: 'center', gap: 10,
                                background: r.success ? 'transparent' : '#ff6b6b08',
                            }}>
                                <span style={{ color: r.success ? '#4ecdc4' : '#ff6b6b', fontSize: 14 }}>
                                    {r.success ? '✓' : '✗'}
                                </span>
                                <span style={{ flex: 1, fontSize: 13 }}>
                                    {r.metadata?.file_name || 'Unknown'}
                                </span>
                                <span style={{
                                    padding: '1px 8px', background: '#6c63ff22', color: '#6c63ff',
                                    borderRadius: 4, fontSize: 10, fontWeight: 600,
                                }}>
                                    {r.file_type}
                                </span>
                                <span style={{ color: '#666', fontSize: 11 }}>
                                    {r.metadata?.char_count ? `${(r.metadata.char_count / 1000).toFixed(1)}k chars` : ''}
                                </span>
                                {r.success && r.text && (
                                    <button
                                        onClick={() => setPreviewData(r)}
                                        style={{ background: 'none', border: 'none', color: '#6c63ff', cursor: 'pointer', padding: 2 }}
                                    >
                                        <Eye size={14} />
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Preview Modal */}
            {previewData && (
                <div style={overlayStyle} onClick={() => setPreviewData(null)}>
                    <div style={modalStyle} onClick={e => e.stopPropagation()}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                            <h3 style={{ margin: 0 }}>📄 {previewData.metadata?.file_name}</h3>
                            <button onClick={() => setPreviewData(null)} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer' }}>
                                <X size={18} />
                            </button>
                        </div>
                        <pre style={{
                            background: '#0a0a15', padding: 16, borderRadius: 8, maxHeight: 400,
                            overflow: 'auto', fontSize: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap',
                        }}>
                            {previewData.text?.slice(0, 5000) || 'No text content'}
                        </pre>
                    </div>
                </div>
            )}

            {/* Dataset Builder Config */}
            {successCount > 0 && (
                <div style={{ marginTop: 24, background: '#0d0d1a', border: '1px solid #222', borderRadius: 12, padding: 20 }}>
                    <h3 style={{ margin: '0 0 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Settings size={18} /> Dataset Builder
                    </h3>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
                        <label style={labelStyle}>
                            Dataset Name
                            <input value={config.dataset_name} onChange={e => setConfig({ ...config, dataset_name: e.target.value })} style={inputStyle} />
                        </label>

                        <label style={labelStyle}>
                            Output Format
                            <select value={config.output_format} onChange={e => setConfig({ ...config, output_format: e.target.value })} style={inputStyle}>
                                {formats.map(f => <option key={f.id} value={f.id}>{f.description}</option>)}
                            </select>
                        </label>

                        <label style={labelStyle}>
                            File Type
                            <select value={config.output_type} onChange={e => setConfig({ ...config, output_type: e.target.value })} style={inputStyle}>
                                <option value="jsonl">JSONL</option>
                                <option value="csv">CSV</option>
                                <option value="parquet">Parquet</option>
                            </select>
                        </label>

                        <label style={labelStyle}>
                            Chunk Size
                            <input type="number" value={config.chunk_size} onChange={e => setConfig({ ...config, chunk_size: parseInt(e.target.value) })} style={inputStyle} />
                        </label>

                        <label style={labelStyle}>
                            Overlap
                            <input type="number" value={config.chunk_overlap} onChange={e => setConfig({ ...config, chunk_overlap: parseInt(e.target.value) })} style={inputStyle} />
                        </label>

                        <label style={labelStyle}>
                            Min Length
                            <input type="number" value={config.min_length} onChange={e => setConfig({ ...config, min_length: parseInt(e.target.value) })} style={inputStyle} />
                        </label>
                    </div>

                    <div style={{ display: 'flex', gap: 16, marginTop: 14, alignItems: 'center' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13 }}>
                            <input type="checkbox" checked={config.deduplicate} onChange={e => setConfig({ ...config, deduplicate: e.target.checked })} />
                            Deduplicate
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13 }}>
                            <input type="checkbox" checked={config.ocr} onChange={e => setConfig({ ...config, ocr: e.target.checked })} />
                            OCR (images)
                        </label>
                    </div>

                    <button onClick={buildDataset} disabled={building} style={{ ...btnPrimary, marginTop: 16 }}>
                        {building ? 'Building...' : <><Play size={16} /> Build Dataset ({successCount} files)</>}
                    </button>
                </div>
            )}

            {/* Build Result */}
            {buildResult && (
                <div style={{
                    marginTop: 20, padding: 20, borderRadius: 12,
                    background: buildResult.success ? '#4ecdc411' : '#ff6b6b11',
                    border: `1px solid ${buildResult.success ? '#4ecdc433' : '#ff6b6b33'}`,
                }}>
                    {buildResult.success ? (
                        <>
                            <h3 style={{ margin: '0 0 10px', color: '#4ecdc4' }}>
                                <Check size={18} /> Dataset Built Successfully
                            </h3>
                            <div style={{ fontSize: 13, lineHeight: 2 }}>
                                <div><strong>Records:</strong> {buildResult.record_count}</div>
                                <div><strong>Size:</strong> {buildResult.file_size_human}</div>
                                <div><strong>Format:</strong> {buildResult.output_format} ({buildResult.output_type})</div>
                                <div><strong>Path:</strong> <code style={{ color: '#6c63ff' }}>{buildResult.output_path}</code></div>
                                {buildResult.stats && (
                                    <div><strong>Avg Record:</strong> {buildResult.stats.avg_record_length} chars</div>
                                )}
                            </div>
                            {buildResult.sample && (
                                <details style={{ marginTop: 12 }}>
                                    <summary style={{ cursor: 'pointer', color: '#6c63ff', fontSize: 13 }}>Sample Records</summary>
                                    <pre style={{
                                        background: '#0a0a15', padding: 12, borderRadius: 6, marginTop: 8,
                                        fontSize: 11, maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap',
                                    }}>
                                        {JSON.stringify(buildResult.sample, null, 2)}
                                    </pre>
                                </details>
                            )}
                        </>
                    ) : (
                        <p style={{ color: '#ff6b6b', margin: 0 }}>❌ {buildResult.error}</p>
                    )}
                </div>
            )}
        </div>
    );
}

const btnPrimary = {
    padding: '10px 20px', background: '#6c63ff', color: '#fff', border: 'none',
    borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
    fontSize: 14, fontWeight: 500,
};
const btnSecondary = {
    padding: '8px 14px', background: '#1a1a2e', color: '#ccc', border: '1px solid #333',
    borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13,
};
const labelStyle = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#888' };
const inputStyle = {
    padding: '8px 10px', background: '#16162a', border: '1px solid #333', borderRadius: 6,
    color: '#ddd', fontSize: 13, outline: 'none',
};
const overlayStyle = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9999,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
};
const modalStyle = {
    background: '#16162a', border: '1px solid #333', borderRadius: 12,
    width: '90%', maxWidth: 700, padding: 24, maxHeight: '80vh', overflow: 'auto',
    boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
};
