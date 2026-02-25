import React, { useState, useEffect, useCallback } from 'react';
import { FolderSearch, Download, HardDrive, Filter, RefreshCw } from 'lucide-react';

const API = 'http://localhost:8000';

export default function Scanner() {
    const [directory, setDirectory] = useState('');
    const [recursive, setRecursive] = useState(true);
    const [results, setResults] = useState(null);
    const [hints, setHints] = useState([]);
    const [loading, setLoading] = useState(false);
    const [importing, setImporting] = useState(null);
    const [importResult, setImportResult] = useState(null);
    const [filterFormat, setFilterFormat] = useState('all');

    useEffect(() => {
        fetch(`${API}/api/scan/hints`)
            .then(r => r.json())
            .then(data => setHints(data.hints || []))
            .catch(() => { });
    }, []);

    const scanDirectory = async () => {
        if (!directory.trim()) return;
        setLoading(true);
        setResults(null);
        setImportResult(null);
        try {
            const res = await fetch(`${API}/api/scan?directory=${encodeURIComponent(directory)}&recursive=${recursive}`);
            const data = await res.json();
            if (res.ok) setResults(data);
            else alert(data.detail || 'Scan failed');
        } catch (e) {
            alert('Failed to connect to backend');
        }
        setLoading(false);
    };

    const importModel = async (model) => {
        setImporting(model.path);
        try {
            const res = await fetch(`${API}/api/scan/import`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: model.path, copy_file: false }),
            });
            const data = await res.json();
            setImportResult({ path: model.path, ...data });
        } catch (e) {
            setImportResult({ path: model.path, status: 'error', message: String(e) });
        }
        setImporting(null);
    };

    const filteredModels = results?.models?.filter(m =>
        filterFormat === 'all' || m.format === filterFormat
    ) || [];

    const formatCounts = results?.by_format || {};
    const allFormats = Object.keys(formatCounts);

    return (
        <div style={{ padding: 32 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
                <FolderSearch size={28} />
                <h1 style={{ margin: 0, fontSize: 24 }}>Model Scanner</h1>
            </div>
            <p style={{ color: '#999', marginBottom: 24, maxWidth: 600 }}>
                Discover model files on your PC — GGUF, SafeTensors, ONNX, PyTorch, OpenVINO, TensorRT, and more.
                Import them into NPU-STACK's registry with one click.
            </p>

            {/* Scan Input */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
                <input
                    type="text"
                    value={directory}
                    onChange={e => setDirectory(e.target.value)}
                    placeholder="Enter directory path to scan (e.g. C:\ComfyUI\models)"
                    style={{
                        flex: 1, minWidth: 300, padding: '10px 14px',
                        background: '#1a1a2e', border: '1px solid #333', borderRadius: 8,
                        color: '#fff', fontSize: 14,
                    }}
                    onKeyDown={e => e.key === 'Enter' && scanDirectory()}
                />
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#aaa', fontSize: 13 }}>
                    <input type="checkbox" checked={recursive} onChange={e => setRecursive(e.target.checked)} />
                    Recursive
                </label>
                <button
                    onClick={scanDirectory}
                    disabled={loading || !directory.trim()}
                    style={{
                        padding: '10px 20px', background: '#6c63ff', color: '#fff', border: 'none',
                        borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
                        opacity: loading ? 0.6 : 1,
                    }}
                >
                    {loading ? <RefreshCw size={16} className="spin" /> : <FolderSearch size={16} />}
                    {loading ? 'Scanning...' : 'Scan'}
                </button>
            </div>

            {/* Quick Scan Hints */}
            {hints.length > 0 && (
                <div style={{ marginBottom: 24 }}>
                    <p style={{ color: '#888', fontSize: 13, marginBottom: 8 }}>Quick scan:</p>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {hints.filter(h => h.exists).map((hint, i) => (
                            <button
                                key={i}
                                onClick={() => { setDirectory(hint.path); }}
                                style={{
                                    padding: '6px 12px', background: '#1a1a2e', border: '1px solid #333',
                                    borderRadius: 6, color: '#6c63ff', cursor: 'pointer', fontSize: 12,
                                }}
                            >
                                <HardDrive size={12} style={{ marginRight: 4 }} />
                                {hint.source}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Results */}
            {results && (
                <>
                    <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        marginBottom: 16, flexWrap: 'wrap', gap: 8,
                    }}>
                        <p style={{ color: '#ccc', margin: 0 }}>
                            Found <strong style={{ color: '#6c63ff' }}>{results.total_files}</strong> model files
                        </p>
                        {/* Format filter */}
                        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                            <Filter size={14} color="#888" />
                            <button
                                onClick={() => setFilterFormat('all')}
                                style={{
                                    padding: '4px 10px', borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 12,
                                    background: filterFormat === 'all' ? '#6c63ff' : '#1a1a2e', color: '#fff',
                                }}
                            >All</button>
                            {allFormats.map(fmt => (
                                <button
                                    key={fmt}
                                    onClick={() => setFilterFormat(fmt)}
                                    style={{
                                        padding: '4px 10px', borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 12,
                                        background: filterFormat === fmt ? '#6c63ff' : '#1a1a2e', color: '#fff',
                                    }}
                                >{fmt} ({formatCounts[fmt]})</button>
                            ))}
                        </div>
                    </div>

                    {/* Model list */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {filteredModels.map((model, i) => (
                            <div key={i} style={{
                                padding: '12px 16px', background: '#12122a', border: '1px solid #222',
                                borderRadius: 8, display: 'flex', alignItems: 'center', gap: 12,
                            }}>
                                <span style={{
                                    padding: '2px 8px', background: '#6c63ff22', color: '#6c63ff',
                                    borderRadius: 4, fontSize: 11, fontWeight: 600, minWidth: 60, textAlign: 'center',
                                }}>
                                    {model.extension}
                                </span>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <p style={{ margin: 0, fontWeight: 500, fontSize: 14, wordBreak: 'break-all' }}>{model.filename}</p>
                                    <p style={{ margin: 0, color: '#666', fontSize: 12 }}>{model.path}</p>
                                </div>
                                <span style={{ color: '#888', fontSize: 12, whiteSpace: 'nowrap' }}>{model.size_human}</span>
                                {model.quantization && (
                                    <span style={{
                                        padding: '2px 6px', background: '#ff6b3522', color: '#ff6b35',
                                        borderRadius: 4, fontSize: 11,
                                    }}>{model.quantization}</span>
                                )}
                                <span style={{
                                    padding: '2px 6px', background: '#0da47022', color: '#0da470',
                                    borderRadius: 4, fontSize: 11,
                                }}>{model.category}</span>
                                <button
                                    onClick={() => importModel(model)}
                                    disabled={importing === model.path || importResult?.path === model.path && importResult?.status !== 'error'}
                                    style={{
                                        padding: '6px 14px', background: '#0da470', color: '#fff', border: 'none',
                                        borderRadius: 6, cursor: 'pointer', fontSize: 12,
                                        opacity: (importing === model.path || (importResult?.path === model.path && importResult?.status !== 'error')) ? 0.5 : 1,
                                    }}
                                >
                                    {importing === model.path ? '...' :
                                        importResult?.path === model.path && importResult?.status === 'imported' ? '✓ Imported' :
                                            importResult?.path === model.path && importResult?.status === 'already_exists' ? '✓ Exists' :
                                                <><Download size={12} /> Import</>}
                                </button>
                            </div>
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}
