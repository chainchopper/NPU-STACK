import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
    Camera, Square, Circle, Settings, SlidersHorizontal,
    Monitor, Cpu, Zap, Loader, AlertCircle, Search,
    FolderOpen, RefreshCw
} from 'lucide-react';
import { apiUrl, websocketUrl } from '../api/client';

// Detection class colors palette
const CLASS_COLORS = [
    '#6c63ff', '#ff6b35', '#0da470', '#ff3860', '#00d1ff',
    '#ffdd57', '#b86bff', '#36d1dc', '#ff6b6b', '#48c774',
];

// Format byte sizes nicely
const humanSize = (bytes) => {
    if (!bytes) return '—';
    if (bytes > 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
    if (bytes > 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
    if (bytes > 1e3) return `${(bytes / 1e3).toFixed(0)} KB`;
    return `${bytes} B`;
};

export default function WebcamTest() {
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const wsRef = useRef(null);
    const frameLoopRef = useRef(null);

    // Models from DB
    const [models, setModels] = useState([]);
    const [loadingModels, setLoadingModels] = useState(true);
    const [selectedModelId, setSelectedModelId] = useState('');
    const [modelFilter, setModelFilter] = useState('');
    const [customPath, setCustomPath] = useState('');
    const [useCustomPath, setUseCustomPath] = useState(false);

    // Webcam state
    const [streaming, setStreaming] = useState(false);
    const [modelLoaded, setModelLoaded] = useState(false);
    const [loadingModel, setLoadingModel] = useState(false);
    const [confidence, setConfidence] = useState(0.5);
    const [maxDetections, setMaxDetections] = useState(20);
    const [stats, setStats] = useState({ fps: 0, inferenceMs: 0, detections: 0 });
    const [detections, setDetections] = useState([]);
    const [error, setError] = useState('');
    const [backend, setBackend] = useState('auto');
    const [loadedModelName, setLoadedModelName] = useState('');

    // Fetch models from the DB
    const fetchModels = async () => {
        setLoadingModels(true);
        try {
            const res = await fetch(apiUrl('/models'));
            const data = await res.json();
            setModels(data.models || []);
        } catch (e) {
            console.error('Failed to fetch models', e);
        }
        setLoadingModels(false);
    };

    useEffect(() => {
        fetchModels();
        // Also check if a model is already loaded
        fetch(apiUrl('/webcam/status')).then(r => r.json()).then(data => {
            if (data.model_loaded) {
                setModelLoaded(true);
                setLoadedModelName(data.model_path || 'Previously loaded');
            }
        }).catch(() => { });
    }, []);

    // Filter models for display — show compatible formats
    const compatibleFormats = ['onnx', 'openvino', 'pytorch', 'ultralytics'];
    const filteredModels = models.filter(m => {
        const nameMatch = !modelFilter || m.name.toLowerCase().includes(modelFilter.toLowerCase());
        const formatStr = (m.format || m.framework || '').toLowerCase();
        const extMatch = m.file_path?.toLowerCase().endsWith('.onnx') || m.file_path?.toLowerCase().endsWith('.pt');
        const formatMatch = compatibleFormats.some(fmt => formatStr.includes(fmt)) || extMatch;
        return nameMatch && formatMatch;
    });

    // Get the actual file path for the selected model
    const getModelPath = () => {
        if (useCustomPath) return customPath;
        const model = models.find(m => m.id === parseInt(selectedModelId));
        return model?.file_path || '';
    };

    const loadModel = async () => {
        setError('');
        setLoadingModel(true);
        const path = getModelPath();
        if (!path) {
            setError('No model selected.');
            setLoadingModel(false);
            return;
        }
        try {
            const res = await fetch(
                `${apiUrl('/webcam/load')}?model_path=${encodeURIComponent(path)}&backend=${backend}`,
                { method: 'POST' }
            );
            const data = await res.json();
            if (res.ok) {
                setModelLoaded(true);
                const model = models.find(m => m.id === parseInt(selectedModelId));
                setLoadedModelName(model?.name || path.split(/[\\/]/).pop());
            } else {
                setError(data.detail || 'Failed to load model');
            }
        } catch (e) {
            setError('Failed to connect to backend');
        }
        setLoadingModel(false);
    };

    const startStream = async () => {
        setError('');
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480, facingMode: 'user' }
            });
            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                await videoRef.current.play();
            }

            const ws = new WebSocket(websocketUrl('/api/webcam/stream'));
            wsRef.current = ws;

            ws.onopen = () => {
                ws.send(JSON.stringify({ type: 'config', confidence, max_detections: maxDetections }));
                setStreaming(true);
                startFrameLoop();
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'detections') {
                    setDetections(data.detections || []);
                    setStats({
                        fps: Math.round(1000 / Math.max(data.inference_ms, 1)),
                        inferenceMs: data.inference_ms,
                        detections: data.count,
                    });
                    drawDetections(data.detections || [], data.resolution);
                } else if (data.type === 'error') {
                    setError(data.message);
                }
            };

            ws.onerror = () => setError('WebSocket connection error');
            ws.onclose = () => setStreaming(false);
        } catch (e) {
            setError(`Camera access denied: ${e.message}`);
        }
    };

    const stopStream = () => {
        if (frameLoopRef.current) {
            clearTimeout(frameLoopRef.current);
            frameLoopRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        if (videoRef.current?.srcObject) {
            videoRef.current.srcObject.getTracks().forEach(t => t.stop());
            videoRef.current.srcObject = null;
        }
        setStreaming(false);
        setDetections([]);
    };

    const startFrameLoop = () => {
        const sendFrame = () => {
            if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
            if (!videoRef.current) return;

            const canvas = document.createElement('canvas');
            canvas.width = 640;
            canvas.height = 480;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(videoRef.current, 0, 0, 640, 480);

            canvas.toBlob((blob) => {
                if (blob && wsRef.current?.readyState === WebSocket.OPEN) {
                    blob.arrayBuffer().then(buf => {
                        wsRef.current.send(new Uint8Array(buf));
                    });
                }
            }, 'image/jpeg', 0.7);

            frameLoopRef.current = setTimeout(sendFrame, 100); // ~10 fps
        };
        sendFrame();
    };

    const drawDetections = (dets, resolution) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        canvas.width = 640;
        canvas.height = 480;
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const scaleX = resolution ? 640 / resolution.width : 1;
        const scaleY = resolution ? 480 / resolution.height : 1;

        dets.forEach((det) => {
            const color = CLASS_COLORS[det.class_id % CLASS_COLORS.length];
            const x1 = det.x1 * scaleX;
            const y1 = det.y1 * scaleY;
            const x2 = det.x2 * scaleX;
            const y2 = det.y2 * scaleY;

            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

            const label = `${det.label} ${(det.confidence * 100).toFixed(0)}%`;
            ctx.font = 'bold 13px Inter, sans-serif';
            const textWidth = ctx.measureText(label).width;
            ctx.fillStyle = color;
            ctx.fillRect(x1, y1 - 22, textWidth + 12, 22);
            ctx.fillStyle = '#fff';
            ctx.fillText(label, x1 + 6, y1 - 6);
        });
    };

    useEffect(() => {
        return () => stopStream();
    }, []);

    useEffect(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'config', confidence, max_detections: maxDetections }));
        }
    }, [confidence, maxDetections]);

    const formatName = (m) => {
        const sizeStr = humanSize(m.file_size);
        return `${m.name}  (${m.format?.toUpperCase() || m.framework} — ${sizeStr})`;
    };

    return (
        <div>
            {/* Header */}
            <div className="section-header">
                <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Camera size={24} /> Webcam Object Detection
                </h2>
                <p className="text-secondary">
                    Load any imported or trained model and test it in real-time with your webcam. Supports ONNX, OpenVINO, and YOLO.
                </p>
            </div>

            <div className="grid-2">
                {/* Left Column — Model Selection + Controls */}
                <div>
                    {/* Model Picker Card */}
                    <div className="card" style={{ marginBottom: 16 }}>
                        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <Cpu size={16} /> Detection Model
                            </h3>
                            <div style={{ display: 'flex', gap: 8 }}>
                                <button
                                    onClick={() => setUseCustomPath(!useCustomPath)}
                                    className={`btn btn-sm ${useCustomPath ? 'btn-primary' : 'btn-outline'}`}
                                    title="Toggle custom path entry"
                                >
                                    <FolderOpen size={12} /> Custom Path
                                </button>
                                <button onClick={fetchModels} className="btn btn-sm btn-outline" title="Refresh model list">
                                    <RefreshCw size={12} />
                                </button>
                            </div>
                        </div>

                        {/* Model Source: DB Selector or Custom Path */}
                        {useCustomPath ? (
                            <div>
                                <label style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, display: 'block' }}>
                                    Manual Model Path
                                </label>
                                <input
                                    type="text"
                                    value={customPath}
                                    onChange={e => setCustomPath(e.target.value)}
                                    placeholder="C:\path\to\model.onnx  or  yolov8n.pt"
                                    className="form-input"
                                    style={{ width: '100%' }}
                                />
                            </div>
                        ) : (
                            <div>
                                {/* Search filter */}
                                <div style={{ position: 'relative', marginBottom: 10 }}>
                                    <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-muted)' }} />
                                    <input
                                        type="text"
                                        value={modelFilter}
                                        onChange={e => setModelFilter(e.target.value)}
                                        placeholder="Filter models..."
                                        className="form-input"
                                        style={{ width: '100%', paddingLeft: 32 }}
                                    />
                                </div>
                                <select
                                    value={selectedModelId}
                                    onChange={e => setSelectedModelId(e.target.value)}
                                    className="form-select"
                                    style={{ width: '100%' }}
                                >
                                    <option value="">
                                        {loadingModels ? 'Loading models...' : `Select from ${filteredModels.length} imported models…`}
                                    </option>
                                    {filteredModels.map(m => (
                                        <option key={m.id} value={m.id}>
                                            {formatName(m)}
                                        </option>
                                    ))}
                                </select>
                                {selectedModelId && (() => {
                                    const m = models.find(x => x.id === parseInt(selectedModelId));
                                    return m ? (
                                        <div style={{
                                            marginTop: 8, padding: '8px 12px', borderRadius: 8,
                                            background: 'var(--bg-input)', fontSize: 11, color: 'var(--text-muted)',
                                            fontFamily: 'var(--font-mono)', wordBreak: 'break-all'
                                        }}>
                                            {m.file_path}
                                        </div>
                                    ) : null;
                                })()}
                            </div>
                        )}

                        {/* Backend selector + Load button */}
                        <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
                            <select
                                value={backend}
                                onChange={e => setBackend(e.target.value)}
                                className="form-select"
                            >
                                <option value="auto">Auto-detect Backend</option>
                                <option value="onnx">ONNX Runtime</option>
                                <option value="openvino">OpenVINO</option>
                                <option value="ultralytics">Ultralytics YOLO</option>
                            </select>
                            <button
                                onClick={loadModel}
                                disabled={(!selectedModelId && !customPath) || loadingModel}
                                className="btn btn-primary"
                                style={{ whiteSpace: 'nowrap' }}
                            >
                                {loadingModel ? <><Loader size={14} className="spin" /> Loading…</> : <><Zap size={14} /> Load Model</>}
                            </button>
                        </div>

                        {modelLoaded && (
                            <div style={{
                                marginTop: 10, padding: '8px 12px', borderRadius: 8,
                                background: 'rgba(13,164,112,0.1)', border: '1px solid rgba(13,164,112,0.3)',
                                color: 'var(--accent-green)', fontSize: 13,
                                display: 'flex', alignItems: 'center', gap: 6,
                            }}>
                                <Zap size={14} /> Model loaded: <strong>{loadedModelName}</strong>
                            </div>
                        )}
                    </div>

                    {/* Inference Settings Card */}
                    <div className="card" style={{ marginBottom: 16 }}>
                        <div className="card-header">
                            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <SlidersHorizontal size={16} /> Inference Settings
                            </h3>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                            <div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>Confidence Threshold</label>
                                    <span style={{ color: 'var(--accent-blue)', fontSize: 13, fontWeight: 600 }}>
                                        {(confidence * 100).toFixed(0)}%
                                    </span>
                                </div>
                                <input
                                    type="range" min="0.1" max="0.95" step="0.05"
                                    value={confidence}
                                    onChange={e => setConfidence(parseFloat(e.target.value))}
                                    style={{ width: '100%' }}
                                />
                            </div>
                            <div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>Max Detections</label>
                                    <span style={{ color: 'var(--accent-blue)', fontSize: 13, fontWeight: 600 }}>
                                        {maxDetections}
                                    </span>
                                </div>
                                <input
                                    type="range" min="1" max="50" step="1"
                                    value={maxDetections}
                                    onChange={e => setMaxDetections(parseInt(e.target.value))}
                                    style={{ width: '100%' }}
                                />
                            </div>
                        </div>
                    </div>

                    {/* Stream Controls */}
                    <div className="card">
                        <div className="card-header">
                            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <Monitor size={16} /> Camera Controls
                            </h3>
                        </div>
                        {!streaming ? (
                            <button
                                onClick={startStream}
                                disabled={!modelLoaded}
                                className="btn btn-primary"
                                style={{ width: '100%', padding: '12px', fontSize: 15 }}
                            >
                                <Circle size={16} /> Start Webcam Detection
                            </button>
                        ) : (
                            <button
                                onClick={stopStream}
                                className="btn btn-danger"
                                style={{ width: '100%', padding: '12px', fontSize: 15 }}
                            >
                                <Square size={16} /> Stop Webcam
                            </button>
                        )}
                        {!modelLoaded && (
                            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8, textAlign: 'center' }}>
                                Load a model above to enable webcam detection.
                            </p>
                        )}
                    </div>
                </div>

                {/* Right Column — Video Feed + Stats */}
                <div>
                    {/* Stats Bar */}
                    {streaming && (
                        <div className="card" style={{ marginBottom: 16 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center' }}>
                                <div>
                                    <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--accent-green)' }}>{stats.fps}</div>
                                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>FPS</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--accent-amber)' }}>{stats.inferenceMs}ms</div>
                                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>Inference</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--accent-blue)' }}>{stats.detections}</div>
                                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>Objects</div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Error Alert */}
                    {error && (
                        <div style={{
                            padding: '10px 16px', marginBottom: 12, borderRadius: 'var(--radius-md)',
                            background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
                            color: 'var(--accent-red)', fontSize: 13,
                            display: 'flex', alignItems: 'center', gap: 8,
                        }}>
                            <AlertCircle size={16} /> {error}
                        </div>
                    )}

                    {/* Video Feed Card */}
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <div style={{
                            position: 'relative', width: '100%', aspectRatio: '4/3',
                            background: '#0a0a1a',
                        }}>
                            <video
                                ref={videoRef}
                                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                muted
                                playsInline
                            />
                            <canvas
                                ref={canvasRef}
                                style={{
                                    position: 'absolute', top: 0, left: 0,
                                    width: '100%', height: '100%', pointerEvents: 'none',
                                }}
                            />
                            {!streaming && (
                                <div style={{
                                    position: 'absolute', inset: 0, display: 'flex',
                                    flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                                    color: 'var(--text-muted)', gap: 8,
                                }}>
                                    <Camera size={48} strokeWidth={1} />
                                    <span style={{ fontSize: 14 }}>Webcam feed will appear here</span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Live Detection Tags */}
                    {detections.length > 0 && (
                        <div className="card" style={{ marginTop: 16 }}>
                            <div className="card-header">
                                <h3 className="card-title" style={{ fontSize: 13 }}>
                                    Live Detections ({detections.length})
                                </h3>
                            </div>
                            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                {detections.map((det, i) => (
                                    <span key={i} style={{
                                        padding: '4px 10px', borderRadius: 'var(--radius-sm)', fontSize: 12,
                                        background: `${CLASS_COLORS[det.class_id % CLASS_COLORS.length]}15`,
                                        color: CLASS_COLORS[det.class_id % CLASS_COLORS.length],
                                        border: `1px solid ${CLASS_COLORS[det.class_id % CLASS_COLORS.length]}33`,
                                        fontWeight: 600,
                                    }}>
                                        {det.label} ({(det.confidence * 100).toFixed(0)}%)
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
