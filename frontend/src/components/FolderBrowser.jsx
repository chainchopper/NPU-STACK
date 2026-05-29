import React, { useState, useEffect } from 'react';
import { Folder, HardDrive, ChevronRight, ArrowUp, X, Check } from 'lucide-react';
import { apiUrl } from '../api/client';

/**
 * Reusable folder browser modal.
 * Props:
 *   open        — boolean, whether modal is visible
 *   onClose     — callback when modal is dismissed
 *   onSelect    — callback(path) when user confirms a folder selection
 *   showFiles   — if true, show model files alongside folders (default: false)
 *   title       — modal title (default: "Browse Folder")
 */
export default function FolderBrowser({ open, onClose, onSelect, showFiles = false, title = "Browse Folder" }) {
    const [currentPath, setCurrentPath] = useState('');
    const [parentPath, setParentPath] = useState(null);
    const [folders, setFolders] = useState([]);
    const [files, setFiles] = useState([]);
    const [drives, setDrives] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        if (open) loadDrives();
    }, [open]);

    const loadDrives = async () => {
        setLoading(true);
        setError('');
        try {
            const res = await fetch(apiUrl('/browse/drives'));
            const data = await res.json();
            setDrives(data.drives || []);
            setCurrentPath('');
            setParentPath(null);
            setFolders([]);
            setFiles([]);
        } catch {
            setError('Failed to load drives');
        }
        setLoading(false);
    };

    const browse = async (path) => {
        setLoading(true);
        setError('');
        try {
            const res = await fetch(`${apiUrl('/browse')}?path=${encodeURIComponent(path)}`);
            if (!res.ok) {
                const err = await res.json();
                setError(err.detail || 'Access denied');
                setLoading(false);
                return;
            }
            const data = await res.json();
            setCurrentPath(data.current);
            setParentPath(data.parent);
            setFolders(data.folders || []);
            setFiles(data.files || []);
        } catch {
            setError('Failed to browse directory');
        }
        setLoading(false);
    };

    const goUp = () => {
        if (parentPath) browse(parentPath);
        else loadDrives();
    };

    if (!open) return null;

    const breadcrumbs = currentPath ? currentPath.split('/').filter(Boolean) : [];

    return (
        <div style={styles.overlay} onClick={onClose}>
            <div style={styles.modal} onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div style={styles.header}>
                    <h3 style={{ margin: 0, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Folder size={18} /> {title}
                    </h3>
                    <button onClick={onClose} style={styles.closeBtn}><X size={18} /></button>
                </div>

                {/* Breadcrumb / path bar */}
                <div style={styles.pathBar}>
                    <button onClick={loadDrives} style={styles.pathBtn} title="Drives">
                        <HardDrive size={14} />
                    </button>
                    {currentPath && (
                        <button onClick={goUp} style={styles.pathBtn} title="Up">
                            <ArrowUp size={14} />
                        </button>
                    )}
                    <div style={styles.breadcrumbs}>
                        {breadcrumbs.map((seg, i) => {
                            const partial = breadcrumbs.slice(0, i + 1).join('/');
                            return (
                                <span key={i} style={{ display: 'inline-flex', alignItems: 'center' }}>
                                    <ChevronRight size={12} color="#555" />
                                    <button
                                        onClick={() => browse(partial)}
                                        style={{ ...styles.pathBtn, fontSize: 12 }}
                                    >{seg}</button>
                                </span>
                            );
                        })}
                    </div>
                </div>

                {error && <p style={{ color: '#ff6b6b', padding: '0 16px', fontSize: 13 }}>{error}</p>}

                {/* Content */}
                <div style={styles.content}>
                    {loading ? (
                        <p style={{ color: '#888', textAlign: 'center', padding: 32 }}>Loading...</p>
                    ) : !currentPath ? (
                        /* Drive list */
                        drives.map((d, i) => (
                            <button key={i} onClick={() => browse(d.path)} style={styles.item}>
                                <HardDrive size={16} color="#6c63ff" />
                                <span style={{ flex: 1, fontWeight: 500 }}>{d.label}</span>
                                <span style={{ color: '#666', fontSize: 12 }}>
                                    {d.free_gb} GB free / {d.total_gb} GB
                                </span>
                            </button>
                        ))
                    ) : (
                        <>
                            {folders.length === 0 && files.length === 0 && (
                                <p style={{ color: '#666', textAlign: 'center', padding: 24 }}>Empty directory</p>
                            )}
                            {folders.map((f, i) => (
                                <button key={`f-${i}`} onClick={() => browse(f.path)} style={styles.item}>
                                    <Folder size={16} color="#f0c040" />
                                    <span style={{ flex: 1 }}>{f.name}</span>
                                    <ChevronRight size={14} color="#555" />
                                </button>
                            ))}
                            {showFiles && files.map((f, i) => (
                                <div key={`m-${i}`} style={{ ...styles.item, opacity: 0.8, cursor: 'default' }}>
                                    <span style={{
                                        padding: '1px 6px', background: '#6c63ff22', color: '#6c63ff',
                                        borderRadius: 3, fontSize: 10, fontWeight: 600,
                                    }}>{f.extension}</span>
                                    <span style={{ flex: 1, fontSize: 13 }}>{f.name}</span>
                                    <span style={{ color: '#666', fontSize: 11 }}>{f.size_human}</span>
                                </div>
                            ))}
                        </>
                    )}
                </div>

                {/* Footer */}
                <div style={styles.footer}>
                    <span style={{ color: '#888', fontSize: 12, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {currentPath || 'Select a drive'}
                    </span>
                    <button
                        onClick={() => { if (currentPath) { onSelect(currentPath); onClose(); } }}
                        disabled={!currentPath}
                        style={{
                            ...styles.selectBtn,
                            opacity: currentPath ? 1 : 0.4,
                        }}
                    >
                        <Check size={14} /> Select Folder
                    </button>
                </div>
            </div>
        </div>
    );
}

const styles = {
    overlay: {
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9999,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
    },
    modal: {
        background: '#16162a', border: '1px solid #333', borderRadius: 12,
        width: '90%', maxWidth: 600, maxHeight: '80vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
    },
    header: {
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 16px', borderBottom: '1px solid #222',
    },
    closeBtn: {
        background: 'none', border: 'none', color: '#888', cursor: 'pointer', padding: 4,
    },
    pathBar: {
        display: 'flex', alignItems: 'center', gap: 4, padding: '8px 16px',
        borderBottom: '1px solid #1a1a2e', flexWrap: 'wrap',
    },
    pathBtn: {
        background: '#1a1a2e', border: '1px solid #333', borderRadius: 4,
        color: '#ccc', cursor: 'pointer', padding: '3px 8px', fontSize: 13,
        display: 'inline-flex', alignItems: 'center', gap: 4,
    },
    breadcrumbs: {
        display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap',
    },
    content: {
        flex: 1, overflowY: 'auto', padding: '4px 0',
        minHeight: 200, maxHeight: 400,
    },
    item: {
        display: 'flex', alignItems: 'center', gap: 10, padding: '8px 16px',
        background: 'transparent', border: 'none', color: '#ddd', cursor: 'pointer',
        width: '100%', textAlign: 'left', fontSize: 14, transition: 'background 0.15s',
    },
    footer: {
        display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px',
        borderTop: '1px solid #222',
    },
    selectBtn: {
        padding: '8px 16px', background: '#6c63ff', color: '#fff', border: 'none',
        borderRadius: 6, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
        fontSize: 13, fontWeight: 500,
    },
};
