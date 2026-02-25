import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { LayoutDashboard, Box, GraduationCap, ArrowRightLeft, Gauge, Menu, X, Play, Globe, Database, Server, Wrench, FolderSearch, Camera, Upload } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Models from './pages/Models';
import Training from './pages/Training';
import Conversion from './pages/Conversion';
import Benchmark from './pages/Benchmark';
import Playground from './pages/Playground';
import HuggingFaceHub from './pages/HuggingFaceHub';
import Datasets from './pages/Datasets';
import Serving from './pages/Serving';
import FineTuning from './pages/FineTuning';
import Scanner from './pages/Scanner';
import WebcamTest from './pages/WebcamTest';
import DataIngestion from './pages/DataIngestion';

const navItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/playground', icon: Play, label: 'Playground' },
    { path: '/models', icon: Box, label: 'Models' },
    { path: '/huggingface', icon: Globe, label: 'HuggingFace' },
    { path: '/datasets', icon: Database, label: 'Datasets' },
    { path: '/ingestion', icon: Upload, label: 'Data Ingestion' },
    { path: '/serving', icon: Server, label: 'Serving' },
    { path: '/training', icon: GraduationCap, label: 'Training' },
    { path: '/finetuning', icon: Wrench, label: 'Fine-Tuning' },
    { path: '/conversion', icon: ArrowRightLeft, label: 'Conversion' },
    { path: '/scanner', icon: FolderSearch, label: 'Scanner' },
    { path: '/webcam', icon: Camera, label: 'Webcam' },
    { path: '/benchmark', icon: Gauge, label: 'Benchmark' },
];

export default function App() {
    const [sidebarOpen, setSidebarOpen] = useState(false);

    return (
        <BrowserRouter>
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
                    <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/playground" element={<Playground />} />
                        <Route path="/models" element={<Models />} />
                        <Route path="/huggingface" element={<HuggingFaceHub />} />
                        <Route path="/datasets" element={<Datasets />} />
                        <Route path="/ingestion" element={<DataIngestion />} />
                        <Route path="/serving" element={<Serving />} />
                        <Route path="/training" element={<Training />} />
                        <Route path="/finetuning" element={<FineTuning />} />
                        <Route path="/conversion" element={<Conversion />} />
                        <Route path="/scanner" element={<Scanner />} />
                        <Route path="/webcam" element={<WebcamTest />} />
                        <Route path="/benchmark" element={<Benchmark />} />
                    </Routes>
                </main>

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
