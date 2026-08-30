import React, { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { LayoutDashboard, Box, GraduationCap, ArrowRightLeft, Gauge, Menu, X, Globe, Database, Server, Wrench, FolderSearch, Camera, Upload, Cpu, CloudUpload, Zap, MonitorSmartphone, Radio, FlaskConical, Sun, Moon, Microscope, Bot, Sparkles, BookOpen, SearchCheck, MessageSquare, ChevronDown, ChevronRight, Antenna, Smartphone, Volume2 } from 'lucide-react';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import { AgentRuntimeProvider } from './context/AgentRuntimeContext';
import { API_BASE } from './api/client';
const CompactAgentOverlay = lazy(() => import('./components/CompactAgentOverlay'));

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Models = lazy(() => import('./pages/Models'));
const Training = lazy(() => import('./pages/Training'));
const AdvancedTraining = lazy(() => import('./pages/AdvancedTraining'));
const TrainingCenter = lazy(() => import('./pages/TrainingCenter'));
const Conversion = lazy(() => import('./pages/Conversion'));
const Benchmark = lazy(() => import('./pages/Benchmark'));
const Playground = lazy(() => import('./pages/Playground'));
const Chat = lazy(() => import('./pages/Chat'));
const ChatPlayground = lazy(() => import('./pages/ChatPlayground'));
const Orchestration = lazy(() => import('./pages/Orchestration'));
const Agents = lazy(() => import('./pages/Agents'));
const AutoResearch = lazy(() => import('./pages/AutoResearch'));
const Documentation = lazy(() => import('./pages/Documentation'));
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
const NirvanaChat = lazy(() => import('./pages/NirvanaChat'));
const NirvanaTodos = lazy(() => import('./pages/NirvanaTodos'));
const NirvanaInsights = lazy(() => import('./pages/NirvanaInsights'));
const BoardExplorer = lazy(() => import('./pages/BoardExplorer'));
const BoardDetail = lazy(() => import('./pages/BoardDetail'));
const EspNowDeploy = lazy(() => import('./pages/EspNowDeploy'));
const EspDevConsole = lazy(() => import('./pages/EspDevConsole'));
const DevicePlayground = lazy(() => import('./pages/DevicePlayground'));
const AudioOutput = lazy(() => import('./pages/AudioOutput'));

const managementItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/models', icon: Box, label: 'Models' },
    { path: '/hub', icon: Globe, label: 'Model Hub' },
    { path: '/datasets', icon: Database, label: 'Datasets' },
    { path: '/ingestion', icon: Upload, label: 'Data Ingestion' },
    { path: '/serving', icon: Server, label: 'Serving' },
    { path: '/training', icon: GraduationCap, label: 'Training' },
    { path: '/gguf-studio', icon: Cpu, label: 'GGUF Studio' },
    { path: '/fastflowlm', icon: Zap, label: 'FastFlowLM' },
    { path: '/conversion', icon: ArrowRightLeft, label: 'Conversion' },
    { path: '/scanner', icon: FolderSearch, label: 'Scanner' },
    { path: '/webcam', icon: Camera, label: 'Webcam' },
    { path: '/benchmark', icon: Gauge, label: 'Benchmark' },
    { path: '/edge-fleet', icon: MonitorSmartphone, label: 'Edge Fleet' },
    { path: '/fleet-command', icon: Radio, label: 'Fleet Command' },
    { path: '/esp-dev', icon: Cpu, label: 'ESP Dev' },
    { path: '/boards', icon: Cpu, label: 'Boards' },
    { path: '/device-playground', icon: Smartphone, label: 'Device Playground' },
];

const nirvanaItems = [
    { path: '/nirvana-chat', icon: MessageSquare, label: 'Chat' },
    { path: '/agents', icon: Bot, label: 'Agents' },
    { path: '/audio-output', icon: Volume2, label: 'Audio Output' },
    { path: '/orchestration', icon: Microscope, label: 'Orchestration' },
    { path: '/autoresearch', icon: SearchCheck, label: 'AutoResearch' },
    { path: '/documentation', icon: BookOpen, label: 'Documentation' },
    { path: '/chat-playground', icon: FlaskConical, label: 'Chat Playground' },
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
    const [overlayOpen, setOverlayOpen] = useState(false);

    return (
        <>
            <button
                className="assistant-launcher assistant-launcher-top"
                onClick={() => setOverlayOpen(v => !v)}
                aria-label="Toggle Nirvana overlay"
                title="Toggle Nirvana overlay"
            >
                <Bot size={18} />
                <Sparkles size={13} className="assistant-launcher-spark" />
            </button>

            <button
                className="assistant-launcher assistant-launcher-bottom"
                onClick={() => setOverlayOpen(v => !v)}
                aria-label="Toggle Nirvana overlay"
                title="Toggle Nirvana overlay"
            >
                <Bot size={18} />
            </button>

            {overlayOpen && (
                <Suspense fallback={null}>
                    <CompactAgentOverlay onClose={() => setOverlayOpen(false)} />
                </Suspense>
            )}
        </>
    );
}

