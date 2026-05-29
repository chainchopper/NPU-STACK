import React, { useState, useEffect, useCallback } from 'react';
import {
    FolderSearch, Download, HardDrive, Filter, RefreshCw, FolderOpen,
    CheckCircle, AlertCircle, Loader, Search, Database
} from 'lucide-react';
import FolderBrowser from '../components/FolderBrowser';
import { apiUrl } from '../api/client';

const humanSize = (bytes) => {
    if (!bytes) return '—';
    if (bytes > 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
    if (bytes > 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
    if (bytes > 1e3) return `${(bytes / 1e3).toFixed(0)} KB`;
    return `${bytes} B`;
};

export default function Scanner() {
    const [directory, setDirectory] = useState('');
    const [recursive, setRecursive] = useState(true);
    const [results, setResults] = useState(null);
    const [hints, setHints] = useState([]);
    const [loading, setLoading] = useState(false);
    const [importing, setImporting] = useState(null);
    const [importResults, setImportResults] = useState({}); // path -> result
    const [filterFormat, setFilterFormat] = useState('all');
    const [filterImport, setFilterImport] = useState('all'); // 'all' | 'not_imported' | 'imported'
    const [browseOpen, setBrowseOpen] = useState(false);
    const [searchText, setSearchText] = useState('');

    // Existing imported models — keyed by file_path for fast lookups
    const [importedPaths, setImportedPaths] = useState(new Set());

    useEffect(() => {
        fetch(apiUrl('/scan/hints'))
            .then(r => r.json())
            .then(data => setHints(data.hints || []))
            .catch(() => {});

        // Load existing models to mark already-imported
        fetch(apiUrl('/models'))
            .then(r => r.json())
            .then(data => {
                const paths = new Set((data.models || []).map(m => m.file_path).filter(Boolean));
                setImportedPaths(paths);
            })
            .catch(() => {});
    }, []);

    const scanDirectory = async () => {
        if (!directory.trim()) return;
        setLoading(true);
        setResults(null);
        setImportResults({});
        try {
            const res = await fetch(`${apiUrl('/scan')}?directory=${encodeURIComponent(directory)}&recursive=${recursive}`);
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
            const res = await fetch(apiUrl('/scan/import'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: model.path, copy_file: false }),
            });
            const data = await res.json();
            setImportResults(prev => ({ ...prev, [model.path]: data }));
            // Update imported paths set
            if (data.status === 'imported' || data.status === 'already_exists') {
                setImportedPaths(prev => new Set([...prev, model.path]));
            }
        } catch (e) {
            setImportResults(prev => ({ ...prev, [model.path]: { status: 'error', message: String(e) } }));
        }
        setImporting(null);
    };

    const importAll = async () => {
        const toImport = filteredModels.filter(m => !isImported(m));
        for (const model of toImport) {
            await importModel(model);
        }
    };

    const isImported = (model) => {
        return importedPaths.has(model.path) ||
               importResults[model.path]?.status === 'imported' ||
               importResults[model.path]?.status === 'already_exists';
    };

    // Apply all filters
    const allModels = results?.models || [];
    const filteredModels = allModels.filter(m => {
        if (filterFormat !== 'all' && m.format !== filterFormat) return false;
        if (filterImport === 'imported' && !isImported(m)) return false;
        if (filterImport === 'not_imported' && isImported(m)) return false;
        if (searchText && !m.filename.toLowerCase().includes(searchText.toLowerCase())) return false;
        return true;
    });

    const formatCounts = results?.by_format || {};
    const allFormats = Object.keys(formatCounts);
    const importedCount = allModels.filter(m => isImported(m)).length;
    const notImportedCount = allModels.length - importedCount;

    return (
        <div>
            <div className="section-header">
                <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <FolderSearch size={24} /> Model Scanner
                </h2>
                <p className="text-secondary">
                    Discover model files on your PC and import them into NPU-STACK's registry.
                    Models are referenced in-place — no files are copied or duplicated.
                </p>
            </div>

            {/* Scan Input Card */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    <input
                        type="text"
                        value={directory}
                        onChange={e => setDirectory(e.target.value)}
                        placeholder="Enter directory to scan (e.g. F:\ComfyUI\models)"
                        className="form-input"
                        style={{ flex: 1, minWidth: 280 }}
                        onKeyDown={e => e.key === 'Enter' && scanDirectory()}
                    />
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 13, cursor: 'pointer' }}>
                        <input type="checkbox" checked={recursive} onChange={e => setRecursive(e.target.checked)} />
                        Recursive
                    </label>
                    <button onClick={scanDirectory} disabled={loading || !directory.trim()} className="btn btn-primary">
                        {loading ? <><Loader size={14} className="spin" /> Scanning…</> : <><FolderSearch size={14} /> Scan</>}
                    </button>
                    <button onClick={() => setBrowseOpen(true)} className="btn btn-outline">
                        <FolderOpen size={14} /> Browse
                    </button>
                </div>
            </div>

            <FolderBrowser
                open={browseOpen}
                onClose={() => setBrowseOpen(false)}
                onSelect={(path) => setDirectory(path)}
                showFiles={true}
                title="Browse for Models"
            />

            {/* Quick Scan Hints */}
            {hints.filter(h => h.exists).length > 0 && (
                <div style={{ marginBottom: 16 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', marginRight: 8 }}>Quick scan:</span>
                    {hints.filter(h => h.exists).map((hint, i) => (
                        <button key={i} onClick={() => setDirectory(hint.path)}
                            className="btn btn-sm btn-ghost" style={{ marginRight: 4, marginBottom: 4 }}>
                            <HardDrive size={12} /> {hint.source}
                        </button>
                    ))}
                </div>
            )}

            {/* Results */}
            {results && (
                <>
                    {/* Summary + Filters */}
                    <div className="card" style={{ marginBottom: 16 }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                            <p style={{ margin: 0, fontSize: 14 }}>
                                Found <strong style={{ color: 'var(--accent-blue)' }}>{results.total_files}</strong> models
                                {importedCount > 0 && (
                                    <> · <span style={{ color: 'var(--accent-green)' }}>{importedCount} imported</span></>
                                )}
                                {notImportedCount > 0 && (
                                    <> · <span style={{ color: 'var(--text-muted)' }}>{notImportedCount} new</span></>
                                )}
                            </p>
                            {notImportedCount > 0 && (
                                <button onClick={importAll} className="btn btn-sm btn-primary" disabled={importing}>
                                    <Download size={12} /> Import All New ({notImportedCount})
                                </button>
                            )}
                        </div>

                        {/* Search */}
                        <div style={{ position: 'relative', marginBottom: 10 }}>
                            <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-muted)' }} />
                            <input type="text" value={searchText} onChange={e => setSearchText(e.target.value)}
                                placeholder="Filter by filename…" className="form-input"
                                style={{ width: '100%', paddingLeft: 32 }} />
                        </div>

                        {/* Import Status Filter */}
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
                            <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: '28px', marginRight: 4 }}>
                                <Database size={12} style={{ verticalAlign: -2 }} /> Status:
                            </span>
                            {[
                                { id: 'all', label: 'All' },
                                { id: 'not_imported', label: `New (${notImportedCount})` },
                                { id: 'imported', label: `Imported (${importedCount})` },
                            ].map(f => (
                                <button key={f.id} onClick={() => setFilterImport(f.id)}
                                    className={`btn btn-sm ${filterImport === f.id ? 'btn-primary' : 'btn-ghost'}`}>
                                    {f.label}
                                </button>
                            ))}
                        </div>

                        {/* Format Filter */}
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: '28px', marginRight: 4 }}>
                                <Filter size={12} style={{ verticalAlign: -2 }} /> Format:
                            </span>
                            <button onClick={() => setFilterFormat('all')}
                                className={`btn btn-sm ${filterFormat === 'all' ? 'btn-primary' : 'btn-ghost'}`}>
                                All
                            </button>
                            {allFormats.map(fmt => (
                                <button key={fmt} onClick={() => setFilterFormat(fmt)}
                                    className={`btn btn-sm ${filterFormat === fmt ? 'btn-primary' : 'btn-ghost'}`}>
                                    {fmt} ({formatCounts[fmt]})
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Model List */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {filteredModels.map((model, i) => {
                            const imported = isImported(model);
                            const result = importResults[model.path];
                            return (
                                <div key={i} className="card" style={{
                                    padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10,
                                    borderColor: imported ? 'rgba(13,164,112,0.2)' : undefined,
                                }}>
                                    {/* Imported badge */}
                                    {imported ? (
                                        <CheckCircle size={16} style={{ color: 'var(--accent-green)', flexShrink: 0 }} />
                                    ) : (
                                        <div style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid var(--border-subtle)', flexShrink: 0 }} />
                                    )}

                                    {/* Format badge */}
                                    <span style={{
                                        padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                                        background: 'rgba(108,99,255,0.12)', color: 'var(--accent-blue)',
                                        minWidth: 55, textAlign: 'center',
                                    }}>
                                        {model.extension}
                                    </span>

                                    {/* File info */}
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <p style={{ margin: 0, fontWeight: 500, fontSize: 13, wordBreak: 'break-all' }}>{model.filename}</p>
                                        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>{model.path}</p>
                                    </div>

                                    <span style={{ color: 'var(--text-muted)', fontSize: 12, whiteSpace: 'nowrap' }}>{model.size_human}</span>

                                    {model.quantization && (
                                        <span style={{
                                            padding: '2px 6px', borderRadius: 4, fontSize: 11,
                                            background: 'rgba(255,107,53,0.12)', color: '#ff6b35',
                                        }}>{model.quantization}</span>
                                    )}

                                    <span style={{
                                        padding: '2px 6px', borderRadius: 4, fontSize: 11,
                                        background: 'rgba(13,164,112,0.12)', color: 'var(--accent-green)',
                                    }}>{model.category}</span>

                                    {/* Import button */}
                                    {imported ? (
                                        <span style={{ fontSize: 11, color: 'var(--accent-green)', whiteSpace: 'nowrap' }}>
                                            ✓ {result?.status === 'already_exists' ? 'Already in DB' : 'Imported'}
                                        </span>
                                    ) : (
                                        <button
                                            onClick={() => importModel(model)}
                                            disabled={importing === model.path}
                                            className="btn btn-sm btn-primary"
                                            style={{ whiteSpace: 'nowrap' }}
                                        >
                                            {importing === model.path ? <Loader size={12} className="spin" /> : <Download size={12} />}
                                            Import
                                        </button>
                                    )}
                                </div>
                            );
                        })}
                        {filteredModels.length === 0 && (
                            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
                                No models match filters
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
