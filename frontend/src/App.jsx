import React, { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Box, GraduationCap, ArrowRightLeft, Gauge, Menu, X, Globe, Database, Server, Wrench, FolderSearch, Camera, Upload, Cpu, CloudUpload, Zap, MonitorSmartphone, Radio, FlaskConical, Sun, Moon, Microscope, Bot, Sparkles } from 'lucide-react';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import { API_BASE } from './api/client';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Models = lazy(() => import('./pages/Models'));
const Training = lazy(() => import('./pages/Training'));
const AdvancedTraining = lazy(() => import('./pages/AdvancedTraining'));
const Conversion = lazy(() => import('./pages/Conversion'));
const Benchmark = lazy(() => import('./pages/Benchmark'));
const Playground = lazy(() => import('./pages/Playground'));
const Chat = lazy(() => import('./pages/Chat'));
const ChatPlayground = lazy(() => import('./pages/ChatPlayground'));
const Orchestration = lazy(() => import('./pages/Orchestration'));
const AutoResearch = lazy(() => import('./pages/AutoResearch'));
const ModelHub = lazy(() => import('./pages/ModelHub'));
const Datasets = lazy(() => import('./pages/Datasets'));
const Serving = lazy(() => import('./pages/Serving'));
const FineTuning = lazy(() => import('./pages/FineTuning'));
const Scanner = lazy(() => import('./pages/Scanner'));
const WebcamTest = lazy(() => import('./pages/WebcamTest'));
const DataIngestion = lazy(() => import('./pages/DataIngestion'));
const GGUFStudio = lazy(() => import('./pages/GGUFStudio'));
const HubPublisher = lazy(() => import('./pages/HubPublisher'));
const FastFlowLM = lazy(() => import('./pages/FastFlowLM'));
const EdgeFleet = lazy(() => import('./pages/EdgeFleet'));
const FleetCommand = lazy(() => import('./pages/FleetCommand'));

const navItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/chat-playground', icon: FlaskConical, label: 'Chat & Playground' },
    { path: '/orchestration', icon: Microscope, label: 'Orchestration' },
    { path: '/models', icon: Box, label: 'Models' },
    { path: '/hub', icon: Globe, label: 'Model Hub' },
    { path: '/hf-publisher', icon: CloudUpload, label: 'HF Publisher' },
    { path: '/datasets', icon: Database, label: 'Datasets' },
    { path: '/ingestion', icon: Upload, label: 'Data Ingestion' },
    { path: '/serving', icon: Server, label: 'Serving' },
    { path: '/training', icon: GraduationCap, label: 'Training' },
    { path: '/advanced-training', icon: Zap, label: 'Advanced Training' },
    { path: '/finetuning', icon: Wrench, label: 'Fine-Tuning' },
    { path: '/gguf-studio', icon: Cpu, label: 'GGUF Studio' },
    { path: '/fastflowlm', icon: Zap, label: 'FastFlowLM' },
    { path: '/conversion', icon: ArrowRightLeft, label: 'Conversion' },
    { path: '/scanner', icon: FolderSearch, label: 'Scanner' },
    { path: '/webcam', icon: Camera, label: 'Webcam' },
    { path: '/benchmark', icon: Gauge, label: 'Benchmark' },
    { path: '/edge-fleet', icon: MonitorSmartphone, label: 'Edge Fleet' },
    { path: '/fleet-command', icon: Radio, label: 'Fleet Command' },
];

function RouteLoadingFallback() {
    return (
        <div className="loading-overlay">
            <div className="spinner" />
            <span>Loading page...</span>
        </div>
    );
}

