import React, { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { LayoutDashboard, Box, GraduationCap, ArrowRightLeft, Gauge, Menu, X, Globe, Database, Server, Wrench, FolderSearch, Camera, Upload, Cpu, CloudUpload, Zap, MonitorSmartphone, Radio, FlaskConical, Sun, Moon, Microscope, Bot, Sparkles, BookOpen, SearchCheck, Settings, MessageSquare, Puzzle, Clock, Home, Brain, Kanban, Key, ScrollText, FolderOpen, Palette, Package } from 'lucide-react';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import { API_BASE } from './api/client';
const CompactAgentOverlay = lazy(() => import('./components/CompactAgentOverlay'));

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
const NirvanaSettings = lazy(() => import('./pages/NirvanaSettings'));
const NirvanaSessions = lazy(() => import('./pages/NirvanaSessions'));
const NirvanaSkills = lazy(() => import('./pages/NirvanaSkills'));
const NirvanaDashboard = lazy(() => import('./pages/NirvanaDashboard'));
const NirvanaCron = lazy(() => import('./pages/NirvanaCron'));
const NirvanaMemory = lazy(() => import('./pages/NirvanaMemory'));
const NirvanaKanban = lazy(() => import('./pages/NirvanaKanban'));
const NirvanaProviders = lazy(() => import('./pages/NirvanaProviders'));
const NirvanaLogs = lazy(() => import('./pages/NirvanaLogs'));
const NirvanaWorkspace = lazy(() => import('./pages/NirvanaWorkspace'));
const NirvanaAppearance = lazy(() => import('./pages/NirvanaAppearance'));
const NirvanaPlugins = lazy(() => import('./pages/NirvanaPlugins'));

const navItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/chat-playground', icon: FlaskConical, label: 'Chat & Playground' },
    { path: '/orchestration', icon: Microscope, label: 'Orchestration' },
    { path: '/agents', icon: Bot, label: 'Agents' },
    { path: '/autoresearch', icon: SearchCheck, label: 'AutoResearch' },
    { path: '/documentation', icon: BookOpen, label: 'Documentation' },
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
    // ── Nirvana native panels ──
    { path: '/nirvana-chat', icon: MessageSquare, label: 'Nirvana Chat' },
    { path: '/nirvana-settings', icon: Settings, label: 'Settings' },
    { path: '/nirvana-sessions', icon: BookOpen, label: 'Sessions' },
    { path: '/nirvana-skills', icon: Puzzle, label: 'Skills' },
    { path: '/nirvana-dashboard', icon: Home, label: 'Nirvana Home' },
    { path: '/nirvana-cron', icon: Clock, label: 'Cron' },
    { path: '/nirvana-memory', icon: Brain, label: 'Memory' },
    { path: '/nirvana-kanban', icon: Kanban, label: 'Kanban' },
    { path: '/nirvana-providers', icon: Key, label: 'Providers' },
    { path: '/nirvana-logs', icon: ScrollText, label: 'Logs' },
    { path: '/nirvana-workspace', icon: FolderOpen, label: 'Workspace' },
    { path: '/nirvana-appearance', icon: Palette, label: 'Appearance' },
    { path: '/nirvana-plugins', icon: Package, label: 'Plugins' },
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
                            <Route path="/agents" element={<Agents />} />
                            <Route path="/autoresearch" element={<AutoResearch />} />
                            <Route path="/documentation" element={<Documentation />} />
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
                            <Route path="/nirvana-chat" element={<NirvanaChat />} />
                            <Route path="/nirvana-settings" element={<NirvanaSettings />} />
                            <Route path="/nirvana-sessions" element={<NirvanaSessions />} />
                            <Route path="/nirvana-skills" element={<NirvanaSkills />} />
                            <Route path="/nirvana-dashboard" element={<NirvanaDashboard />} />
                            <Route path="/nirvana-cron" element={<NirvanaCron />} />
                            <Route path="/nirvana-memory" element={<NirvanaMemory />} />
                            <Route path="/nirvana-kanban" element={<NirvanaKanban />} />
                            <Route path="/nirvana-providers" element={<NirvanaProviders />} />
                            <Route path="/nirvana-logs" element={<NirvanaLogs />} />
                            <Route path="/nirvana-workspace" element={<NirvanaWorkspace />} />
                            <Route path="/nirvana-appearance" element={<NirvanaAppearance />} />
                            <Route path="/nirvana-plugins" element={<NirvanaPlugins />} />
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
