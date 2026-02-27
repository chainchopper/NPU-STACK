import React, { useState, useEffect } from 'react';
import {
    Cpu, RefreshCw, Box, CheckCircle, AlertTriangle, Search,
    Minimize2, GitMerge, Scissors, FileSearch, Loader, AlertCircle,
    Zap, FolderOpen, Info
} from 'lucide-react';
import FolderBrowser from '../components/FolderBrowser';

const API = 'http://localhost:8000';

const humanSize = (bytes) => {
    if (!bytes) return '—';
    if (bytes > 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
    if (bytes > 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
    if (bytes > 1e3) return `${(bytes / 1e3).toFixed(0)} KB`;
    return `${bytes} B`;
};

const TABS = [
    { id: 'inspect', label: 'Inspect', icon: FileSearch, desc: 'Read GGUF metadata' },
    { id: 'quantize', label: 'Quantize', icon: Minimize2, desc: 'Reduce precision for smaller/faster models' },
    { id: 'convert', label: 'HF → GGUF', icon: Zap, desc: 'Convert HuggingFace model dirs to GGUF' },
    { id: 'lora', label: 'Merge LoRA', icon: GitMerge, desc: 'Merge a LoRA adapter into base model' },
    { id: 'split', label: 'Split / Join', icon: Scissors, desc: 'Split large GGUFs into shards' },
];

export default function GGUFStudio() {
    const [activeTab, setActiveTab] = useState('inspect');
    const [status, setStatus] = useState(null);
    const [models, setModels] = useState([]);
    const [quantTypes, setQuantTypes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [running, setRunning] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');

    // Inspect state
    const [inspectModelId, setInspectModelId] = useState('');
    const [inspectCustomPath, setInspectCustomPath] = useState('');
    const [useCustomInspect, setUseCustomInspect] = useState(false);

    // Quantize state
    const [quantModelId, setQuantModelId] = useState('');
    const [quantType, setQuantType] = useState('Q4_K_M');
    const [quantOutputName, setQuantOutputName] = useState('');
    const [quantThreads, setQuantThreads] = useState(0);

    // Convert HF state
    const [hfModelDir, setHfModelDir] = useState('');
    const [hfOutputType, setHfOutputType] = useState('f16');

    // LoRA merge state
    const [loraBaseId, setLoraBaseId] = useState('');
    const [loraPath, setLoraPath] = useState('');
    const [loraOutputName, setLoraOutputName] = useState('');
    const [loraScale, setLoraScale] = useState(1.0);

    // Split state
    const [splitModelId, setSplitModelId] = useState('');
    const [splitMaxSize, setSplitMaxSize] = useState(4.0);

    // Browser state
    const [browserOpen, setBrowserOpen] = useState(false);
    const [browserTarget, setBrowserTarget] = useState(''); // 'inspect', 'convert', 'lora'

    useEffect(() => {
        Promise.all([
            fetch(`${API}/api/gguf/pipeline/status`).then(r => r.json()),
            fetch(`${API}/api/models`).then(r => r.json()),
            fetch(`${API}/api/gguf/pipeline/quant-types`).then(r => r.json()).catch(() => ({ quant_types: [] })),
        ]).then(([statusData, modelsData, quantData]) => {
            setStatus(statusData);
            setModels(modelsData.models || []);
            setQuantTypes(quantData.quant_types || []);
        }).catch(e => console.error(e))
            .finally(() => setLoading(false));
    }, []);

    const ggufModels = models.filter(m => m.format === 'gguf');
    const allModels = models;

    const getModel = (id) => models.find(m => m.id === parseInt(id));

    // Capability check
    const cap = status?.capabilities || {};
    const toolAvailable = status?.llama_cpp_tools?.available || {};

    const resetResult = () => { setResult(null); setError(''); };

    // Auto-generate output names
    useEffect(() => {
        const m = getModel(quantModelId);
        if (m) setQuantOutputName(`${m.name}_${quantType}`);
    }, [quantModelId, quantType]);

    useEffect(() => {
        const m = getModel(loraBaseId);
        if (m) setLoraOutputName(`${m.name}_lora_merged`);
    }, [loraBaseId]);

    const postForm = async (endpoint, formData) => {
        setRunning(true);
        resetResult();
        try {
            const res = await fetch(`${API}${endpoint}`, {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();
            if (res.ok && data.success !== false) {
                setResult(data);
            } else {
                setError(data.detail || data.error || 'Operation failed');
            }
        } catch (e) {
            setError(e.message);
        }
        setRunning(false);
    };

    const handleInspect = () => {
        const model = getModel(inspectModelId);
        const path = useCustomInspect ? inspectCustomPath : model?.file_path;
        if (!path) return;
        const fd = new FormData();
        fd.append('model_path', path);
        postForm('/api/gguf/inspect', fd);
    };

    const handleQuantize = () => {
        const model = getModel(quantModelId);
        if (!model?.file_path) return;
        const fd = new FormData();
        fd.append('input_path', model.file_path);
        fd.append('quant_type', quantType);
        if (quantOutputName) fd.append('output_name', quantOutputName);
        if (quantThreads > 0) fd.append('n_threads', quantThreads.toString());
        postForm('/api/gguf/quantize', fd);
    };

    const handleConvert = () => {
        if (!hfModelDir) return;
        const fd = new FormData();
        fd.append('model_dir', hfModelDir);
        fd.append('output_type', hfOutputType);
        postForm('/api/gguf/convert/hf-to-gguf', fd);
    };

    const handleMergeLora = () => {
        const base = getModel(loraBaseId);
        if (!base?.file_path || !loraPath) return;
        const fd = new FormData();
        fd.append('base_model_path', base.file_path);
        fd.append('lora_path', loraPath);
        if (loraOutputName) fd.append('output_name', loraOutputName);
        fd.append('scale', loraScale.toString());
        postForm('/api/gguf/merge/lora', fd);
    };

    const handleSplit = () => {
        const model = getModel(splitModelId);
        if (!model?.file_path) return;
        const fd = new FormData();
        fd.append('input_path', model.file_path);
        fd.append('max_size_gb', splitMaxSize.toString());
        postForm('/api/gguf/split', fd);
    };

    const ToolStatus = ({ toolKey, label }) => {
        const available = toolAvailable[toolKey];
        return (
            <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 8px', borderRadius: 4, fontSize: 11,
                background: available ? 'rgba(13,164,112,0.1)' : 'rgba(239,68,68,0.1)',
                color: available ? 'var(--accent-green)' : 'var(--accent-red)',
            }}>
                {available ? <CheckCircle size={10} /> : <AlertTriangle size={10} />}
                {label}
            </span>
        );
    };

    return (
        <div>
            <div className="section-header">
                <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Cpu size={24} /> GGUF Studio
                </h2>
                <p className="text-secondary">
                    Inspect, quantize, convert, merge, and split GGUF models. {ggufModels.length} GGUF models in registry.
                </p>
            </div>

            {/* Tool Status Bar */}
            {status && (
                <div className="card" style={{ marginBottom: 16 }}>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginRight: 4 }}>Pipeline Tools:</span>
                        <ToolStatus toolKey="llama-cli" label="llama-cli" />
                        <ToolStatus toolKey="llama-quantize" label="llama-quantize" />
                        <ToolStatus toolKey="llama-gguf-split" label="gguf-split" />
                        <ToolStatus toolKey="convert_hf_to_gguf" label="HF converter" />
                        <ToolStatus toolKey="llama-imatrix" label="imatrix" />
                        {status.gguf_python_lib?.available && (
                            <span style={{
                                display: 'inline-flex', alignItems: 'center', gap: 4,
                                padding: '2px 8px', borderRadius: 4, fontSize: 11,
                                background: 'rgba(13,164,112,0.1)', color: 'var(--accent-green)',
                            }}>
                                <CheckCircle size={10} /> gguf lib v{status.gguf_python_lib.version}
                            </span>
                        )}
                    </div>
                </div>
            )}

            {/* Tab Bar */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid var(--border-subtle)', paddingBottom: 4, overflowX: 'auto' }}>
                {TABS.map(tab => {
                    const Icon = tab.icon;
                    return (
                        <button
                            key={tab.id}
                            onClick={() => { setActiveTab(tab.id); resetResult(); }}
                            className={`btn btn-sm ${activeTab === tab.id ? 'btn-primary' : 'btn-ghost'}`}
                            style={{ whiteSpace: 'nowrap' }}
                        >
                            <Icon size={14} /> {tab.label}
                        </button>
                    );
                })}
            </div>

            <div className="grid-2">
                {/* Left: Active Tool Panel */}
                <div>
                    {/* ═══ INSPECT ═══ */}
                    {activeTab === 'inspect' && (
                        <div className="card">
                            <div className="card-header">
                                <h3 className="card-title"><FileSearch size={16} /> Inspect GGUF Metadata</h3>
                            </div>
                            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>
                                Read architecture, tensor count, quant info, vocab, and context length from any GGUF file.
                            </p>

                            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                                <button className={`btn btn-sm ${!useCustomInspect ? 'btn-primary' : 'btn-outline'}`}
                                    onClick={() => setUseCustomInspect(false)}>From Registry</button>
                                <button className={`btn btn-sm ${useCustomInspect ? 'btn-primary' : 'btn-outline'}`}
                                    onClick={() => setUseCustomInspect(true)}><FolderOpen size={12} /> Custom Path</button>
                            </div>

                            {useCustomInspect ? (
                                <div style={{ display: 'flex', gap: 8 }}>
                                    <input type="text" className="form-input" style={{ flex: 1 }}
                                        value={inspectCustomPath} onChange={e => setInspectCustomPath(e.target.value)}
                                        placeholder="Path to .gguf file" />
                                    <button className="btn btn-outline" onClick={() => { setBrowserTarget('inspect'); setBrowserOpen(true); }}>
                                        Browse
                                    </button>
                                </div>
                            ) : (
                                <select className="form-select" style={{ width: '100%' }}
                                    value={inspectModelId} onChange={e => setInspectModelId(e.target.value)}>
                                    <option value="">Select a GGUF model ({ggufModels.length} available)…</option>
                                    {ggufModels.map(m => (
                                        <option key={m.id} value={m.id}>{m.name} ({humanSize(m.file_size)})</option>
                                    ))}
                                </select>
                            )}

                            <button onClick={handleInspect} disabled={running || (!inspectModelId && !inspectCustomPath)}
                                className="btn btn-primary" style={{ width: '100%', marginTop: 12, justifyContent: 'center' }}>
                                {running ? <><Loader size={14} className="spin" /> Inspecting…</> : <><FileSearch size={14} /> Inspect Model</>}
                            </button>
                        </div>
                    )}

                    {/* ═══ QUANTIZE ═══ */}
                    {activeTab === 'quantize' && (
                        <div className="card">
                            <div className="card-header">
                                <h3 className="card-title"><Minimize2 size={16} /> Quantize GGUF</h3>
                            </div>
                            {!toolAvailable['llama-quantize'] && (
                                <div style={{
                                    padding: '8px 12px', borderRadius: 8, marginBottom: 12,
                                    background: 'rgba(255,184,0,0.08)', border: '1px solid rgba(255,184,0,0.2)',
                                    color: 'var(--accent-amber)', fontSize: 12,
                                    display: 'flex', alignItems: 'center', gap: 6,
                                }}>
                                    <AlertTriangle size={14} /> <strong>llama-quantize</strong> not found in PATH. Install llama.cpp tools to enable.
                                </div>
                            )}

                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                <div>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Source GGUF Model</label>
                                    <select className="form-select" style={{ width: '100%' }}
                                        value={quantModelId} onChange={e => setQuantModelId(e.target.value)}>
                                        <option value="">Select model…</option>
                                        {ggufModels.map(m => (
                                            <option key={m.id} value={m.id}>{m.name} ({humanSize(m.file_size)})</option>
                                        ))}
                                    </select>
                                    {getModel(quantModelId) && (
                                        <ModelInfoMini model={getModel(quantModelId)} />
                                    )}
                                </div>

                                <div>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Quantization Type</label>
                                    <select className="form-select" style={{ width: '100%' }}
                                        value={quantType} onChange={e => setQuantType(e.target.value)}>
                                        {(status?.quant_types_available || []).map(qt => (
                                            <option key={qt} value={qt}>
                                                {qt} {['Q4_K_M', 'Q5_K_M', 'Q6_K', 'Q8_0'].includes(qt) ? '⭐ recommended' : ''}
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                <div>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Output Name</label>
                                    <input type="text" className="form-input" style={{ width: '100%' }}
                                        value={quantOutputName} onChange={e => setQuantOutputName(e.target.value)}
                                        placeholder="Auto-generated" />
                                </div>

                                <div>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                                        Threads (0 = auto)
                                    </label>
                                    <input type="number" className="form-input" style={{ width: 100 }}
                                        value={quantThreads} min={0} max={64}
                                        onChange={e => setQuantThreads(Number(e.target.value))} />
                                </div>
                            </div>

                            <button onClick={handleQuantize} disabled={running || !quantModelId}
                                className="btn btn-primary" style={{ width: '100%', marginTop: 16, justifyContent: 'center' }}>
                                {running ? <><Loader size={14} className="spin" /> Quantizing…</> : <><Minimize2 size={14} /> Quantize Model</>}
                            </button>
                        </div>
                    )}

                    {/* ═══ CONVERT HF ═══ */}
                    {activeTab === 'convert' && (
                        <div className="card">
                            <div className="card-header">
                                <h3 className="card-title"><Zap size={16} /> Convert HuggingFace → GGUF</h3>
                            </div>
                            {!toolAvailable['convert_hf_to_gguf'] && (
                                <div style={{
                                    padding: '8px 12px', borderRadius: 8, marginBottom: 12,
                                    background: 'rgba(255,184,0,0.08)', border: '1px solid rgba(255,184,0,0.2)',
                                    color: 'var(--accent-amber)', fontSize: 12,
                                    display: 'flex', alignItems: 'center', gap: 6,
                                }}>
                                    <AlertTriangle size={14} /> <strong>convert_hf_to_gguf.py</strong> not found. Install llama.cpp Python tools.
                                </div>
                            )}
                            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>
                                Point to a local HuggingFace model directory (containing <code>config.json</code>, <code>*.safetensors</code> or <code>*.bin</code>)
                                to convert it to GGUF format for use with llama.cpp-based inference.
                            </p>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                <div>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Model Directory</label>
                                    <div style={{ display: 'flex', gap: 8 }}>
                                        <input type="text" className="form-input" style={{ flex: 1 }}
                                            value={hfModelDir} onChange={e => setHfModelDir(e.target.value)}
                                            placeholder="C:\Users\...\.cache\huggingface\hub\models--org--model\snapshots\..." />
                                        <button className="btn btn-outline" onClick={() => { setBrowserTarget('convert'); setBrowserOpen(true); }}>
                                            Browse
                                        </button>
                                    </div>
                                </div>
                                <div>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Output Precision</label>
                                    <select className="form-select" style={{ width: '100%' }}
                                        value={hfOutputType} onChange={e => setHfOutputType(e.target.value)}>
                                        <option value="f32">F32 (full precision, largest)</option>
                                        <option value="f16">F16 (half precision, recommended)</option>
                                        <option value="bf16">BF16 (bfloat16)</option>
                                        <option value="q8_0">Q8_0 (8-bit quantized)</option>
                                    </select>
                                </div>
                            </div>

                            <button onClick={handleConvert} disabled={running || !hfModelDir}
                                className="btn btn-primary" style={{ width: '100%', marginTop: 16, justifyContent: 'center' }}>
                                {running ? <><Loader size={14} className="spin" /> Converting…</> : <><Zap size={14} /> Convert to GGUF</>}
                            </button>
                        </div>
                    )}

                    {/* ═══ LORA MERGE ═══ */}
                    {activeTab === 'lora' && (
                        <div className="card">
                            <div className="card-header">
                                <h3 className="card-title"><GitMerge size={16} /> Merge LoRA Adapter</h3>
                            </div>
                            {!toolAvailable['llama-server'] && (
                                <div style={{
                                    padding: '8px 12px', borderRadius: 8, marginBottom: 12,
                                    background: 'rgba(255,184,0,0.08)', border: '1px solid rgba(255,184,0,0.2)',
                                    color: 'var(--accent-amber)', fontSize: 12,
                                    display: 'flex', alignItems: 'center', gap: 6,
                                }}>
                                    <AlertTriangle size={14} /> <strong>llama-export-lora</strong> tool may not be available. Check llama.cpp installation.
                                </div>
                            )}

                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                <div>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Base GGUF Model</label>
                                    <select className="form-select" style={{ width: '100%' }}
                                        value={loraBaseId} onChange={e => setLoraBaseId(e.target.value)}>
                                        <option value="">Select base model…</option>
                                        {ggufModels.map(m => (
                                            <option key={m.id} value={m.id}>{m.name} ({humanSize(m.file_size)})</option>
                                        ))}
                                    </select>
                                    {getModel(loraBaseId) && <ModelInfoMini model={getModel(loraBaseId)} />}
                                </div>
                                <div>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>LoRA Adapter Path</label>
                                    <div style={{ display: 'flex', gap: 8 }}>
                                        <input type="text" className="form-input" style={{ flex: 1 }}
                                            value={loraPath} onChange={e => setLoraPath(e.target.value)}
                                            placeholder="Path to LoRA adapter (.gguf or directory)" />
                                        <button className="btn btn-outline" onClick={() => { setBrowserTarget('lora'); setBrowserOpen(true); }}>
                                            Browse
                                        </button>
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: 12 }}>
                                    <div style={{ flex: 1 }}>
                                        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Output Name</label>
                                        <input type="text" className="form-input" style={{ width: '100%' }}
                                            value={loraOutputName} onChange={e => setLoraOutputName(e.target.value)}
                                            placeholder="Auto-generated" />
                                    </div>
                                    <div style={{ width: 100 }}>
                                        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Scale</label>
                                        <input type="number" className="form-input" style={{ width: '100%' }}
                                            value={loraScale} min={0} max={2} step={0.1}
                                            onChange={e => setLoraScale(parseFloat(e.target.value))} />
                                    </div>
                                </div>
                            </div>

                            <button onClick={handleMergeLora} disabled={running || !loraBaseId || !loraPath}
                                className="btn btn-primary" style={{ width: '100%', marginTop: 16, justifyContent: 'center' }}>
                                {running ? <><Loader size={14} className="spin" /> Merging…</> : <><GitMerge size={14} /> Merge LoRA</>}
                            </button>
                        </div>
                    )}

                    {/* ═══ SPLIT / JOIN ═══ */}
                    {activeTab === 'split' && (
                        <div className="card">
                            <div className="card-header">
                                <h3 className="card-title"><Scissors size={16} /> Split / Join GGUF</h3>
                            </div>
                            {!toolAvailable['llama-gguf-split'] && (
                                <div style={{
                                    padding: '8px 12px', borderRadius: 8, marginBottom: 12,
                                    background: 'rgba(255,184,0,0.08)', border: '1px solid rgba(255,184,0,0.2)',
                                    color: 'var(--accent-amber)', fontSize: 12,
                                    display: 'flex', alignItems: 'center', gap: 6,
                                }}>
                                    <AlertTriangle size={14} /> <strong>llama-gguf-split</strong> not found in PATH. Install llama.cpp tools.
                                </div>
                            )}

                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                <div>
                                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>GGUF Model to Split</label>
                                    <select className="form-select" style={{ width: '100%' }}
                                        value={splitModelId} onChange={e => setSplitModelId(e.target.value)}>
                                        <option value="">Select model…</option>
                                        {ggufModels.map(m => (
                                            <option key={m.id} value={m.id}>{m.name} ({humanSize(m.file_size)})</option>
                                        ))}
                                    </select>
                                    {getModel(splitModelId) && <ModelInfoMini model={getModel(splitModelId)} />}
                                </div>
                                <div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                        <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>Max Shard Size</label>
                                        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent-blue)' }}>{splitMaxSize} GB</span>
                                    </div>
                                    <input type="range" min={1} max={16} step={0.5} value={splitMaxSize}
                                        onChange={e => setSplitMaxSize(parseFloat(e.target.value))} style={{ width: '100%' }} />
                                </div>
                            </div>

                            <button onClick={handleSplit} disabled={running || !splitModelId}
                                className="btn btn-primary" style={{ width: '100%', marginTop: 16, justifyContent: 'center' }}>
                                {running ? <><Loader size={14} className="spin" /> Splitting…</> : <><Scissors size={14} /> Split Model</>}
                            </button>
                        </div>
                    )}
                </div>

                {/* Right: Results + Info */}
                <div>
                    {error && (
                        <div className="card" style={{ marginBottom: 16, borderColor: 'rgba(239,68,68,0.3)' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent-red)' }}>
                                <AlertCircle size={18} /> <strong>Error</strong>
                            </div>
                            <p style={{ marginTop: 8, fontSize: 13, color: 'var(--accent-red)' }}>{error}</p>
                        </div>
                    )}

                    {result ? (
                        <div className="card" style={{ marginBottom: 16 }}>
                            <div className="card-header" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <CheckCircle size={18} style={{ color: 'var(--accent-green)' }} />
                                <h3 className="card-title" style={{ color: 'var(--accent-green)' }}>
                                    {result.message || 'Operation Complete'}
                                </h3>
                            </div>
                            <pre style={{
                                fontSize: 11, fontFamily: 'var(--font-mono)', padding: 12,
                                background: 'var(--bg-input)', borderRadius: 'var(--radius-md)',
                                maxHeight: 400, overflowY: 'auto', whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                            }}>
                                {JSON.stringify(result, null, 2)}
                            </pre>
                        </div>
                    ) : (
                        <div className="card" style={{ marginBottom: 16 }}>
                            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>
                                <Cpu size={36} strokeWidth={1} />
                                <p style={{ marginTop: 8 }}>{TABS.find(t => t.id === activeTab)?.desc}</p>
                            </div>
                        </div>
                    )}

                    {/* Supported Architectures */}
                    <div className="card">
                        <div className="card-header">
                            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <Info size={16} /> Supported Architectures ({status?.supported_architectures?.length || 0})
                            </h3>
                        </div>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {(status?.supported_architectures || []).map(arch => (
                                <span key={arch} style={{
                                    padding: '2px 8px', borderRadius: 4, fontSize: 11,
                                    background: 'var(--bg-input)', color: 'var(--text-secondary)',
                                }}>
                                    {arch}
                                </span>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* Folder Browser Modal */}
            <FolderBrowser
                open={browserOpen}
                onClose={() => setBrowserOpen(false)}
                showFiles={browserTarget === 'inspect'} // Only show files for inspect, others target dirs
                onSelect={(path) => {
                    if (browserTarget === 'inspect') setInspectCustomPath(path);
                    else if (browserTarget === 'convert') setHfModelDir(path);
                    else if (browserTarget === 'lora') setLoraPath(path);
                }}
            />
        </div>
    );
}

function ModelInfoMini({ model }) {
    return (
        <div style={{
            marginTop: 6, padding: '6px 10px', borderRadius: 6,
            background: 'var(--bg-input)', fontSize: 11, color: 'var(--text-muted)',
            display: 'flex', gap: 12, flexWrap: 'wrap',
        }}>
            <span>{model.format?.toUpperCase()}</span>
            <span>{humanSize(model.file_size)}</span>
            <span style={{ fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>{model.file_path}</span>
        </div>
    );
}