function AppInner() {
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [nirvanaExpanded, setNirvanaExpanded] = useState(true);
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
                        {managementItems.map(({ path, icon: Icon, label }) => (
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

                        {/* ── Nirvana ────────────────────────────── */}
                        <div style={{ marginTop: 12, borderTop: '1px solid var(--border-color)', paddingTop: 8 }}>
                            <button
                                onClick={() => setNirvanaExpanded(v => !v)}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: 10,
                                    width: '100%', padding: '8px 12px',
                                    background: 'none', border: 'none',
                                    color: 'var(--text-secondary)', cursor: 'pointer',
                                    fontSize: 12, fontWeight: 600,
                                    textTransform: 'uppercase', letterSpacing: 1,
                                    borderRadius: 8, marginBottom: 4,
                                }}>
                                <Bot size={16} color="#4ade80" />
                                Nirvana
                                <span style={{ marginLeft: 'auto' }}>
                                    {nirvanaExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                </span>
                            </button>

                            <div style={{
                                overflow: nirvanaExpanded ? 'hidden auto' : 'hidden',
                                maxHeight: nirvanaExpanded ? '420px' : '0',
                                transition: 'max-height 0.25s ease',
                            }}>
                                {nirvanaItems.map(({ path, icon: Icon, label }) => (
                                    <NavLink
                                        key={path}
                                        to={path}
                                        className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                                        onClick={() => setSidebarOpen(false)}
                                    >
                                        <Icon size={18} />
                                        {label}
                                    </NavLink>
                                ))}
                            </div>
                        </div>
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
                            <Route path="/agents" element={<Agents />} />
                            <Route path="/audio-output" element={<AudioOutput />} />
                            <Route path="/autoresearch" element={<AutoResearch />} />
                            <Route path="/documentation" element={<Documentation />} />
                            <Route path="/models" element={<Models />} />
                            <Route path="/hub" element={<ModelHub />} />
                            <Route path="/datasets" element={<Datasets />} />
                            <Route path="/ingestion" element={<DataIngestion />} />
                            <Route path="/serving" element={<Serving />} />
                            <Route path="/training" element={<TrainingCenter />} />
                            <Route path="/advanced-training" element={<Navigate to="/training" replace />} />
                            <Route path="/finetuning" element={<Navigate to="/training" replace />} />
                            <Route path="/hf-publisher" element={<Navigate to="/training" replace />} />
                            <Route path="/gguf-studio" element={<GGUFStudio />} />
                            <Route path="/fastflowlm" element={<FastFlowLM />} />
                            <Route path="/conversion" element={<Conversion />} />
                            <Route path="/scanner" element={<Scanner />} />
                            <Route path="/webcam" element={<WebcamTest />} />
                            <Route path="/benchmark" element={<Benchmark />} />
                            <Route path="/edge-fleet" element={<EdgeFleet />} />
                            <Route path="/fleet-command" element={<FleetCommand />} />
                            <Route path="/espnow-deploy" element={<Navigate to="/esp-dev" replace />} />
                            <Route path="/esp-dev" element={<EspDevConsole />} />
                            <Route path="/boards" element={<BoardExplorer />} />
                            <Route path="/boards/:boardId" element={<BoardDetail />} />
                            <Route path="/device-playground" element={<DevicePlayground />} />
                            <Route path="/nirvana-chat" element={<NirvanaChat />} />
                            <Route path="/nirvana-todos" element={<NirvanaTodos />} />
                            <Route path="/nirvana-insights" element={<NirvanaInsights />} />
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
            <AgentRuntimeProvider>
                <AppInner />
            </AgentRuntimeProvider>
        </ThemeProvider>
    );
}