function AssistantLauncher() {
    const navigate = useNavigate();
    const [open, setOpen] = useState(false);
    const [initializing, setInitializing] = useState(false);
    const [starting, setStarting] = useState(false);
    const [notice, setNotice] = useState('');
    const [agentStatus, setAgentStatus] = useState(null);
    const [chatMessages, setChatMessages] = useState([]);
    const [chatInput, setChatInput] = useState('');
    const [chatLoading, setChatLoading] = useState(false);

    const refreshStatus = async () => {
        try {
            const res = await fetch(`${API_BASE}/agent/status`);
            const data = await res.json();
            setAgentStatus(data);
        } catch {
            setAgentStatus(null);
        }
    };

    useEffect(() => {
        if (!open) return;

        refreshStatus();
        const timer = setInterval(() => {
            refreshStatus();
        }, 7000);

        return () => clearInterval(timer);
    }, [open]);

    const initializeSystemAgent = async () => {
        setInitializing(true);
        setNotice('');
        try {
            const res = await fetch(`${API_BASE}/agent/init`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok || !data?.success) {
                throw new Error(data?.detail || data?.message || 'Agent initialization failed');
            }
            setNotice('Nirvana model downloaded and ready to start.');
            await refreshStatus();
            return true;
        } catch (e) {
            setNotice(e.message || 'Unable to initialize Nirvana');
            return false;
        } finally {
            setInitializing(false);
        }
    };

    const startSystemAgent = async () => {
        setStarting(true);
        setNotice('');
        try {
            const res = await fetch(`${API_BASE}/agent/start`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok || !data?.success) {
                throw new Error(data?.detail || data?.message || 'Agent start failed');
            }
            setNotice('Nirvana is live.');
            await refreshStatus();
            return true;
        } catch (e) {
            setNotice(e.message || 'Unable to start assistant');
            return false;
        } finally {
            setStarting(false);
        }
    };

    const sendToNirvana = async () => {
        const trimmed = chatInput.trim();
        if (!trimmed || chatLoading) return;

        const nextMsgs = [...chatMessages, { role: 'user', content: trimmed }];
        setChatMessages(nextMsgs);
        setChatInput('');
        setChatLoading(true);
        setNotice('');

        try {
            let canChat = Boolean(agentStatus?.is_running);
            if (!canChat && !agentStatus?.is_downloaded) {
                canChat = await initializeSystemAgent();
            }
            if (canChat && !agentStatus?.is_running) {
                canChat = await startSystemAgent();
            }
            if (!canChat) {
                throw new Error('Nirvana is not ready yet. Initialize/start first.');
            }

            const res = await fetch(`${API_BASE}/agent/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    messages: nextMsgs.map((m) => ({ role: m.role, content: m.content })),
                    temperature: 0.7,
                    max_tokens: 400,
                    use_fleet_tools: true,
                    use_orchestration_context: true,
                }),
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data?.detail || 'Nirvana response failed');
            }

            const reply = data?.choices?.[0]?.message?.content || 'No response from Nirvana.';
            const runtimeMeta = data?.nirvana_runtime || null;
            setChatMessages((prev) => [...prev, { role: 'assistant', content: reply, runtime: runtimeMeta }]);
            if (runtimeMeta) {
                setNotice(`Verified engine: ${runtimeMeta.engine} (${runtimeMeta.model_file})`);
            }
        } catch (e) {
            setChatMessages((prev) => [...prev, { role: 'assistant', content: `Error: ${e.message}` }]);
        } finally {
            setChatLoading(false);
            refreshStatus();
        }
    };

    return (
        <>
            <button
                className="assistant-launcher assistant-launcher-top"
                onClick={() => setOpen(v => !v)}
                aria-label="Open orchestration assistant"
                title="Nirvana"
            >
                <Bot size={18} />
                <Sparkles size={13} className="assistant-launcher-spark" />
            </button>

            <button
                className="assistant-launcher assistant-launcher-bottom"
                onClick={() => setOpen(v => !v)}
                aria-label="Open orchestration assistant"
                title="Nirvana"
            >
                <Bot size={18} />
            </button>

            {open && (
                <div className="assistant-launcher-panel">
                    <div className="assistant-launcher-title">Nirvana</div>
                    <div className="assistant-launcher-subtitle">Built-in orchestration assistant</div>

                    <div className="assistant-launcher-notice">
                        Status: {agentStatus?.is_running ? 'Running' : agentStatus?.is_downloaded ? 'Downloaded (not loaded)' : 'Not downloaded'}
                    </div>

                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <span className={`badge ${agentStatus?.is_running ? 'badge-success' : 'badge-warning'}`}>
                            Runtime: {agentStatus?.is_running ? 'online' : 'offline'}
                        </span>
                        <span className={`badge ${agentStatus?.is_downloaded ? 'badge-info' : 'badge-error'}`}>
                            Model: {agentStatus?.is_downloaded ? 'ready' : 'missing'}
                        </span>
                    </div>

                    <button className="btn btn-primary btn-sm w-full" onClick={() => { navigate('/chat-playground'); setOpen(false); }}>
                        Open Chat & Playground
                    </button>
                    <button className="btn btn-secondary btn-sm w-full" onClick={() => { navigate('/orchestration'); setOpen(false); }}>
                        Open Orchestration
                    </button>
                    <button className="btn btn-secondary btn-sm w-full" onClick={initializeSystemAgent} disabled={initializing || agentStatus?.is_downloaded}>
                        {initializing ? 'Initializing Nirvana…' : agentStatus?.is_downloaded ? 'Nirvana model ready' : 'Initialize Nirvana model'}
                    </button>
                    <button className="btn btn-secondary btn-sm w-full" onClick={startSystemAgent} disabled={starting}>
                        {starting ? 'Starting Nirvana…' : 'Start/Reload Nirvana'}
                    </button>

                    <div className="assistant-launcher-chatlog">
                        {chatMessages.length === 0 && <div className="text-muted">Ask Nirvana anything…</div>}
                        {chatMessages.map((m, idx) => (
                            <div key={`${m.role}-${idx}`} className={`assistant-msg assistant-msg-${m.role}`}>
                                <strong>{m.role === 'user' ? 'You' : 'Nirvana'}:</strong> {m.content}
                                {m.role === 'assistant' && m.runtime && (
                                    <div className="assistant-msg-runtime">
                                        engine: {m.runtime.engine} · model: {m.runtime.model_file} · mock: {String(m.runtime.uses_mock_responses)}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    <div style={{ display: 'flex', gap: 6 }}>
                        <input
                            className="form-input"
                            value={chatInput}
                            onChange={(e) => setChatInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') sendToNirvana(); }}
                            placeholder="Message Nirvana..."
                        />
                        <button className="btn btn-primary btn-sm" onClick={sendToNirvana} disabled={chatLoading || !chatInput.trim()}>
                            {chatLoading ? '…' : 'Send'}
                        </button>
                    </div>

                    {notice && <div className="assistant-launcher-notice">{notice}</div>}
                </div>
            )}
        </>
    );
}

function AppInner() {
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const { theme, toggleTheme } = useTheme();

    return (
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <div className="app-layout">

                {/* Mobile menu button */}
                <button
                    className="mobile-menu-btn"
                    onClick={() => setSidebarOpen(!sidebarOpen)}
                    aria-label="Toggle navigation"
                >
                    {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
                </button>

                {/* Sidebar overlay (mobile) */}
                {sidebarOpen && (
                    <div
                        className="sidebar-overlay"
                        onClick={() => setSidebarOpen(false)}
                        style={{
                            position: 'fixed', inset: 0,
                            background: 'rgba(0,0,0,0.5)',
                            zIndex: 99,
                            backdropFilter: 'blur(4px)',
                        }}
                    />
                )}

                {/* Sidebar */}
                <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
                    <div className="sidebar-header">
                        <div className="sidebar-logo">
                            <div className="sidebar-logo-icon">
                                <img src="/favicon.png" alt="NPU-STACK" />
                            </div>
                            <div className="sidebar-logo-text">
                                <h1>NPU-STACK</h1>
                                <span>Neural Processor Toolkit</span>
                            </div>
                        </div>
                    </div>

                    <div className="sidebar-brand">
                        Made by Fanalogy
                    </div>

                    <nav className="sidebar-nav">
                        {navItems.map(({ path, icon: Icon, label }) => (
                            <NavLink
                                key={path}
                                to={path}
                                end={path === '/'}
                                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                                onClick={() => setSidebarOpen(false)}
                            >
                                <Icon size={20} />
                                {label}
                            </NavLink>
                        ))}
                    </nav>

                    <div className="sidebar-footer">
                        <button
                            onClick={toggleTheme}
                            className="theme-toggle-btn"
                            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
                            aria-label="Toggle theme"
                        >
                            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                            {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
                        </button>
                        <div className="footer-brand">
                            Made by <strong>Fanalogy</strong>
                        </div>
                        <div className="footer-powered">
                            Powered by <strong>Nirvana</strong>
                        </div>
                        <div className="sidebar-version">v1.0.0</div>
                    </div>
                </aside>

                {/* Main Content */}
                <main className="main-content">
                    <Suspense fallback={<RouteLoadingFallback />}>
                        <Routes>
                            <Route path="/" element={<Dashboard />} />
                            <Route path="/chat" element={<Chat />} />
                            <Route path="/playground" element={<Playground />} />
                            <Route path="/chat-playground" element={<ChatPlayground />} />
                            <Route path="/orchestration" element={<Orchestration />} />
                            <Route path="/autoresearch" element={<AutoResearch />} />
                            <Route path="/models" element={<Models />} />
                            <Route path="/hub" element={<ModelHub />} />
                            <Route path="/hf-publisher" element={<HubPublisher />} />
                            <Route path="/datasets" element={<Datasets />} />
                            <Route path="/ingestion" element={<DataIngestion />} />
                            <Route path="/serving" element={<Serving />} />
                            <Route path="/training" element={<Training />} />
                            <Route path="/advanced-training" element={<AdvancedTraining />} />
                            <Route path="/finetuning" element={<FineTuning />} />
                            <Route path="/gguf-studio" element={<GGUFStudio />} />
                            <Route path="/fastflowlm" element={<FastFlowLM />} />
                            <Route path="/conversion" element={<Conversion />} />
                            <Route path="/scanner" element={<Scanner />} />
                            <Route path="/webcam" element={<WebcamTest />} />
                            <Route path="/benchmark" element={<Benchmark />} />
                            <Route path="/edge-fleet" element={<EdgeFleet />} />
                            <Route path="/fleet-command" element={<FleetCommand />} />
                            <Route path="*" element={<Navigate to="/" replace />} />
                        </Routes>
                    </Suspense>
                </main>

                <AssistantLauncher />

                {/* Footer Bar */}
                <footer className="main-footer">
                    <div className="footer-left">
                        Made by <strong>Fanalogy</strong>
                    </div>
                    <div className="footer-right">
                        Powered by <strong>Nirvana</strong>
                    </div>
                </footer>
            </div>
        </BrowserRouter>
    );
}

export default function App() {
    return (
        <ThemeProvider>
            <AppInner />
        </ThemeProvider>
    );
}
