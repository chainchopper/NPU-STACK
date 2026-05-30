import React, { useState, useEffect } from 'react';
import { Box, GraduationCap, Gauge, Cpu, HardDrive, Monitor, Zap, Database, Activity, ArrowRight, Server, Cloud, Layers, Sparkles, Rocket, ChevronRight, CheckCircle2 } from 'lucide-react';
import { getStatus, getSystemInfo } from '../api/client';
import SystemAgent from '../components/SystemAgent';

export default function Dashboard() {
    const [status, setStatus] = useState(null);
    const [sysInfo, setSysInfo] = useState(null);
    const [loading, setLoading] = useState(true);
    const [wizardDismissed, setWizardDismissed] = useState(() => localStorage.getItem('npu-wizard-dismissed') === 'true');

    useEffect(() => {
        let cancelled = false;
        const fallbackStatus = { models: 0, training_jobs: 0, running_jobs: 0, benchmarks: 0 };

        getStatus()
            .catch(() => fallbackStatus)
            .then((nextStatus) => {
                if (cancelled) return;
                setStatus(nextStatus);
                setLoading(false);
            });

        getSystemInfo()
            .catch(() => null)
            .then((nextSysInfo) => {
                if (cancelled) return;
                setSysInfo(nextSysInfo);
            });

        const unblockTimer = setTimeout(() => {
            if (!cancelled) {
                setLoading(false);
            }
        }, 3000);

        return () => {
            cancelled = true;
            clearTimeout(unblockTimer);
        };
    }, []);

    if (loading) {
        return (
            <div className="loading-overlay">
                <div className="spinner" />
                <span>Loading dashboard...</span>
            </div>
        );
    }

    // Build device cards from API data — only REAL detected hardware
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

    // CUDA/ROCm/iGPU GPUs from API
    if (sysInfo?.gpus) {
        sysInfo.gpus.forEach(gpu => {
            const colorMap = { 'ROCm (AMD)': 'amber', 'AMD iGPU': 'amber', 'Intel Arc': 'purple', 'OpenVINO GPU': 'blue' };
            devices.push({
                name: gpu.name,
                type: gpu.type || 'GPU',
                status: gpu.status || 'online',
                memory: gpu.memory_gb ? `${gpu.memory_gb} GB VRAM` : gpu.type?.includes('iGPU') ? 'Shared Memory' : '—',
                cores: gpu.compute_capability || '—',
                temp: gpu.temperature_c ? `${gpu.temperature_c}°C` : null,
                utilization: gpu.utilization_pct != null ? `${gpu.utilization_pct}%` : null,
                power: gpu.power_draw_w ? `${gpu.power_draw_w}W` : null,
                pcie_tx: gpu.pcie_tx_mb_s != null ? `${gpu.pcie_tx_mb_s} MB/s` : null,
                pcie_rx: gpu.pcie_rx_mb_s != null ? `${gpu.pcie_rx_mb_s} MB/s` : null,
                color: colorMap[gpu.type] || 'green',
            });
        });
    }

    // NPU — only if actually detected
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

    // Coral TPU — only if actually detected
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

    // NOTE: We intentionally do NOT add OpenVINO sub-devices (GPU.0, GPU.1, etc.)
    // as device cards. OpenVINO reports these as execution targets, not physical GPUs.
    // They are shown in the capabilities section instead.

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

    const isFirstRun = (status?.models ?? 0) === 0 && !wizardDismissed;

    return (
        <div>
            <div className="page-header">
                <h2>Dashboard</h2>
                <p>Overview of your NPU/TPU model development environment</p>
            </div>

            {/* Onboarding Wizard */}
            {isFirstRun && <OnboardingWizard onDismiss={() => { setWizardDismissed(true); localStorage.setItem('npu-wizard-dismissed', 'true'); }} />}

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

            {/* ── Device Cards ────────────────────── */}
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
                                <span className="device-stat-label">{d.type === 'CPU' ? 'Cores' : 'Compute'}</span>
                                <span className="device-stat-value">{d.cores}</span>
                            </div>
                            {d.temp && (
                                <div className="device-stat">
                                    <span className="device-stat-label">Temp</span>
                                    <span className="device-stat-value">{d.temp}</span>
                                </div>
                            )}
                            {d.utilization && (
                                <div className="device-stat">
                                    <span className="device-stat-label">GPU Load</span>
                                    <span className="device-stat-value">{d.utilization}</span>
                                </div>
                            )}
                            {d.power && (
                                <div className="device-stat">
                                    <span className="device-stat-label">Power</span>
                                    <span className="device-stat-value">{d.power}</span>
                                </div>
                            )}
                            {d.pcie_tx && (
                                <div className="device-stat">
                                    <span className="device-stat-label">PCIe Tx</span>
                                    <span className="device-stat-value">{d.pcie_tx}</span>
                                </div>
                            )}
                            {d.pcie_rx && (
                                <div className="device-stat">
                                    <span className="device-stat-label">PCIe Rx</span>
                                    <span className="device-stat-value">{d.pcie_rx}</span>
                                </div>
                            )}
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
                            <InfoRow label="NVIDIA Driver" value={sysInfo.nvidia_driver_version || 'N/A'} />
                            <InfoRow label="CUDA" value={sysInfo.cuda_available ? `✅ v${sysInfo.cuda_version || '?'} — ${sysInfo.cuda_device || 'GPU'}` : '❌ Not available'} />
                            <InfoRow
                                label="ORT CUDA"
                                value={sysInfo.onnxruntime_cuda_ready
                                    ? '✅ Provider ready'
                                    : `❌ ${sysInfo.onnxruntime_cuda_error || 'Provider unavailable'}`}
                            />
                            <InfoRow
                                label="ONNX Runtime Providers"
                                value={sysInfo.onnxruntime_providers?.length
                                    ? sysInfo.onnxruntime_providers.join(', ')
                                    : 'N/A'}
                            />
                            <InfoRow label="AVX2" value={sysInfo.avx2_available ? '✅ Available' : '❌ Not available'} />
                            {sysInfo.cuda_available && sysInfo.cuda_memory_gb && (
                                <InfoRow label="VRAM" value={`${sysInfo.cuda_memory_gb} GB`} />
                            )}
                            {sysInfo.cudnn_version && (
                                <InfoRow label="cuDNN" value={`v${sysInfo.cudnn_version}`} />
                            )}
                            {sysInfo.torch_version && (
                                <InfoRow label="PyTorch" value={sysInfo.torch_version} />
                            )}
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
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '420px', overflowY: 'auto' }}>
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

            <PipelineFlow />
            <HardwareMatrix capabilities={sysInfo?.capabilities} />
            <SystemAgent />
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

