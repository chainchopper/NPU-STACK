import { useState, useEffect } from 'react';
import { Server, Play, Square, Loader, Copy, Terminal, Zap } from 'lucide-react';
import ActivityLogCard from '../components/ActivityLogCard';
import OperationNotice from '../components/OperationNotice';
import { OPENAI_BASE, openAIUrl, absoluteUrl, diagnoseBackendError } from '../api/client';

export default function Serving() {
    const [models, setModels] = useState([]);
    const [modelFilter, setModelFilter] = useState('all');
    const [loadedModels, setLoadedModels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadingModel, setLoadingModel] = useState(null);
    const [chatModel, setChatModel] = useState('');
    const [chatMessages, setChatMessages] = useState([]);
    const [chatInput, setChatInput] = useState('');
    const [chatLoading, setChatLoading] = useState(false);
    const [copied, setCopied] = useState(null);
    const [notice, setNotice] = useState(null);
    const [activityLog, setActivityLog] = useState([]);

    const openAIBaseUrl = absoluteUrl(OPENAI_BASE);
    const chatCompletionsUrl = absoluteUrl(openAIUrl('/chat/completions'));

    const addLog = (line) => {
        const timestamp = new Date().toLocaleTimeString();
        setActivityLog((prev) => [...prev.slice(-59), `${timestamp} — ${line}`]);
    };

    const fetchModels = async () => {
        try {
            const res = await fetch(openAIUrl('/models'));
            const data = await res.json();
            setModels(data.data || []);
        } catch (e) {
            setNotice({
                tone: 'warning',
                title: 'Model registry unavailable',
                message: diagnoseBackendError(e, 'Serving models list'),
                details: e?.message || null,
            });
            addLog(`Model registry unavailable: ${diagnoseBackendError(e, 'Serving models list')}`);
        }
    };

    const fetchStatus = async () => {
        try {
            const res = await fetch(openAIUrl('/models/status'));
            const data = await res.json();
            setLoadedModels(data.models || []);
            if (data.models?.length > 0 && !chatModel) {
                setChatModel(data.models[0].name);
            }
        } catch (e) {
            setNotice({
                tone: 'warning',
                title: 'Serving status unavailable',
                message: diagnoseBackendError(e, 'Serving status'),
                details: e?.message || null,
            });
            addLog(`Serving status unavailable: ${diagnoseBackendError(e, 'Serving status')}`);
        }
    };

    useEffect(() => {
        Promise.all([fetchModels(), fetchStatus()]).finally(() => setLoading(false));
        const interval = setInterval(fetchStatus, 5000);
        return () => clearInterval(interval);
    }, []);

    const loadModel = async (name) => {
        setLoadingModel(name);
        addLog(`Load requested for model ${name}`);
        try {
            await fetch(openAIUrl('/models/load'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name }),
            });
            await fetchStatus();
            setChatModel(name);
            setNotice({ tone: 'success', title: 'Model loaded', message: `${name} is now active.` });
            addLog(`Model loaded: ${name}`);
        } catch (e) {
            setNotice({
                tone: 'danger',
                title: 'Load failed',
                message: diagnoseBackendError(e, 'Model load'),
                details: e?.message || null,
            });
            addLog(`Load failed for ${name}: ${diagnoseBackendError(e, 'Model load')}`);
        }
        setLoadingModel(null);
    };

    const unloadModel = async (name) => {
        addLog(`Unload requested for model ${name}`);
        try {
            await fetch(openAIUrl('/models/unload'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name }),
            });
            await fetchStatus();
            setNotice({ tone: 'info', title: 'Model unloaded', message: `${name} was removed from active serving.` });
            addLog(`Model unloaded: ${name}`);
        } catch (e) {
            setNotice({
                tone: 'danger',
                title: 'Unload failed',
                message: diagnoseBackendError(e, 'Model unload'),
                details: e?.message || null,
            });
            addLog(`Unload failed for ${name}: ${diagnoseBackendError(e, 'Model unload')}`);
        }
    };

    const sendChat = async () => {
        if (!chatInput.trim() || !chatModel) return;

        const userMsg = { role: 'user', content: chatInput };
        const newMsgs = [...chatMessages, userMsg];
        setChatMessages(newMsgs);
        setChatInput('');
        setChatLoading(true);
        addLog(`Chat message sent using ${chatModel}`);

        try {
            const res = await fetch(openAIUrl('/chat/completions'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: chatModel,
                    messages: newMsgs.map((m) => ({ role: m.role, content: m.content })),
                    max_tokens: 256,
                    temperature: 0.7,
                }),
            });
            const data = await res.json();
            if (data.choices?.[0]?.message) {
                setChatMessages([...newMsgs, data.choices[0].message]);
                addLog(`Chat response received from ${chatModel}`);
            } else if (data.detail) {
                setChatMessages([...newMsgs, { role: 'system', content: `Error: ${data.detail}` }]);
                addLog(`Chat returned error: ${data.detail}`);
            }
        } catch (e) {
            setChatMessages([...newMsgs, { role: 'system', content: `Error: ${e.message}` }]);
            addLog(`Chat failed: ${e.message}`);
        }

        setChatLoading(false);
    };

    const copySnippet = (lang) => {
        const snippets = {
            python: `from openai import OpenAI

client = OpenAI(
    base_url="${openAIBaseUrl}",
    api_key="any"  # Not required for local
)

response = client.chat.completions.create(
    model="${chatModel || 'your-model-name'}",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)`,
            javascript: `const response = await fetch("${chatCompletionsUrl}", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "${chatModel || 'your-model-name'}",
    messages: [{ role: "user", content: "Hello!" }]
  })
});
const data = await response.json();
console.log(data.choices[0].message.content);`,
            curl: `curl ${chatCompletionsUrl} \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${chatModel || 'your-model-name'}",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`,
        };

        navigator.clipboard.writeText(snippets[lang]);
        setCopied(lang);
        addLog(`Copied ${lang} API snippet`);
        setTimeout(() => setCopied(null), 2000);
    };

    const loadedNames = new Set(loadedModels.map((m) => m.name));

    return (
        <div>
            <div className="section-header">
                <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <Server size={24} /> Model Serving
                </h2>
                <p className="text-secondary">
                    OpenAI-compatible API at{' '}
                    <code style={{ background: 'var(--bg-input)', padding: '2px 8px', borderRadius: '6px', fontSize: '13px' }}>
                        {openAIBaseUrl}
                    </code>
                </p>
            </div>

            <OperationNotice
                tone={notice?.tone || 'info'}
                title={notice?.title}
                message={notice?.message}
                details={notice?.details}
            />

            <div className="card mb-4">
                <div className="card-header">
                    <h3 className="card-title">
                        <Zap size={16} style={{ color: 'var(--accent-green)' }} /> Active Models ({loadedModels.length})
                    </h3>
                </div>
                {loadedModels.length === 0 ? (
                    <p className="text-secondary" style={{ padding: '16px 0' }}>
                        No models loaded. Load a model below to start serving.
                    </p>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {loadedModels.map((m, index) => (
                            <div
                                key={`loaded-${m.name}-${index}`}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '12px',
                                    padding: '12px 16px',
                                    background: 'var(--bg-input)',
                                    borderRadius: 'var(--radius-md)',
                                    border: '1px solid rgba(16,185,129,0.2)',
                                }}
                            >
                                <span
                                    style={{
                                        width: '8px',
                                        height: '8px',
                                        borderRadius: '50%',
                                        background: 'var(--accent-green)',
                                        flexShrink: 0,
                                    }}
                                />
                                <span style={{ fontWeight: 600, flex: 1 }}>{m.name}</span>
                                <span className="badge">{m.type}</span>
                                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                                    {Math.round(m.uptime_seconds)}s uptime
                                </span>
                                <button className="btn btn-sm btn-danger" onClick={() => unloadModel(m.name)}>
                                    <Square size={12} /> Unload
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="grid-2">
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Model Registry</h3>
                        <select
                            value={modelFilter}
                            onChange={(e) => setModelFilter(e.target.value)}
                            className="form-select"
                            style={{ width: 'auto', fontSize: '12px', padding: '4px 24px 4px 8px', minHeight: '28px' }}
                        >
                            <option value="all">All Formats</option>
                            <option value="gguf">GGUF</option>
                            <option value="onnx">ONNX</option>
                            <option value="pytorch">PyTorch</option>
                            <option value="openvino">OpenVINO</option>
                            <option value="safetensors">SafeTensors</option>
                        </select>
                    </div>
                    {loading ? (
                        <div className="loading"><Loader className="spin" size={20} /> Loading models...</div>
                    ) : models.length === 0 ? (
                        <p className="text-secondary">No models registered. Upload or download a model first.</p>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '400px', overflowY: 'auto' }}>
                            {models.filter((m) => modelFilter === 'all' || m.framework?.toLowerCase() === modelFilter || m.format?.toLowerCase() === modelFilter).length === 0 ? (
                                <p className="text-secondary" style={{ textAlign: 'center', padding: '20px 0', fontSize: '13px' }}>
                                    No models match the selected filter.
                                </p>
                            ) : models
                                .filter((m) => modelFilter === 'all' || m.framework?.toLowerCase() === modelFilter || m.format?.toLowerCase() === modelFilter)
                                .map((m, index) => (
                                    <div
                                        key={`model-${m.id}-${index}`}
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '10px',
                                            padding: '10px 14px',
                                            background: 'var(--bg-input)',
                                            borderRadius: 'var(--radius-md)',
                                        }}
                                    >
                                        <span style={{ flex: 1, fontWeight: 500, fontSize: '14px' }}>{m.id}</span>
                                        {loadedNames.has(m.id) ? (
                                            <span className="badge badge-green">Loaded</span>
                                        ) : (
                                            <button className="btn btn-sm btn-primary" onClick={() => loadModel(m.id)} disabled={loadingModel === m.id}>
                                                {loadingModel === m.id ? <Loader size={12} className="spin" /> : <Play size={12} />} Load
                                            </button>
                                        )}
                                    </div>
                                ))}
                        </div>
                    )}
                </div>

                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Chat Test</h3>
                        {loadedModels.length > 0 && (
                            <select value={chatModel} onChange={(e) => setChatModel(e.target.value)} className="form-select" style={{ width: 'auto', fontSize: '12px' }}>
                                {loadedModels.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
                            </select>
                        )}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minHeight: '200px', maxHeight: '350px', overflowY: 'auto', marginBottom: '12px' }}>
                        {chatMessages.length === 0 && (
                            <p className="text-secondary" style={{ textAlign: 'center', marginTop: '40px' }}>
                                Load a model and start chatting
                            </p>
                        )}
                        {chatMessages.map((msg, i) => (
                            <div
                                key={i}
                                style={{
                                    padding: '10px 14px',
                                    borderRadius: 'var(--radius-md)',
                                    background: msg.role === 'user'
                                        ? 'rgba(59,130,246,0.1)'
                                        : msg.role === 'system'
                                            ? 'rgba(239,68,68,0.1)'
                                            : 'var(--bg-input)',
                                    borderLeft: `3px solid ${msg.role === 'user' ? 'var(--accent-blue)' : msg.role === 'system' ? 'var(--accent-red)' : 'var(--accent-green)'}`,
                                }}
                            >
                                <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px', display: 'block' }}>
                                    {msg.role}
                                </span>
                                <span style={{ fontSize: '14px', whiteSpace: 'pre-wrap' }}>{msg.content}</span>
                            </div>
                        ))}
                        {chatLoading && <div className="loading"><Loader className="spin" size={16} /> Generating...</div>}
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <input
                            type="text"
                            value={chatInput}
                            onChange={(e) => setChatInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && sendChat()}
                            placeholder={loadedModels.length ? 'Type a message...' : 'Load a model first...'}
                            disabled={!loadedModels.length || chatLoading}
                            className="form-input"
                            style={{ flex: 1 }}
                        />
                        <button className="btn btn-primary" onClick={sendChat} disabled={!loadedModels.length || chatLoading || !chatInput.trim()}>
                            Send
                        </button>
                    </div>
                </div>
            </div>

            <div className="card mt-4">
                <div className="card-header">
                    <h3 className="card-title"><Terminal size={16} /> API Usage</h3>
                </div>
                <p className="text-secondary" style={{ marginBottom: '16px', fontSize: '13px' }}>
                    Use NPU-STACK as a drop-in replacement for OpenAI. Works with any client library.
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '12px' }}>
                    {['python', 'javascript', 'curl'].map((lang) => (
                        <div key={lang} style={{ position: 'relative' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 14px', background: 'rgba(0,0,0,0.3)', borderRadius: '10px 10px 0 0', borderBottom: '1px solid var(--border)' }}>
                                <span style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)' }}>{lang}</span>
                                <button
                                    onClick={() => copySnippet(lang)}
                                    style={{
                                        background: 'none',
                                        border: 'none',
                                        color: copied === lang ? 'var(--accent-green)' : 'var(--text-muted)',
                                        cursor: 'pointer',
                                        fontSize: '12px',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '4px',
                                    }}
                                >
                                    <Copy size={12} /> {copied === lang ? 'Copied!' : 'Copy'}
                                </button>
                            </div>
                            <pre style={{ margin: 0, padding: '14px', background: 'var(--bg-input)', borderRadius: '0 0 10px 10px', fontSize: '12px', fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', overflowX: 'auto', lineHeight: 1.5, color: 'var(--accent-green)' }}>
                                {lang === 'python' && `from openai import OpenAI\n\nclient = OpenAI(\n    base_url="${openAIBaseUrl}",\n    api_key="any"\n)\n\nresponse = client.chat.completions.create(\n    model="${chatModel || 'your-model'}",\n    messages=[{"role": "user", "content": "Hello!"}]\n)\nprint(response.choices[0].message.content)`}
                                {lang === 'javascript' && `const res = await fetch(\n  "${chatCompletionsUrl}",\n  {\n    method: "POST",\n    headers: {"Content-Type": "application/json"},\n    body: JSON.stringify({\n      model: "${chatModel || 'your-model'}",\n      messages: [{role: "user", content: "Hello!"}]\n    })\n  }\n);\nconst data = await res.json();\nconsole.log(data.choices[0].message.content);`}
                                {lang === 'curl' && `curl ${chatCompletionsUrl} \\\n  -H "Content-Type: application/json" \\
  -d '{\n    "model": "${chatModel || 'your-model'}",\n    "messages": [{"role":"user","content":"Hello!"}]\n  }'`}
                            </pre>
                        </div>
                    ))}
                </div>
            </div>

            <ActivityLogCard
                title="Serving Activity"
                lines={activityLog}
                emptyMessage="No serving activity recorded yet."
                onClear={() => setActivityLog([])}
                style={{ marginTop: 16 }}
            />
        </div>
    );
}
