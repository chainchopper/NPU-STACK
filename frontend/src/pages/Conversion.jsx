import React, { useState, useEffect } from 'react';
import { ArrowRightLeft, Minimize2, Zap, Loader, AlertCircle, CheckCircle, Info, FileBox } from 'lucide-react';

const API = 'http://localhost:8000';

const humanSize = (bytes) => {
    if (!bytes) return '—';
    if (bytes > 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
    if (bytes > 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
    if (bytes > 1e3) return `${(bytes / 1e3).toFixed(0)} KB`;
    return `${bytes} B`;
};

export default function Conversion() {
    const [models, setModels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [converting, setConverting] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [mode, setMode] = useState('convert'); // 'convert' or 'quantize'

    // Cross-conversion paths from the backend
    const [conversionPaths, setConversionPaths] = useState([]);

    // Convert form
    const [selectedModelId, setSelectedModelId] = useState('');
    const [targetFormat, setTargetFormat] = useState('');
    const [outputName, setOutputName] = useState('');
    const [opsetVersion, setOpsetVersion] = useState(17);
    const [fp16, setFp16] = useState(false);
    const [quantizeTf, setQuantizeTf] = useState(false);
    const [inputShape, setInputShape] = useState('');

    // Quantize form
    const [quantizeModelId, setQuantizeModelId] = useState('');
    const [quantMethod, setQuantMethod] = useState('dynamic');
    const [weightType, setWeightType] = useState('int8');
    const [calibSamples, setCalibSamples] = useState(100);
    const [quantOutputName, setQuantOutputName] = useState('');

    useEffect(() => {
        Promise.all([
            fetch(`${API}/api/models`).then(r => r.json()),
            fetch(`${API}/api/convert/cross/paths`).then(r => r.json()),
        ]).then(([modelsData, pathsData]) => {
            setModels(modelsData.models || []);
            setConversionPaths(pathsData.paths || []);
        }).catch(e => console.error(e))
          .finally(() => setLoading(false));
    }, []);

    // Selected model object
    const selectedModel = models.find(m => m.id === parseInt(selectedModelId));
    const quantModel = models.find(m => m.id === parseInt(quantizeModelId));

    // Determine which target formats are available for the selected model's format
    const getTargetsForModel = () => {
        if (!selectedModel) return [];
        const ext = ((selectedModel.file_path || '').match(/\.[^.]+$/) || [''])[0].toLowerCase();
        return conversionPaths.filter(p => p.source_extensions.includes(ext));
    };
    const availableTargets = getTargetsForModel();

    // Auto-generate output name
    useEffect(() => {
        if (selectedModel && targetFormat) {
            const target = conversionPaths.find(p => p.id === targetFormat);
            const baseName = selectedModel.name.replace(/[^a-zA-Z0-9_-]/g, '_');
            const suffix = target ? target.to_format.toLowerCase().replace(/[^a-z0-9]/g, '') : targetFormat;
            setOutputName(`${baseName}_${suffix}`);
        }
    }, [selectedModelId, targetFormat]);

    useEffect(() => {
        if (quantModel && quantMethod) {
            const baseName = quantModel.name.replace(/[^a-zA-Z0-9_-]/g, '_');
            setQuantOutputName(`${baseName}_${quantMethod}_${weightType}`);
        }
    }, [quantizeModelId, quantMethod, weightType]);

    const handleConvert = async (e) => {
        e.preventDefault();
        if (!selectedModel) return;
        setConverting(true);
        setResult(null);
        setError('');

        const target = conversionPaths.find(p => p.id === targetFormat);

        try {
            const body = {
                model_path: selectedModel.file_path,
                target_format: target?.to_format?.toLowerCase()?.replace(/\s+/g, '') || targetFormat,
                output_name: outputName || undefined,
                opset_version: opsetVersion,
                fp16: fp16,
                quantize: quantizeTf,
                input_shape: inputShape ? JSON.parse(inputShape) : undefined,
            };

            const res = await fetch(`${API}/api/convert/cross`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (res.ok) {
                setResult({ success: true, ...data });
                // Refresh models list
                fetch(`${API}/api/models`).then(r => r.json()).then(d => setModels(d.models || []));
            } else {
                setError(data.detail || 'Conversion failed');
            }
        } catch (e) {
            setError(e.message || 'Conversion failed');
        }
        setConverting(false);
    };

    const handleQuantize = async (e) => {
        e.preventDefault();
        if (!quantModel) return;
        setConverting(true);
        setResult(null);
        setError('');

        try {
            const body = {
                model_id: parseInt(quantizeModelId),
                method: quantMethod,
                weight_type: weightType,
                calibration_samples: calibSamples,
            };

            const res = await fetch(`${API}/api/convert/quantize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (res.ok) {
                setResult({ success: true, ...data });
                fetch(`${API}/api/models`).then(r => r.json()).then(d => setModels(d.models || []));
            } else {
                setError(data.detail || 'Quantization failed');
            }
        } catch (e) {
            setError(e.message || 'Quantization failed');
        }
        setConverting(false);
    };

    // Show/hide opset, fp16, quantize, input_shape based on target
    const selectedPath = conversionPaths.find(p => p.id === targetFormat);
    const showInputShape = selectedPath && selectedPath.from_format === 'PyTorch' && selectedPath.to_format === 'ONNX';
    const showFp16 = selectedPath && selectedPath.to_format === 'TensorRT';
    const showQuantize = selectedPath && selectedPath.to_format.includes('TFLite');
    const showOpset = selectedPath && (selectedPath.to_format === 'ONNX' || selectedPath.from_format === 'PyTorch');

    return (
        <div>
            <div className="section-header">
                <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <ArrowRightLeft size={24} /> Conversion Studio
                </h2>
                <p className="text-secondary">
                    Convert between {conversionPaths.length} format paths and quantize models for NPU/TPU deployment.
                </p>
            </div>

            {/* Mode Toggle */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                <button className={`btn ${mode === 'convert' ? 'btn-primary' : 'btn-outline'}`} onClick={() => { setMode('convert'); setResult(null); setError(''); }}>
                    <ArrowRightLeft size={14} /> Format Conversion
                </button>
                <button className={`btn ${mode === 'quantize' ? 'btn-primary' : 'btn-outline'}`} onClick={() => { setMode('quantize'); setResult(null); setError(''); }}>
                    <Minimize2 size={14} /> Quantization
                </button>
            </div>

            <div className="grid-2">
                {/* Left: Form */}
                <div>
                    {mode === 'convert' ? (
                        <form onSubmit={handleConvert}>
                            {/* Source Model */}
                            <div className="card" style={{ marginBottom: 16 }}>
                                <div className="card-header">
                                    <h3 className="card-title"><FileBox size={16} /> Source Model</h3>
                                </div>
                                <select
                                    className="form-select" style={{ width: '100%' }}
                                    value={selectedModelId} onChange={e => { setSelectedModelId(e.target.value); setTargetFormat(''); }}
                                    required
                                >
                                    <option value="">Select a model ({models.length} available)…</option>
                                    {models.map(m => (
                                        <option key={m.id} value={m.id}>
                                            {m.name} ({m.format?.toUpperCase()} — {humanSize(m.file_size)})
                                        </option>
                                    ))}
                                </select>

                                {/* Source Model Info Card */}
                                {selectedModel && (
                                    <div style={{
                                        marginTop: 10, padding: '10px 14px', borderRadius: 'var(--radius-md)',
                                        background: 'var(--bg-input)', fontSize: 13, display: 'grid',
                                        gridTemplateColumns: '1fr 1fr', gap: '6px 16px',
                                    }}>
                                        <div><span style={{ color: 'var(--text-muted)' }}>Format:</span> <strong>{selectedModel.format?.toUpperCase()}</strong></div>
                                        <div><span style={{ color: 'var(--text-muted)' }}>Framework:</span> <strong>{selectedModel.framework}</strong></div>
                                        <div><span style={{ color: 'var(--text-muted)' }}>Size:</span> <strong>{humanSize(selectedModel.file_size)}</strong></div>
                                        <div><span style={{ color: 'var(--text-muted)' }}>ID:</span> <strong>#{selectedModel.id}</strong></div>
                                        <div style={{ gridColumn: '1/-1', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', wordBreak: 'break-all' }}>
                                            {selectedModel.file_path}
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Target Format */}
                            <div className="card" style={{ marginBottom: 16 }}>
                                <div className="card-header">
                                    <h3 className="card-title"><Zap size={16} /> Target Format</h3>
                                </div>
                                <select
                                    className="form-select" style={{ width: '100%' }}
                                    value={targetFormat} onChange={e => setTargetFormat(e.target.value)}
                                    disabled={!selectedModel}
                                    required
                                >
                                    <option value="">
                                        {!selectedModel ? 'Select a source model first' :
                                         availableTargets.length === 0 ? 'No conversion paths for this format' :
                                         `Select target format (${availableTargets.length} available)…`}
                                    </option>
                                    {availableTargets.map(p => (
                                        <option key={p.id} value={p.id} disabled={!p.available}>
                                            {p.to_format} {p.available ? '✓' : `(requires: ${p.note})`}
                                        </option>
                                    ))}
                                </select>

                                {selectedPath && !selectedPath.available && (
                                    <div style={{
                                        marginTop: 8, padding: '8px 12px', borderRadius: 8,
                                        background: 'rgba(255,221,87,0.08)', border: '1px solid rgba(255,221,87,0.2)',
                                        color: 'var(--accent-amber)', fontSize: 12,
                                        display: 'flex', alignItems: 'center', gap: 6,
                                    }}>
                                        <AlertCircle size={14} /> Install required: <code>{selectedPath.note}</code>
                                    </div>
                                )}

                                {/* Output Name */}
                                {targetFormat && (
                                    <div style={{ marginTop: 12 }}>
                                        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                                            Output Model Name
                                        </label>
                                        <input
                                            type="text" className="form-input" style={{ width: '100%' }}
                                            value={outputName} onChange={e => setOutputName(e.target.value)}
                                            placeholder="Auto-generated name"
                                        />
                                    </div>
                                )}

                                {/* Dynamic Options */}
                                {showInputShape && (
                                    <div style={{ marginTop: 12 }}>
                                        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                                            Input Shape (JSON array, e.g. [1,3,224,224])
                                        </label>
                                        <input
                                            type="text" className="form-input" style={{ width: '100%' }}
                                            value={inputShape} onChange={e => setInputShape(e.target.value)}
                                            placeholder="[1, 3, 224, 224]"
                                        />
                                    </div>
                                )}
                                {showOpset && (
                                    <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
                                        <label style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>ONNX Opset:</label>
                                        <input type="number" className="form-input" value={opsetVersion} min={7} max={21}
                                            onChange={e => setOpsetVersion(Number(e.target.value))} style={{ width: 80 }} />
                                    </div>
                                )}
                                {showFp16 && (
                                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, cursor: 'pointer', fontSize: 13 }}>
                                        <input type="checkbox" checked={fp16} onChange={e => setFp16(e.target.checked)} />
                                        Enable FP16 mode (TensorRT)
                                    </label>
                                )}
                                {showQuantize && (
                                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, cursor: 'pointer', fontSize: 13 }}>
                                        <input type="checkbox" checked={quantizeTf} onChange={e => setQuantizeTf(e.target.checked)} />
                                        Enable INT8 quantization (TFLite)
                                    </label>
                                )}
                            </div>

                            <button type="submit" className="btn btn-primary" disabled={converting || !selectedModel || !targetFormat}
                                style={{ width: '100%', padding: 12, fontSize: 15, justifyContent: 'center' }}>
                                {converting ? <><Loader size={16} className="spin" /> Converting…</> : <><ArrowRightLeft size={16} /> Convert Model</>}
                            </button>
                        </form>
                    ) : (
                        /* Quantize Mode */
                        <form onSubmit={handleQuantize}>
                            <div className="card" style={{ marginBottom: 16 }}>
                                <div className="card-header">
                                    <h3 className="card-title"><FileBox size={16} /> Source Model</h3>
                                </div>
                                <select className="form-select" style={{ width: '100%' }}
                                    value={quantizeModelId} onChange={e => setQuantizeModelId(e.target.value)} required>
                                    <option value="">Select model to quantize…</option>
                                    {models.map(m => (
                                        <option key={m.id} value={m.id}>{m.name} ({m.format?.toUpperCase()} — {humanSize(m.file_size)})</option>
                                    ))}
                                </select>

                                {quantModel && (
                                    <div style={{
                                        marginTop: 10, padding: '10px 14px', borderRadius: 'var(--radius-md)',
                                        background: 'var(--bg-input)', fontSize: 13, display: 'grid',
                                        gridTemplateColumns: '1fr 1fr', gap: '6px 16px',
                                    }}>
                                        <div><span style={{ color: 'var(--text-muted)' }}>Format:</span> <strong>{quantModel.format?.toUpperCase()}</strong></div>
                                        <div><span style={{ color: 'var(--text-muted)' }}>Size:</span> <strong>{humanSize(quantModel.file_size)}</strong></div>
                                        <div style={{ gridColumn: '1/-1', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', wordBreak: 'break-all' }}>
                                            {quantModel.file_path}
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="card" style={{ marginBottom: 16 }}>
                                <div className="card-header">
                                    <h3 className="card-title"><Minimize2 size={16} /> Quantization Settings</h3>
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                    <div>
                                        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Method</label>
                                        <select className="form-select" style={{ width: '100%' }} value={quantMethod} onChange={e => setQuantMethod(e.target.value)}>
                                            <option value="dynamic">ONNX Dynamic INT8 (fast, no calibration)</option>
                                            <option value="static">ONNX Static INT8 (calibrated, better accuracy)</option>
                                            <option value="nncf_int8">NNCF INT8 (OpenVINO optimized)</option>
                                            <option value="nncf_int4">NNCF INT4 (maximum compression)</option>
                                        </select>
                                    </div>
                                    {quantMethod === 'dynamic' && (
                                        <div>
                                            <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Weight Type</label>
                                            <select className="form-select" style={{ width: '100%' }} value={weightType} onChange={e => setWeightType(e.target.value)}>
                                                <option value="int8">INT8 (signed)</option>
                                                <option value="uint8">UINT8 (unsigned)</option>
                                            </select>
                                        </div>
                                    )}
                                    {quantMethod === 'static' && (
                                        <div>
                                            <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Calibration Samples</label>
                                            <input type="number" className="form-input" value={calibSamples} min={10} max={1000}
                                                onChange={e => setCalibSamples(Number(e.target.value))} style={{ width: '100%' }} />
                                        </div>
                                    )}
                                    <div>
                                        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Output Name</label>
                                        <input type="text" className="form-input" style={{ width: '100%' }}
                                            value={quantOutputName} onChange={e => setQuantOutputName(e.target.value)}
                                            placeholder="Auto-generated" />
                                    </div>
                                </div>
                            </div>

                            <button type="submit" className="btn btn-primary" disabled={converting || !quantizeModelId}
                                style={{ width: '100%', padding: 12, fontSize: 15, justifyContent: 'center' }}>
                                {converting ? <><Loader size={16} className="spin" /> Quantizing…</> : <><Minimize2 size={16} /> Quantize Model</>}
                            </button>
                        </form>
                    )}
                </div>

                {/* Right: Result + Info */}
                <div>
                    {error && (
                        <div className="card" style={{ marginBottom: 16, borderColor: 'rgba(239,68,68,0.3)' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent-red)' }}>
                                <AlertCircle size={18} />
                                <strong>Error</strong>
                            </div>
                            <p style={{ marginTop: 8, fontSize: 13, color: 'var(--accent-red)' }}>{error}</p>
                        </div>
                    )}

                    {result?.success ? (
                        <div className="card" style={{ marginBottom: 16 }}>
                            <div className="card-header" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <CheckCircle size={18} style={{ color: 'var(--accent-green)' }} />
                                <h3 className="card-title" style={{ color: 'var(--accent-green)' }}>
                                    {result.message || 'Conversion Complete'}
                                </h3>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {result.output_path && <InfoRow label="Output" value={result.output_path} mono />}
                                {result.model_id && <InfoRow label="Model ID" value={`#${result.model_id}`} />}
                                {result.name && <InfoRow label="Name" value={result.name} />}
                                {result.original_size && <InfoRow label="Original" value={humanSize(result.original_size)} />}
                                {result.quantized_size && <InfoRow label="Quantized" value={humanSize(result.quantized_size)} />}
                                {result.compression_ratio && <InfoRow label="Compression" value={`${result.compression_ratio}x`} />}
                                {result.total_size && <InfoRow label="Total Size" value={humanSize(result.total_size)} />}
                                {result.method && <InfoRow label="Method" value={result.method} />}
                            </div>
                        </div>
                    ) : !error && (
                        <div className="card" style={{ marginBottom: 16 }}>
                            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>
                                <ArrowRightLeft size={36} strokeWidth={1} />
                                <p style={{ marginTop: 8 }}>Select a model and target format to see conversion results</p>
                            </div>
                        </div>
                    )}

                    {/* Conversion Paths Overview */}
                    <div className="card">
                        <div className="card-header">
                            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <Info size={16} /> Available Conversion Paths
                            </h3>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 300, overflowY: 'auto' }}>
                            {conversionPaths.map(p => (
                                <div key={p.id} style={{
                                    display: 'flex', alignItems: 'center', gap: 8,
                                    padding: '6px 10px', borderRadius: 'var(--radius-sm)',
                                    background: p.available ? 'rgba(13,164,112,0.06)' : 'rgba(255,255,255,0.02)',
                                    fontSize: 12,
                                }}>
                                    <span style={{
                                        width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                                        background: p.available ? 'var(--accent-green)' : 'var(--text-muted)',
                                    }} />
                                    <strong>{p.from_format}</strong>
                                    <span style={{ color: 'var(--text-muted)' }}>→</span>
                                    <strong>{p.to_format}</strong>
                                    <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 11 }}>
                                        {p.available ? '✓ Ready' : p.note}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function InfoRow({ label, value, mono }) {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
            <span style={{ color: 'var(--text-muted)' }}>{label}</span>
            <span style={{
                fontWeight: 600,
                fontFamily: mono ? 'var(--font-mono)' : 'inherit',
                fontSize: mono ? 11 : 13,
                maxWidth: '60%', textAlign: 'right', wordBreak: 'break-all',
            }}>{value}</span>
        </div>
    );
}
