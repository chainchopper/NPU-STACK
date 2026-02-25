import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Camera, Square, Circle, Settings, Maximize2 } from 'lucide-react';

const API = 'http://localhost:8000';

export default function WebcamTest() {
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const wsRef = useRef(null);
    const frameLoopRef = useRef(null);

    const [streaming, setStreaming] = useState(false);
    const [modelPath, setModelPath] = useState('');
    const [modelLoaded, setModelLoaded] = useState(false);
    const [confidence, setConfidence] = useState(0.5);
    const [stats, setStats] = useState({ fps: 0, inferenceMs: 0, detections: 0 });
    const [detections, setDetections] = useState([]);
    const [error, setError] = useState('');
    const [backend, setBackend] = useState('auto');

    // Colors for different classes
    const CLASS_COLORS = [
        '#6c63ff', '#ff6b35', '#0da470', '#ff3860', '#00d1ff',
        '#ffdd57', '#b86bff', '#36d1dc', '#ff6b6b', '#48c774',
    ];

    const loadModel = async () => {
        setError('');
        try {
            const res = await fetch(
                `${API}/api/webcam/load?model_path=${encodeURIComponent(modelPath)}&backend=${backend}`,
                { method: 'POST' }
            );
            const data = await res.json();
            if (res.ok) {
                setModelLoaded(true);
            } else {
                setError(data.detail || 'Failed to load model');
            }
        } catch (e) {
            setError('Failed to connect to backend');
        }
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

            // Connect WebSocket
            const ws = new WebSocket(`ws://localhost:8000/api/webcam/stream`);
            wsRef.current = ws;

            ws.onopen = () => {
                // Send initial config
                ws.send(JSON.stringify({ type: 'config', confidence }));
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
            cancelAnimationFrame(frameLoopRef.current);
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

        dets.forEach((det, i) => {
            const color = CLASS_COLORS[det.class_id % CLASS_COLORS.length];
            const x1 = det.x1 * scaleX;
            const y1 = det.y1 * scaleY;
            const x2 = det.x2 * scaleX;
            const y2 = det.y2 * scaleY;

            // Draw bounding box
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

            // Draw label
            const label = `${det.label} ${(det.confidence * 100).toFixed(0)}%`;
            ctx.font = 'bold 13px Inter, sans-serif';
            const textWidth = ctx.measureText(label).width;
            ctx.fillStyle = color;
            ctx.fillRect(x1, y1 - 20, textWidth + 10, 20);
            ctx.fillStyle = '#fff';
            ctx.fillText(label, x1 + 5, y1 - 5);
        });
    };

    useEffect(() => {
        return () => stopStream();
    }, []);

    // Update confidence on the WS
    useEffect(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'config', confidence }));
        }
    }, [confidence]);

    return (
        <div style={{ padding: 32 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
                <Camera size={28} />
                <h1 style={{ margin: 0, fontSize: 24 }}>Webcam Object Detection</h1>
            </div>
            <p style={{ color: '#999', marginBottom: 24, maxWidth: 600 }}>
                Test your trained models in real-time using your webcam. Load any YOLO, SSD, or ONNX detection
                model and see live bounding boxes with confidence scores.
            </p>

            {/* Model Loading */}
            <div style={{
                padding: 20, background: '#12122a', borderRadius: 12, border: '1px solid #222',
                marginBottom: 20,
            }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <Settings size={16} color="#888" />
                    <input
                        type="text"
                        value={modelPath}
                        onChange={e => setModelPath(e.target.value)}
                        placeholder="Path to detection model (.onnx, .pt, .xml)"
                        style={{
                            flex: 1, minWidth: 280, padding: '8px 12px',
                            background: '#1a1a2e', border: '1px solid #333', borderRadius: 6,
                            color: '#fff', fontSize: 13,
                        }}
                    />
                    <select
                        value={backend}
                        onChange={e => setBackend(e.target.value)}
                        style={{
                            padding: '8px 12px', background: '#1a1a2e', border: '1px solid #333',
                            borderRadius: 6, color: '#fff', fontSize: 13,
                        }}
                    >
                        <option value="auto">Auto-detect</option>
                        <option value="onnx">ONNX Runtime</option>
                        <option value="openvino">OpenVINO</option>
                        <option value="ultralytics">Ultralytics YOLO</option>
                    </select>
                    <button
                        onClick={loadModel}
                        disabled={!modelPath.trim()}
                        style={{
                            padding: '8px 16px', background: '#6c63ff', color: '#fff', border: 'none',
                            borderRadius: 6, cursor: 'pointer', fontSize: 13,
                            opacity: modelPath.trim() ? 1 : 0.5,
                        }}
                    >Load Model</button>
                </div>
                {modelLoaded && (
                    <p style={{ color: '#0da470', fontSize: 13, margin: '8px 0 0' }}>✓ Model loaded</p>
                )}
            </div>

            {/* Controls */}
            <div style={{
                display: 'flex', gap: 12, alignItems: 'center', marginBottom: 20, flexWrap: 'wrap',
            }}>
                {!streaming ? (
                    <button
                        onClick={startStream}
                        disabled={!modelLoaded}
                        style={{
                            padding: '10px 24px', background: '#0da470', color: '#fff', border: 'none',
                            borderRadius: 8, cursor: 'pointer', fontSize: 14,
                            display: 'flex', alignItems: 'center', gap: 6,
                            opacity: modelLoaded ? 1 : 0.5,
                        }}
                    ><Circle size={14} /> Start Webcam</button>
                ) : (
                    <button
                        onClick={stopStream}
                        style={{
                            padding: '10px 24px', background: '#ff3860', color: '#fff', border: 'none',
                            borderRadius: 8, cursor: 'pointer', fontSize: 14,
                            display: 'flex', alignItems: 'center', gap: 6,
                        }}
                    ><Square size={14} /> Stop</button>
                )}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <label style={{ color: '#888', fontSize: 13 }}>Confidence:</label>
                    <input
                        type="range" min="0.1" max="0.95" step="0.05"
                        value={confidence}
                        onChange={e => setConfidence(parseFloat(e.target.value))}
                        style={{ width: 120 }}
                    />
                    <span style={{ color: '#6c63ff', fontSize: 13, fontWeight: 600 }}>{(confidence * 100).toFixed(0)}%</span>
                </div>
                {streaming && (
                    <div style={{ display: 'flex', gap: 16, color: '#888', fontSize: 13 }}>
                        <span>FPS: <strong style={{ color: '#0da470' }}>{stats.fps}</strong></span>
                        <span>Inference: <strong style={{ color: '#ffdd57' }}>{stats.inferenceMs}ms</strong></span>
                        <span>Objects: <strong style={{ color: '#6c63ff' }}>{stats.detections}</strong></span>
                    </div>
                )}
            </div>

            {error && (
                <div style={{
                    padding: '10px 16px', background: '#ff386022', border: '1px solid #ff3860',
                    borderRadius: 8, color: '#ff3860', fontSize: 13, marginBottom: 16,
                }}>{error}</div>
            )}

            {/* Video + Canvas Overlay */}
            <div style={{
                position: 'relative', width: 640, height: 480,
                background: '#0a0a1a', borderRadius: 12, overflow: 'hidden',
                border: '1px solid #222',
            }}>
                <video
                    ref={videoRef}
                    style={{ width: 640, height: 480, objectFit: 'cover' }}
                    muted
                    playsInline
                />
                <canvas
                    ref={canvasRef}
                    style={{
                        position: 'absolute', top: 0, left: 0,
                        width: 640, height: 480, pointerEvents: 'none',
                    }}
                />
                {!streaming && (
                    <div style={{
                        position: 'absolute', inset: 0, display: 'flex',
                        alignItems: 'center', justifyContent: 'center',
                        color: '#555', fontSize: 16,
                    }}>
                        <Camera size={48} strokeWidth={1} />
                    </div>
                )}
            </div>

            {/* Detection List */}
            {detections.length > 0 && (
                <div style={{ marginTop: 16, maxWidth: 640 }}>
                    <h3 style={{ fontSize: 14, color: '#888', marginBottom: 8 }}>Live Detections</h3>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {detections.map((det, i) => (
                            <span key={i} style={{
                                padding: '4px 10px', borderRadius: 4, fontSize: 12,
                                background: `${CLASS_COLORS[det.class_id % CLASS_COLORS.length]}22`,
                                color: CLASS_COLORS[det.class_id % CLASS_COLORS.length],
                                border: `1px solid ${CLASS_COLORS[det.class_id % CLASS_COLORS.length]}44`,
                            }}>
                                {det.label} ({(det.confidence * 100).toFixed(0)}%)
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
