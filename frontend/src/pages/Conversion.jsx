import React, { useState, useEffect } from 'react';
import { ArrowRightLeft, Minimize2, Box } from 'lucide-react';
import { listModels, convertModel, quantizeModel } from '../api/client';

export default function Conversion() {
    const [models, setModels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [converting, setConverting] = useState(false);
    const [result, setResult] = useState(null);
    const [mode, setMode] = useState('convert'); // 'convert' or 'quantize'

    const [convertForm, setConvertForm] = useState({
        model_id: '',
        target_format: 'openvino',
        compress_fp16: true,
    });

    const [quantizeForm, setQuantizeForm] = useState({
        model_id: '',
        method: 'dynamic',
        weight_type: 'int8',
        calibration_samples: 100,
    });

    useEffect(() => {
        listModels().then(setModels).catch(() => setModels([])).finally(() => setLoading(false));
    }, []);

    const handleConvert = async (e) => {
        e.preventDefault();
        setConverting(true);
        setResult(null);
        try {
            const res = await convertModel(Number(convertForm.model_id), convertForm.target_format, convertForm.compress_fp16);
            setResult({ success: true, ...res });
            listModels().then(setModels);
        } catch (e) {
            setResult({ success: false, error: e.message });
        }
        setConverting(false);
    };

    const handleQuantize = async (e) => {
        e.preventDefault();
        setConverting(true);
        setResult(null);
        try {
            const res = await quantizeModel(Number(quantizeForm.model_id), quantizeForm.method, quantizeForm.weight_type, quantizeForm.calibration_samples);
            setResult({ success: true, ...res });
            listModels().then(setModels);
        } catch (e) {
            setResult({ success: false, error: e.message });
        }
        setConverting(false);
    };

    const formatSize = (bytes) => {
        if (!bytes) return '—';
        return (bytes / 1024 / 1024).toFixed(2) + ' MB';
    };

    const onnxModels = models.filter(m => m.format === 'onnx');
    const allModels = models;

    return (
        <div>
            <div className="page-header">
                <h2>Conversion Studio</h2>
                <p>Convert and quantize models for NPU/TPU deployment</p>
            </div>

            {/* Mode Toggle */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
                <button className={`btn ${mode === 'convert' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => { setMode('convert'); setResult(null); }}>
                    <ArrowRightLeft size={16} /> Format Conversion
                </button>
                <button className={`btn ${mode === 'quantize' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => { setMode('quantize'); setResult(null); }}>
                    <Minimize2 size={16} /> Quantization
                </button>
            </div>

            <div className="grid-2">
                {/* Form */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">{mode === 'convert' ? 'Convert Model Format' : 'Quantize Model'}</h3>
                    </div>

                    {mode === 'convert' ? (
                        <form onSubmit={handleConvert}>
                            <div className="form-group">
                                <label className="form-label">Source Model (ONNX)</label>
                                <select className="form-select" value={convertForm.model_id} onChange={e => setConvertForm({ ...convertForm, model_id: e.target.value })} required>
                                    <option value="">Select a model...</option>
                                    {onnxModels.map(m => (
                                        <option key={m.id} value={m.id}>{m.name} ({formatSize(m.file_size)})</option>
                                    ))}
                                </select>
                            </div>
                            <div className="form-group">
                                <label className="form-label">Target Format</label>
                                <select className="form-select" value={convertForm.target_format} onChange={e => setConvertForm({ ...convertForm, target_format: e.target.value })}>
                                    <option value="openvino">OpenVINO IR (for Intel NPU)</option>
                                </select>
                            </div>
                            <div className="form-group">
                                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                                    <input type="checkbox" checked={convertForm.compress_fp16} onChange={e => setConvertForm({ ...convertForm, compress_fp16: e.target.checked })} />
                                    <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>Compress to FP16 (recommended for NPU)</span>
                                </label>
                            </div>
                            <button type="submit" className="btn btn-primary" disabled={converting || !convertForm.model_id} style={{ width: '100%', justifyContent: 'center' }}>
                                {converting ? 'Converting...' : 'Convert Model'}
                            </button>
                        </form>
                    ) : (
                        <form onSubmit={handleQuantize}>
                            <div className="form-group">
                                <label className="form-label">Source Model</label>
                                <select className="form-select" value={quantizeForm.model_id} onChange={e => setQuantizeForm({ ...quantizeForm, model_id: e.target.value })} required>
                                    <option value="">Select a model...</option>
                                    {allModels.map(m => (
                                        <option key={m.id} value={m.id}>{m.name} ({m.format} — {formatSize(m.file_size)})</option>
                                    ))}
                                </select>
                            </div>
                            <div className="form-group">
                                <label className="form-label">Quantization Method</label>
                                <select className="form-select" value={quantizeForm.method} onChange={e => setQuantizeForm({ ...quantizeForm, method: e.target.value })}>
                                    <option value="dynamic">ONNX Dynamic INT8 (fast, no calibration)</option>
                                    <option value="static">ONNX Static INT8 (calibrated, better accuracy)</option>
                                    <option value="nncf_int8">NNCF INT8 (OpenVINO optimized)</option>
                                    <option value="nncf_int4">NNCF INT4 (maximum compression)</option>
                                </select>
                            </div>
                            {quantizeForm.method === 'dynamic' && (
                                <div className="form-group">
                                    <label className="form-label">Weight Type</label>
                                    <select className="form-select" value={quantizeForm.weight_type} onChange={e => setQuantizeForm({ ...quantizeForm, weight_type: e.target.value })}>
                                        <option value="int8">INT8 (signed)</option>
                                        <option value="uint8">UINT8 (unsigned)</option>
                                    </select>
                                </div>
                            )}
                            {quantizeForm.method === 'static' && (
                                <div className="form-group">
                                    <label className="form-label">Calibration Samples</label>
                                    <input type="number" className="form-input" value={quantizeForm.calibration_samples} min={10} max={1000}
                                        onChange={e => setQuantizeForm({ ...quantizeForm, calibration_samples: Number(e.target.value) })} />
                                </div>
                            )}
                            <button type="submit" className="btn btn-primary" disabled={converting || !quantizeForm.model_id} style={{ width: '100%', justifyContent: 'center' }}>
                                {converting ? 'Quantizing...' : 'Quantize Model'}
                            </button>
                        </form>
                    )}
                </div>

                {/* Result */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Result</h3>
                    </div>
                    {result ? (
                        result.success ? (
                            <div>
                                <div style={{ padding: '16px', background: 'var(--accent-green-glow)', borderRadius: '10px', marginBottom: '16px' }}>
                                    <p style={{ color: 'var(--accent-green)', fontWeight: 600 }}>✅ {result.message || 'Operation completed successfully!'}</p>
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                    {result.model_id && <InfoLine label="New Model ID" value={`#${result.model_id}`} />}
                                    {result.name && <InfoLine label="Name" value={result.name} />}
                                    {result.compression_ratio && <InfoLine label="Compression Ratio" value={`${result.compression_ratio}x`} />}
                                    {result.original_size && <InfoLine label="Original Size" value={formatSize(result.original_size)} />}
                                    {result.quantized_size && <InfoLine label="Quantized Size" value={formatSize(result.quantized_size)} />}
                                    {result.total_size && <InfoLine label="Total Size" value={formatSize(result.total_size)} />}
                                    {result.method && <InfoLine label="Method" value={result.method} />}
                                </div>
                            </div>
                        ) : (
                            <div style={{ padding: '16px', background: 'var(--accent-red-glow)', borderRadius: '10px' }}>
                                <p style={{ color: 'var(--accent-red)', fontWeight: 500 }}>❌ {result.error}</p>
                            </div>
                        )
                    ) : (
                        <div className="empty-state" style={{ padding: '32px' }}>
                            <ArrowRightLeft size={36} />
                            <p className="text-secondary">Select a model and run a conversion to see results</p>
                        </div>
                    )}

                    {/* Info Panel */}
                    <div style={{ marginTop: '24px', padding: '16px', background: 'var(--bg-input)', borderRadius: '10px' }}>
                        <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>About NPU Quantization</h4>
                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                            Quantization reduces model precision from FP32 to INT8/INT4, enabling faster inference on NPU hardware.
                            <strong> Dynamic quantization</strong> is fast but less accurate.
                            <strong> Static quantization</strong> uses calibration data for better accuracy.
                            <strong> NNCF</strong> is Intel's Neural Network Compression Framework, optimized for OpenVINO + NPU.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

function InfoLine({ label, value }) {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>{label}</span>
            <span style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{value}</span>
        </div>
    );
}