/* ─── Onboarding Wizard ────────────────────────────────────── */
function OnboardingWizard({ onDismiss }) {
    const [step, setStep] = useState(0);

    const steps = [
        {
            icon: <Sparkles size={28} />,
            title: 'Welcome to NPU-STACK',
            desc: 'Universal neural processor toolkit for NVIDIA, AMD, Intel, Rockchip, Coral, and more.',
            action: 'Get Started',
        },
        {
            icon: <Database size={28} />,
            title: '1. Import Models',
            desc: 'Use the Scanner to find local models, or browse HuggingFace Hub. ONNX, SafeTensors, GGUF, PyTorch — all supported.',
            action: 'Next',
            link: '/scanner',
            linkLabel: 'Open Scanner →',
        },
        {
            icon: <Layers size={28} />,
            title: '2. Convert & Optimize',
            desc: 'Cross-convert between 14+ format paths. Quantize models for INT8/INT4 or GGUF for CPU inference.',
            action: 'Next',
            link: '/conversion',
            linkLabel: 'Open Conversion Studio →',
        },
        {
            icon: <Zap size={28} />,
            title: '3. Serve & Deploy',
            desc: 'Load any model into the inference server and test with the built-in chat/API playground.',
            action: 'Next',
            link: '/serving',
            linkLabel: 'Open Serving →',
        },
        {
            icon: <Rocket size={28} />,
            title: 'You\'re Ready!',
            desc: 'Explore the sidebar for fine-tuning, benchmarks, GGUF studio, webcam inference, and more.',
            action: 'Start Building',
        },
    ];

    const s = steps[step];
    const isLast = step === steps.length - 1;

    return (
        <div className="card" style={{ marginBottom: '24px', border: '1px solid var(--accent-blue)', background: 'linear-gradient(135deg, rgba(59,130,246,0.08) 0%, rgba(139,92,246,0.06) 100%)' }}>
            <div style={{ padding: '28px', display: 'flex', gap: '24px', alignItems: 'flex-start' }}>
                <div style={{ width: 56, height: 56, borderRadius: 14, background: 'var(--gradient-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', flexShrink: 0 }}>
                    {s.icon}
                </div>
                <div style={{ flex: 1 }}>
                    <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>{s.title}</h3>
                    <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 16 }}>{s.desc}</p>
                    <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                        {s.link && (
                            <a href={s.link} style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent-blue)', textDecoration: 'none' }}>
                                {s.linkLabel}
                            </a>
                        )}
                        <button className="btn btn-primary" onClick={() => isLast ? onDismiss() : setStep(step + 1)} style={{ fontSize: 13, padding: '8px 20px' }}>
                            {s.action} <ChevronRight size={14} style={{ marginLeft: 4 }} />
                        </button>
                        {step === 0 && (
                            <button className="btn btn-ghost" onClick={onDismiss} style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                                Skip tour
                            </button>
                        )}
                    </div>
                </div>
                {/* Step dots */}
                <div style={{ display: 'flex', gap: 6, alignSelf: 'center' }}>
                    {steps.map((_, i) => (
                        <div key={i} style={{
                            width: 8, height: 8, borderRadius: '50%',
                            background: i === step ? 'var(--accent-blue)' : i < step ? 'var(--accent-green)' : 'var(--border-default)',
                            transition: 'background 0.2s',
                            cursor: 'pointer',
                        }} onClick={() => setStep(i)} />
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ─── Pipeline Flow (static architecture diagram) ──────────── */
function PipelineFlow() {
    return (
        <div className="card mt-6">
            <div className="card-header">
                <h3 className="card-title">NPU-STACK Architecture Pipeline</h3>
                <Layers size={18} className="text-secondary" />
            </div>
            <div style={{ padding: '24px', overflowX: 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', minWidth: '800px', gap: '16px' }}>
                    <div style={{ flex: 1, background: 'var(--bg-tertiary)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-subtle)', textAlign: 'center' }}>
                        <Database size={28} style={{ color: 'var(--accent-blue)', marginBottom: '12px' }} />
                        <h4 style={{ fontWeight: 600, fontSize: '14px', marginBottom: '8px' }}>1. Ingestion</h4>
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>HuggingFace Hub<br />Local Models<br />Custom Datasets</div>
                    </div>
                    <ArrowRight size={24} style={{ color: 'var(--text-muted)' }} />
                    <div style={{ flex: 1, background: 'var(--bg-tertiary)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-subtle)', textAlign: 'center' }}>
                        <Box size={28} style={{ color: 'var(--accent-purple)', marginBottom: '12px' }} />
                        <h4 style={{ fontWeight: 600, fontSize: '14px', marginBottom: '8px' }}>2. Processing</h4>
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>ONNX / OpenVINO<br />GGUF / LiteRT<br />Unsloth QLoRA</div>
                    </div>
                    <ArrowRight size={24} style={{ color: 'var(--text-muted)' }} />
                    <div style={{ flex: 1, background: 'var(--bg-tertiary)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-subtle)', textAlign: 'center' }}>
                        <Cpu size={28} style={{ color: 'var(--accent-amber)', marginBottom: '12px' }} />
                        <h4 style={{ fontWeight: 600, fontSize: '14px', marginBottom: '8px' }}>3. Hardware</h4>
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>NVIDIA / AMD / Intel<br />Rockchip / Coral TPU<br />Xilinx Vitis DPU</div>
                    </div>
                    <ArrowRight size={24} style={{ color: 'var(--text-muted)' }} />
                    <div style={{ flex: 1, background: 'var(--bg-tertiary)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-subtle)', textAlign: 'center' }}>
                        <Cloud size={28} style={{ color: 'var(--accent-green)', marginBottom: '12px' }} />
                        <h4 style={{ fontWeight: 600, fontSize: '14px', marginBottom: '8px' }}>4. Deployment</h4>
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>FastFlowLM Runtime<br />FastAPI / NVIDIA NIM<br />CVEDIA-RT Edge</div>
                    </div>
                </div>
            </div>
        </div>
    );
}

/* ─── Hardware Matrix — now driven by actual capabilities ──── */
function HardwareMatrix({ capabilities }) {
    // Map backend capability keys to hardware compatibility rows
    const hwMap = [
        { capKey: 'cuda_gpu', name: 'NVIDIA CUDA GPU', formats: 'PyTorch, ONNX, GGUF, TensorRT', deploy: 'API, NIM, CVEDIA' },
        { capKey: 'onnxruntime_cuda', name: 'ONNX Runtime CUDA EP', formats: 'ONNX', deploy: 'Benchmark / Inference' },
        { capKey: 'rocm_gpu', name: 'AMD ROCm GPU', formats: 'PyTorch, ONNX, GGUF', deploy: 'API, CVEDIA' },
        { capKey: 'intel_npu', name: 'Intel NPU / Arc', formats: 'OpenVINO, ONNX', deploy: 'API, CVEDIA' },
        { capKey: 'coral_tpu', name: 'Google Coral TPU', formats: 'LiteRT (TFLite)', deploy: 'MediaPipe, CVEDIA' },
        { capKey: 'rknn_npu', name: 'Rockchip NPU', formats: 'RKNN, rk-llama GGUF', deploy: 'API, Edge' },
        { capKey: 'vitis_ai', name: 'Xilinx/AMD Alveo', formats: 'vitis_xmodel', deploy: 'Vitis DPU API' },
        { capKey: 'directml', name: 'DirectML (Windows)', formats: 'ONNX', deploy: 'Windows GPU API' },
        { capKey: 'vulkan', name: 'Vulkan Compute', formats: 'ONNX, GGUF (via vulkan)', deploy: 'Cross-platform' },
        { capKey: 'fastflowlm', name: 'FastFlowLM NPU', formats: 'FLM (NPU Optimized)', deploy: 'Ryzen AI Runtime' },
        { capKey: 'cpu', name: 'CPU Inference', formats: 'All formats', deploy: 'API, Edge' },
    ];

    return (
        <div className="card mt-6">
            <div className="card-header">
                <h3 className="card-title">Hardware Compatibility</h3>
                <Server size={18} className="text-secondary" />
            </div>
            <div className="table-responsive">
                <table className="props-table">
                    <thead>
                        <tr>
                            <th>Hardware Target</th>
                            <th>Supported Formats</th>
                            <th>Deployment</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {hwMap.map((row, i) => {
                            const cap = capabilities?.[row.capKey];
                            const detected = cap?.available ?? false;
                            return (
                                <tr key={i}>
                                    <td style={{ fontWeight: 600 }}>{row.name}</td>
                                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '13px' }}>{row.formats}</td>
                                    <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{row.deploy}</td>
                                    <td style={{ fontSize: '13px' }}>
                                        {detected ? (
                                            <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>✅ Detected</span>
                                        ) : (
                                            <span style={{ color: 'var(--text-muted)' }}>— Not installed</span>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
