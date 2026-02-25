import React, { useState, useEffect } from 'react';
import { Box, GraduationCap, Gauge, Cpu, HardDrive, Monitor, Zap, Database, Activity } from 'lucide-react';
import { getStatus, getSystemInfo } from '../api/client';

export default function Dashboard() {
    const [status, setStatus] = useState(null);
    const [sysInfo, setSysInfo] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([
            getStatus().catch(() => ({ models: 0, training_jobs: 0, running_jobs: 0, benchmarks: 0 })),
            getSystemInfo().catch(() => null),
        ]).then(([s, sys]) => {
            setStatus(s);
            setSysInfo(sys);
            setLoading(false);
        });
    }, []);

    if (loading) {
        return (
            <div className="loading-overlay">
                <div className="spinner" />
                <span>Loading dashboard...</span>
            </div>
        );
    }

    // Build device cards from API data
    const devices = [];

    // CPU always present
    if (sysInfo) {
        devices.push({
            name: sysInfo.processor || 'CPU',
            type: 'CPU',
            status: 'online',
            memory: `${sysInfo.memory_available_gb}/${sysInfo.memory_total_gb} GB`,
            cores: `${sysInfo.cpu_count_physical || '?'}C / ${sysInfo.cpu_count || '?'}T`,
            color: 'blue',
        });
    }

    // All GPUs from API (CUDA, ROCm/AMD, etc.)
    if (sysInfo?.gpus) {
        sysInfo.gpus.forEach(gpu => {
            devices.push({
                name: gpu.name,
                type: gpu.type || 'GPU',
                status: gpu.status || 'online',
                memory: gpu.memory_gb ? `${gpu.memory_gb} GB VRAM` : '—',
                cores: gpu.compute_capability || '—',
                color: gpu.type === 'ROCm (AMD)' ? 'amber' : 'green',
            });
        });
    }

    // NPU
    if (sysInfo?.npu_available) {
        devices.push({
            name: 'Intel NPU',
            type: 'NPU',
            status: 'online',
            memory: 'Integrated',
            cores: 'AI Accelerator',
            color: 'purple',
        });
    }

    // Coral TPU
    if (sysInfo?.coral_tpu_available) {
        devices.push({
            name: 'Google Coral',
            type: 'Edge TPU',
            status: 'online',
            memory: 'USB/M.2',
            cores: sysInfo.coral_tpu_delegate || 'Edge TPU',
            color: 'amber',
        });
    }

    // OpenVINO extra devices (GNA, etc.)
    if (sysInfo?.openvino_devices) {
        sysInfo.openvino_devices.forEach(dev => {
            if (dev !== 'CPU' && dev !== 'NPU' && dev !== 'GPU' && !devices.find(d => d.name === dev)) {
                devices.push({
                    name: dev,
                    type: dev,
                    status: 'online',
                    memory: '—',
                    cores: 'OpenVINO',
                    color: 'amber',
                });
            }
        });
    }

    // If only CPU, add offline GPU placeholder
    if (devices.length === 1) {
        devices.push({
            name: 'No GPU Detected',
            type: 'GPU',
            status: 'offline',
            memory: '—',
            cores: '—',
            color: 'red',
        });
    }

    return (
        <div>
            <div className="page-header">
                <h2>Dashboard</h2>
                <p>Overview of your NPU/TPU model development environment</p>
            </div>

            {/* Metrics */}
            <div className="metrics-grid">
                <div className="metric-card blue">
                    <div className="metric-icon"><Box size={22} /></div>
                    <div className="metric-value">{status?.models ?? 0}</div>
                    <div className="metric-label">Models Registered</div>
                </div>
                <div className="metric-card purple">
                    <div className="metric-icon"><GraduationCap size={22} /></div>
                    <div className="metric-value">{status?.training_jobs ?? 0}</div>
                    <div className="metric-label">Training Jobs</div>
                </div>
                <div className="metric-card green">
                    <div className="metric-icon"><Zap size={22} /></div>
                    <div className="metric-value">{status?.running_jobs ?? 0}</div>
                    <div className="metric-label">Running Now</div>
                </div>
                <div className="metric-card amber">
                    <div className="metric-icon"><Gauge size={22} /></div>
                    <div className="metric-value">{status?.benchmarks ?? 0}</div>
                    <div className="metric-label">Benchmarks Run</div>
                </div>
            </div>

            {/* ── Device Cards with Glow ────────────────────── */}
            <h3 style={{ fontSize: '14px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', color: 'var(--text-muted)', marginBottom: '16px', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Activity size={16} /> Compute Devices
            </h3>
            <div className="device-grid">
                {devices.map((d, i) => (
                    <div key={i} className={`device-card device-${d.color} ${d.status === 'online' ? 'device-online' : ''}`}>
                        <div className="device-header">
                            <div className={`device-indicator ${d.status}`}></div>
                            <span className="device-type">{d.type}</span>
                        </div>
                        <div className="device-name">{d.name}</div>
                        <div className="device-stats">
                            <div className="device-stat">
                                <span className="device-stat-label">Memory</span>
                                <span className="device-stat-value">{d.memory}</span>
                            </div>
                            <div className="device-stat">
                                <span className="device-stat-label">Config</span>
                                <span className="device-stat-value">{d.cores}</span>
                            </div>
                        </div>
                        <div className={`device-status-bar ${d.status}`}></div>
                    </div>
                ))}
            </div>

            {/* System Info Grid */}
            <div className="grid-2">
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">System Hardware</h3>
                        <Monitor size={18} className="text-secondary" />
                    </div>
                    {sysInfo ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <InfoRow label="Platform" value={sysInfo.platform} />
                            <InfoRow label="Processor" value={sysInfo.processor || 'N/A'} />
                            <InfoRow label="CPU Cores" value={`${sysInfo.cpu_count_physical || '?'} physical / ${sysInfo.cpu_count || '?'} logical`} />
                            <InfoRow label="Memory" value={`${sysInfo.memory_available_gb} / ${sysInfo.memory_total_gb} GB`} />
                            <InfoRow label="CUDA" value={sysInfo.cuda_available ? `✅ ${sysInfo.cuda_device || 'Yes'}` : '❌ Not available'} />
                        </div>
                    ) : (
                        <p className="text-secondary">System info unavailable</p>
                    )}
                </div>

                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Hardware Capabilities</h3>
                        <Cpu size={18} className="text-secondary" />
                    </div>
                    {sysInfo ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {sysInfo.capabilities ? (
                                Object.entries(sysInfo.capabilities).map(([key, cap]) => (
                                    <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: 'var(--bg-input)', borderRadius: 'var(--radius-md)' }}>
                                        <span style={{ fontSize: '16px', flexShrink: 0 }}>{cap.available ? '✅' : '❌'}</span>
                                        <span style={{ fontSize: '13px', fontWeight: 500, color: cap.available ? 'var(--text-primary)' : 'var(--text-muted)', flex: 1 }}>{cap.label}</span>
                                        <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: cap.available ? 'var(--accent-green)' : 'var(--text-muted)', fontWeight: 600 }}>
                                            {cap.available ? 'READY' : 'N/A'}
                                        </span>
                                    </div>
                                ))
                            ) : (
                                <>
                                    <InfoRow label="NPU" value={sysInfo.npu_available ? '✅ Available' : '❌ Not detected'} />
                                    <InfoRow label="CUDA" value={sysInfo.cuda_available ? '✅ Available' : '❌ Not detected'} />
                                    <InfoRow label="OpenVINO" value={sysInfo.openvino_devices?.length ? `✅ ${sysInfo.openvino_devices.join(', ')}` : '❌ None'} />
                                    <InfoRow label="ORT" value={sysInfo.onnxruntime_providers?.length ? '✅ Available' : '❌ None'} />
                                </>
                            )}
                        </div>
                    ) : (
                        <p className="text-secondary">Capabilities info unavailable</p>
                    )}
                </div>
            </div>

            {/* Quick Actions */}
            <div className="card mt-6">
                <div className="card-header">
                    <h3 className="card-title">Quick Start Guide</h3>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
                    <QuickAction step="1" title="Get a Model" description="Upload an ONNX model, or download one from HuggingFace Hub via the browser." />
                    <QuickAction step="2" title="Test in Playground" description="Run classification, detection, or text generation interactively." />
                    <QuickAction step="3" title="Convert & Quantize" description="Convert to OpenVINO IR and apply INT8/INT4 quantization for NPU." />
                    <QuickAction step="4" title="Benchmark & Compare" description="Run inference benchmarks across CPU, GPU, NPU at different precisions." />
                </div>
            </div>
        </div>
    );
}

function InfoRow({ label, value }) {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-tertiary)', fontWeight: 500 }}>{label}</span>
            <span style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{value}</span>
        </div>
    );
}

function QuickAction({ step, title, description }) {
    return (
        <div style={{
            padding: '20px',
            background: 'var(--bg-tertiary)',
            borderRadius: '12px',
            border: '1px solid var(--border-subtle)',
        }}>
            <div style={{
                width: '32px', height: '32px', borderRadius: '8px',
                background: 'var(--gradient-primary)', display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                fontSize: '14px', fontWeight: 700, color: 'white', marginBottom: '12px',
            }}>
                {step}
            </div>
            <h4 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>{title}</h4>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{description}</p>
        </div>
    );
}
