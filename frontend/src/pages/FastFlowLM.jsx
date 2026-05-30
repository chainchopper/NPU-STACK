import React, { useState, useEffect, useRef } from 'react';
import { 
    Cpu, 
    Server, 
    Download, 
    Play, 
    Square, 
    MessageSquare, 
    Zap, 
    ShieldCheck, 
    AlertCircle, 
    Database, 
    Search,
    RefreshCw,
    Info,
    ChevronDown,
    ChevronUp,
    CheckCircle2,
    XCircle,
    Activity,
    Trash2,
    Clock,
    BarChart3,
    Cloud
} from 'lucide-react';
import { 
    getFLMStatus, 
    listFLMModels, 
    pullFLMModel, 
    serveFLMModel, 
    stopFLMServer, 
    chatFLM,
    diagnoseBackendError
} from '../api/client';
import ActivityLogCard from '../components/ActivityLogCard';
import OperationNotice from '../components/OperationNotice';

export default function FastFlowLM() {
    const [status, setStatus] = useState({ installed: false, version: 'N/A', npu_ready: false, server: { running: false } });
    const [models, setModels] = useState([]);
    const [catalog, setCatalog] = useState([]);
    const [loading, setLoading] = useState(true);
    const [pullingModel, setPullingModel] = useState(null);
    const [pullProgress, setPullProgress] = useState(0);
    const [servingModel, setServingModel] = useState(null);
    const [chatMessages, setChatMessages] = useState([]);
    const [inputMessage, setInputMessage] = useState('');
    const [isTyping, setIsTyping] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [activeTab, setActiveTab] = useState('library'); // 'library' or 'chat'
    const [notice, setNotice] = useState(null);
    const [activityLog, setActivityLog] = useState([]);
    const chatEndRef = useRef(null);

    const addLog = (line) => {
        const timestamp = new Date().toLocaleTimeString();
        setActivityLog((prev) => [...prev.slice(-59), `${timestamp} — ${line}`]);
    };

    useEffect(() => {
        refreshData();
        const interval = setInterval(refreshStatus, 5000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (chatEndRef.current) {
            chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [chatMessages]);

    const refreshData = async () => {
        setLoading(true);
        try {
            const [s, mData] = await Promise.all([
                getFLMStatus(),
                listFLMModels()
            ]);
            setStatus(s);
            setModels(mData.local);
            setCatalog(mData.catalog);
            if (s.server?.running) {
                setServingModel(s.server.model);
            }
        } catch (err) {
            const message = diagnoseBackendError(err, 'FastFlowLM data refresh');
            setNotice({ tone: 'warning', title: 'FastFlowLM data unavailable', message, details: err?.message || null });
            addLog(`Initial data refresh failed: ${message}`);
        } finally {
            setLoading(false);
        }
    };

    const refreshStatus = async () => {
        try {
            const s = await getFLMStatus();
            setStatus(s);
            if (s.server?.running) {
                setServingModel(s.server.model);
            } else {
                setServingModel(null);
            }
        } catch (err) {
            addLog(`Status refresh skipped: ${diagnoseBackendError(err, 'FastFlowLM status')}`);
        }
    };

    const handlePull = async (tag) => {
        if (pullingModel) return;
        setPullingModel(tag);
        setPullProgress(0);
        setNotice(null);
        addLog(`Pull requested for ${tag}`);
        try {
            await pullFLMModel(tag, (progress) => {
                if (progress.status === 'downloading') {
                    setPullProgress(progress.progress || 0);
                } else if (progress.status === 'completed') {
                    setPullProgress(100);
                    setNotice({ tone: 'success', title: 'Model pulled', message: `${tag} is now available in local library.` });
                    addLog(`Pull complete: ${tag}`);
                    setTimeout(() => {
                        setPullingModel(null);
                        refreshData();
                    }, 1000);
                }
            });
        } catch (err) {
            const message = diagnoseBackendError(err, 'Model pull');
            setNotice({ tone: 'danger', title: 'Failed to pull model', message, details: err?.message || null });
            addLog(`Pull failed for ${tag}: ${message}`);
            setPullingModel(null);
        }
    };

    const handleServe = async (model) => {
        setLoading(true);
        setNotice(null);
        addLog(`Serve requested for ${model}`);
        try {
            await serveFLMModel(model);
            await refreshStatus();
            setActiveTab('chat');
            setNotice({ tone: 'success', title: 'Server started', message: `${model} is serving in NPU workspace.` });
            addLog(`Serve active: ${model}`);
        } catch (err) {
            const message = diagnoseBackendError(err, 'Server start');
            setNotice({ tone: 'danger', title: 'Failed to start server', message, details: err?.message || null });
            addLog(`Serve failed for ${model}: ${message}`);
        } finally {
            setLoading(false);
        }
    };

    const handleStop = async () => {
        setLoading(true);
        setNotice(null);
        addLog('Server stop requested');
        try {
            await stopFLMServer();
            await refreshStatus();
            setNotice({ tone: 'success', title: 'Server stopped', message: 'FastFlowLM server is now idle.' });
            addLog('Server stopped');
        } catch (err) {
            const message = diagnoseBackendError(err, 'Server stop');
            setNotice({ tone: 'danger', title: 'Failed to stop server', message, details: err?.message || null });
            addLog(`Stop failed: ${message}`);
        } finally {
            setLoading(false);
        }
    };

    const handleSendMessage = async () => {
        if (!inputMessage.trim() || !status.server?.running) return;

        const userMsg = { role: 'user', content: inputMessage };
        const assistantMsg = { role: 'assistant', content: '' };
        
        setChatMessages(prev => [...prev, userMsg, assistantMsg]);
        setInputMessage('');
        setIsTyping(true);
        addLog('Chat message sent');

        try {
            await chatFLM([...chatMessages, userMsg], status.server.model, 0.7, 1024, (delta) => {
                setChatMessages(prev => {
                    const last = prev[prev.length - 1];
                    const updated = { ...last, content: last.content + delta };
                    return [...prev.slice(0, -1), updated];
                });
            });
        } catch (err) {
            const message = diagnoseBackendError(err, 'Chat stream');
            setNotice({ tone: 'warning', title: 'Chat stream interrupted', message, details: err?.message || null });
            addLog(`Chat error: ${message}`);
            setChatMessages(prev => [
                ...prev.slice(0, -1), 
                { role: 'assistant', content: `Error: ${err.message}` }
            ]);
        } finally {
            setIsTyping(false);
        }
    };

    const filteredCatalog = catalog.filter(m => 
        (m.name || '').toLowerCase().includes(searchQuery.toLowerCase()) || 
        (m.family || '').toLowerCase().includes(searchQuery.toLowerCase())
    );

    const isInstalled = (tag) => models.some(m => m.tag === tag);

    if (loading && !models.length) {
        return (
            <div className="flex flex-col items-center justify-center h-full bg-slate-950 text-white">
                <RefreshCw className="w-12 h-12 animate-spin text-blue-500 mb-4" />
                <h2 className="text-xl font-medium">Initializing FastFlowLM...</h2>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full bg-slate-950 text-slate-200 overflow-hidden font-sans">
            {/* Header / Status Bar */}
            <div className="flex items-center justify-between px-6 py-4 bg-slate-900/50 border-b border-slate-800 backdrop-blur-md sticky top-0 z-20">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-lg shadow-lg shadow-blue-900/20">
                        <Zap className="w-6 h-6 text-white" />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-400">
                            FastFlowLM Integration
                        </h1>
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                            <span>v{status.version}</span>
                            <span className="w-1 h-1 bg-slate-700 rounded-full" />
                            <span className={status.installed ? 'text-emerald-400' : 'text-rose-400'}>
                                {status.installed ? 'Runtime Detected' : 'Runtime Missing'}
                            </span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${status.npu_ready ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-slate-800 border-slate-700 text-slate-500'}`}>
                        <Cpu className="w-4 h-4" />
                        <span className="text-xs font-semibold">NPU: {status.npu_ready ? 'READY' : 'WAITING'}</span>
                    </div>
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${status.server?.running ? 'bg-blue-500/10 border-blue-500/30 text-blue-400' : 'bg-slate-800 border-slate-700 text-slate-500'}`}>
                        <Server className="w-4 h-4" />
                        <span className="text-xs font-semibold">SERVER: {status.server?.running ? 'ACTIVE' : 'IDLE'}</span>
                    </div>
                    {status.server?.running && (
                        <button 
                            onClick={handleStop}
                            className="p-1.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 rounded-lg border border-rose-500/30 transition-colors"
                            title="Stop Server"
                        >
                            <Square className="w-4 h-4 fill-current" />
                        </button>
                    )}
                </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex px-6 border-b border-slate-800 bg-slate-900/30">
                <button 
                    onClick={() => setActiveTab('library')}
                    className={`px-6 py-3 text-sm font-medium border-b-2 transition-all ${activeTab === 'library' ? 'border-blue-500 text-blue-400 bg-blue-500/5' : 'border-transparent text-slate-500 hover:text-slate-300'}`}
                >
                    <div className="flex items-center gap-2">
                        <Database className="w-4 h-4" />
                        Model Library
                    </div>
                </button>
                <button 
                    onClick={() => setActiveTab('chat')}
                    className={`px-6 py-3 text-sm font-medium border-b-2 transition-all ${activeTab === 'chat' ? 'border-blue-500 text-blue-400 bg-blue-500/5' : 'border-transparent text-slate-500 hover:text-slate-300'}`}
                >
                    <div className="flex items-center gap-2">
                        <MessageSquare className="w-4 h-4" />
                        NPU Workspace
                        {status.server?.running && <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />}
                    </div>
                </button>
            </div>

            <div style={{ padding: '12px 24px 0 24px' }}>
                <OperationNotice
                    tone={notice?.tone || 'info'}
                    title={notice?.title}
                    message={notice?.message}
                    details={notice?.details}
                    style={{ marginBottom: 0 }}
                />
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-auto bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-slate-950">
                {activeTab === 'library' ? (
                    <div className="p-8 max-w-7xl mx-auto space-y-8">
                        {/* Search & Stats */}
                        <div className="flex flex-col md:flex-row gap-6 items-center justify-between">
                            <div className="relative w-full md:w-96">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                                <input 
                                    type="text" 
                                    placeholder="Search FastFlowLM models..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all"
                                />
                            </div>
                            <div className="flex gap-4">
                                <div className="px-4 py-2 bg-slate-900/50 border border-slate-800 rounded-xl">
                                    <span className="text-xs text-slate-500 block">LOCAL MODELS</span>
                                    <span className="text-lg font-bold">{models.length}</span>
                                </div>
                                <div className="px-4 py-2 bg-slate-900/50 border border-slate-800 rounded-xl">
                                    <span className="text-xs text-slate-500 block">CATALOG SIZE</span>
                                    <span className="text-lg font-bold text-blue-400">{catalog.length}</span>
                                </div>
                            </div>
                        </div>

                        {/* Local Models Grid */}
                        {models.length > 0 && (
                            <section>
                                <div className="flex items-center gap-2 mb-4">
                                    <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                                    <h2 className="text-lg font-semibold">Installed Models</h2>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                    {models.map(model => (
                                        <div key={model.tag} className={`group relative bg-slate-900/40 border border-slate-800 rounded-2xl p-5 hover:border-blue-500/50 hover:bg-slate-900/60 transition-all duration-300 ${servingModel === model.tag ? 'ring-2 ring-blue-500/50 bg-blue-500/5 border-blue-500/50' : ''}`}>
                                            <div className="flex items-start justify-between mb-4">
                                                <div className="p-2.5 bg-slate-800 rounded-xl group-hover:bg-blue-500/20 group-hover:text-blue-400 transition-colors">
                                                    <Cpu className="w-6 h-6" />
                                                </div>
                                                <div className="text-right">
                                                    <span className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">Local Copy</span>
                                                    <div className="text-xs font-mono text-slate-400">{model.size}</div>
                                                </div>
                                            </div>
                                            <h3 className="text-lg font-bold mb-1 truncate">{model.name}</h3>
                                            <p className="text-xs text-slate-500 mb-4 font-mono">{model.tag}</p>
                                            
                                            <div className="flex items-center gap-2 mt-4">
                                                {servingModel === model.tag ? (
                                                    <button 
                                                        disabled
                                                        className="flex-1 flex items-center justify-center gap-2 py-2 bg-blue-500 text-white rounded-lg text-sm font-bold shadow-lg shadow-blue-900/20"
                                                    >
                                                        <Activity className="w-4 h-4 animate-pulse" />
                                                        Serving...
                                                    </button>
                                                ) : (
                                                    <button 
                                                        onClick={() => handleServe(model.tag)}
                                                        className="flex-1 flex items-center justify-center gap-2 py-2 bg-slate-800 hover:bg-blue-600 text-white rounded-lg text-sm font-bold transition-all"
                                                    >
                                                        <Play className="w-4 h-4 fill-current" />
                                                        Deploy to NPU
                                                    </button>
                                                )}
                                                <button className="p-2 bg-slate-800 hover:bg-rose-500/20 hover:text-rose-400 text-slate-500 rounded-lg border border-transparent hover:border-rose-500/30 transition-all">
                                                    <Trash2 className="w-5 h-5" />
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </section>
                        )}

                        {/* Catalog Grid */}
                        <section>
                            <div className="flex items-center gap-2 mb-4">
                                <Cloud className="w-5 h-5 text-blue-500" />
                                <h2 className="text-lg font-semibold">Cloud Catalog</h2>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                {filteredCatalog.filter(m => !isInstalled(m.tag)).map(model => (
                                    <div key={model.tag} className="group relative bg-slate-900/40 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition-all">
                                        <div className="flex items-start justify-between mb-4">
                                            <div className="p-2.5 bg-slate-800/50 rounded-xl group-hover:bg-slate-800 transition-colors">
                                                <Zap className="w-6 h-6 text-slate-500 group-hover:text-blue-400" />
                                            </div>
                                            <div className="text-right">
                                                <span className="px-2 py-0.5 bg-slate-800 rounded-full text-[10px] font-bold text-slate-400 uppercase tracking-tight">
                                                    {model.family}
                                                </span>
                                                <div className="text-xs mt-1 text-slate-500">{model.size || 'Auto-Scale'}</div>
                                            </div>
                                        </div>
                                        <h3 className="text-md font-bold mb-1 group-hover:text-blue-300 transition-colors">{model.name}</h3>
                                        <div className="flex items-center gap-2 text-[10px] text-slate-500 mb-6 uppercase tracking-wider">
                                            <BarChart3 className="w-3 h-3" />
                                            <span>Context: {model.context || '128k'}</span>
                                        </div>
                                        
                                        {pullingModel === model.tag ? (
                                            <div className="space-y-2">
                                                <div className="flex justify-between text-[10px] font-bold text-blue-400">
                                                    <span>DOWNLOADING...</span>
                                                    <span>{pullProgress}%</span>
                                                </div>
                                                <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                                                    <div className="h-full bg-blue-500 transition-all duration-300" style={{ width: `${pullProgress}%` }} />
                                                </div>
                                            </div>
                                        ) : (
                                            <button 
                                                onClick={() => handlePull(model.tag)}
                                                className="w-full flex items-center justify-center gap-2 py-2 bg-slate-800/50 hover:bg-slate-800 text-slate-200 border border-slate-700 hover:border-slate-600 rounded-lg text-sm font-bold transition-all"
                                            >
                                                <Download className="w-4 h-4" />
                                                Pull to Device
                                            </button>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </section>

                        <ActivityLogCard
                            title="FastFlowLM Activity"
                            lines={activityLog}
                            emptyMessage="No FastFlowLM activity recorded yet."
                            onClear={() => setActivityLog([])}
                        />
                    </div>
                ) : (
                    <div className="flex flex-col h-full bg-slate-950">
                        {/* Chat Messages */}
                        <div className="flex-1 overflow-y-auto p-6 space-y-6">
                            {!status.server?.running ? (
                                <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
                                    <div className="p-6 bg-slate-900 rounded-3xl border border-slate-800 shadow-2xl mb-6">
                                        <AlertCircle className="w-12 h-12 text-blue-400 mb-4 mx-auto" />
                                        <h3 className="text-xl font-bold mb-2">Workspace Inactive</h3>
                                        <p className="text-sm text-slate-500">
                                            Select a model from your library and click "Deploy to NPU" to start chatting with high-context acceleration.
                                        </p>
                                    </div>
                                    <button 
                                        onClick={() => setActiveTab('library')}
                                        className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl transition-all shadow-lg shadow-blue-900/40"
                                    >
                                        Open Model Library
                                    </button>
                                </div>
                            ) : (
                                <>
                                    <div className="flex items-center justify-center">
                                        <div className="px-4 py-1.5 bg-blue-500/10 border border-blue-500/20 rounded-full text-[10px] text-blue-400 font-bold uppercase tracking-widest flex items-center gap-2">
                                            <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
                                            Connection Established • {status.server.model}
                                        </div>
                                    </div>
                                    
                                    {chatMessages.length === 0 && (
                                        <div className="flex flex-col items-center text-center py-20">
                                            <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl mb-4">
                                                <Zap className="w-8 h-8 text-blue-500" />
                                            </div>
                                            <h2 className="text-2xl font-bold mb-2">Welcome to NPU Space</h2>
                                            <p className="text-slate-500 max-w-sm">
                                                You're running <strong>{status.server.model}</strong> directly on your AMD Ryzen AI NPU.
                                                Ask me anything — I'm running locally and securely.
                                            </p>
                                        </div>
                                    )}

                                    {chatMessages.map((msg, idx) => (
                                        <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                            <div className={`max-w-[80%] rounded-2xl px-5 py-3.5 shadow-lg ${
                                                msg.role === 'user' 
                                                ? 'bg-blue-600 text-white rounded-tr-none' 
                                                : 'bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none'
                                            }`}>
                                                <div className="text-[10px] font-black uppercase tracking-tighter opacity-50 mb-1">
                                                    {msg.role}
                                                </div>
                                                <div className="text-sm leading-relaxed whitespace-pre-wrap font-medium">
                                                    {msg.content}
                                                    {isTyping && idx === chatMessages.length - 1 && (
                                                        <span className="inline-block w-1.5 h-4 ml-1 bg-blue-400 animate-pulse align-middle" />
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                    <div ref={chatEndRef} />
                                </>
                            )}
                        </div>

                        {/* Input Area */}
                        <div className="p-6 bg-slate-950 border-t border-slate-900">
                            <div className="max-w-4xl mx-auto relative">
                                <textarea 
                                    rows="1"
                                    disabled={!status.server?.running}
                                    placeholder={status.server?.running ? "Type a message..." : "Server inactive — deploy a model first"}
                                    value={inputMessage}
                                    onChange={(e) => setInputMessage(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' && !e.shiftKey) {
                                            e.preventDefault();
                                            handleSendMessage();
                                        }
                                    }}
                                    className="w-full bg-slate-900 border border-slate-800 rounded-2xl px-6 py-4 pr-16 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 resize-none transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                                />
                                <button 
                                    onClick={handleSendMessage}
                                    disabled={!inputMessage.trim() || !status.server?.running || isTyping}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 p-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 text-white rounded-xl transition-all shadow-lg"
                                >
                                    <Zap className={`w-5 h-5 ${isTyping ? 'animate-pulse' : ''}`} />
                                </button>
                            </div>
                            <div className="mt-4 flex flex-wrap justify-center gap-6 text-[10px] text-slate-600 font-bold uppercase tracking-widest">
                                <div className="flex items-center gap-1.5"><ShieldCheck className="w-3 h-3" /> Privacy Guaranteed</div>
                                <div className="flex items-center gap-1.5"><Cpu className="w-3 h-3" /> NPU Optimized</div>
                                <div className="flex items-center gap-1.5"><Clock className="w-3 h-3" /> Real-time Streaming</div>
                            </div>
                            <ActivityLogCard
                                title="FastFlowLM Activity"
                                lines={activityLog}
                                emptyMessage="No FastFlowLM activity recorded yet."
                                onClear={() => setActivityLog([])}
                                style={{ marginTop: 12 }}
                            />
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
