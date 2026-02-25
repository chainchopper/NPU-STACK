import React, { useState, useEffect } from 'react';
import { Gauge, Play, BarChart3 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell } from 'recharts';
import { listModels, runBenchmark, listBenchmarks } from '../api/client';

const COLORS = ['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444'];

export default function Benchmark() {
    const [models, setModels] = useState([]);
    const [benchmarks, setBenchmarks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [running, setRunning] = useState(false);
    const [latestResult, setLatestResult] = useState(null);

    const [form, setForm] = useState({
        model_id: '',
        runtime: 'onnxruntime',
        device: 'cpu',
        batch_size: 1,
        warmup_runs: 10,
        num_iterations: 100,
    });

    useEffect(() => {
        Promise.all([
            listModels().catch(() => []),
            listBenchmarks().catch(() => []),
        ]).then(([m, b]) => {
            setModels(m);
            setBenchmarks(b);
            setLoading(false);
        });
    }, []);

    const handleRun = async (e) => {
        e.preventDefault();
        setRunning(true);
        setLatestResult(null);
        try {
            const result = await runBenchmark({
                model_id: Number(form.model_id),
                runtime: form.runtime,
                device: form.device,
                batch_size: form.batch_size,
                warmup_runs: form.warmup_runs,
                num_iterations: form.num_iterations,
            });
            setLatestResult(result);
            listBenchmarks().then(setBenchmarks);
        } catch (e) {
            alert('Benchmark failed: ' + e.message);
        }
        setRunning(false);
    };

    // Prepare chart data from benchmarks
    const chartData = benchmarks.slice(0, 10).map((b, i) => ({
        name: `${b.model_name.slice(0, 20)}`,
        latency: b.latency_mean_ms,
        throughput: b.throughput_fps,
        fill: COLORS[i % COLORS.length],
    }));

    return (
        <div>
            <div className="page-header">
                <h2>Benchmark Lab</h2>
                <p>Profile and compare model inference performance across devices and runtimes</p>
            </div>

            <div className="grid-2">
                {/* Benchmark Config */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Run Benchmark</h3>
                    </div>
                    <form onSubmit={handleRun}>
                        <div className="form-group">
                            <label className="form-label">Model</label>
                            <select className="form-select" value={form.model_id} onChange={e => setForm({ ...form, model_id: e.target.value })} required>
                                <option value="">Select a model...</option>
                                {models.filter(m => ['onnx', 'openvino_ir'].includes(m.format)).map(m => (
                                    <option key={m.id} value={m.id}>{m.name} ({m.format})</option>
                                ))}
                            </select>
                        </div>
                        <div className="form-row">
                            <div className="form-group">
                                <label className="form-label">Runtime</label>
                                <select className="form-select" value={form.runtime} onChange={e => setForm({ ...form, runtime: e.target.value })}>
                                    <option value="onnxruntime">ONNX Runtime</option>
                                    <option value="openvino">OpenVINO Runtime</option>
                                </select>
                            </div>
                            <div className="form-group">
                                <label className="form-label">Device</label>
                                <select className="form-select" value={form.device} onChange={e => setForm({ ...form, device: e.target.value })}>
                                    <option value="cpu">CPU</option>
                                    <option value="npu">NPU (Intel)</option>
                                    <option value="cuda">CUDA GPU</option>
                                    <option value="auto">AUTO</option>
                                </select>
                            </div>
                        </div>
                        <div className="form-row">
                            <div className="form-group">
                                <label className="form-label">Batch Size</label>
                                <input type="number" className="form-input" value={form.batch_size} min={1} max={64} onChange={e => setForm({ ...form, batch_size: Number(e.target.value) })} />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Iterations</label>
                                <input type="number" className="form-input" value={form.num_iterations} min={10} max={10000} onChange={e => setForm({ ...form, num_iterations: Number(e.target.value) })} />
                            </div>
                        </div>
                        <button type="submit" className="btn btn-primary" disabled={running || !form.model_id} style={{ width: '100%', justifyContent: 'center' }}>
                            <Play size={16} />
                            {running ? 'Running benchmark...' : 'Run Benchmark'}
                        </button>
                    </form>
                </div>

                {/* Latest Result */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="card-title">Latest Result</h3>
                    </div>
                    {latestResult ? (
                        <div>
                            <div style={{ marginBottom: '16px' }}>
                                <span className="badge badge-success">✅ Complete</span>
                                <span className="badge badge-info" style={{ marginLeft: '8px' }}>{latestResult.runtime}</span>
                                <span className="badge badge-purple" style={{ marginLeft: '8px' }}>{latestResult.device || latestResult.active_provider}</span>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                <ResultCard label="Mean Latency" value={`${latestResult.latency_mean_ms} ms`} accent="blue" />
                                <ResultCard label="Throughput" value={`${latestResult.throughput_fps} FPS`} accent="green" />
                                <ResultCard label="P95 Latency" value={`${latestResult.latency_p95_ms} ms`} accent="purple" />
                                <ResultCard label="Peak Memory" value={`${latestResult.memory_peak_mb} MB`} accent="amber" />
                            </div>
                            <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <MetricRow label="P50 Latency" value={`${latestResult.latency_p50_ms} ms`} />
                                <MetricRow label="P99 Latency" value={`${latestResult.latency_p99_ms} ms`} />
                                <MetricRow label="Min Latency" value={`${latestResult.latency_min_ms} ms`} />
                                <MetricRow label="Max Latency" value={`${latestResult.latency_max_ms} ms`} />
                            </div>
                        </div>
                    ) : (
                        <div className="empty-state" style={{ padding: '32px' }}>
                            <Gauge size={36} />
                            <p className="text-secondary">Run a benchmark to see results</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Comparison Chart */}
            {chartData.length > 0 && (
                <div className="card mt-6">
                    <div className="card-header">
                        <h3 className="card-title">Performance Comparison</h3>
                        <BarChart3 size={18} className="text-secondary" />
                    </div>
                    <div className="grid-2">
                        <div>
                            <h4 style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '12px' }}>Latency (ms) — Lower is better</h4>
                            <ResponsiveContainer width="100%" height={250}>
                                <BarChart data={chartData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                                    <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={11} angle={-20} textAnchor="end" height={60} />
                                    <YAxis stroke="var(--text-muted)" fontSize={12} />
                                    <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '8px' }} />
                                    <Bar dataKey="latency" radius={[4, 4, 0, 0]}>
                                        {chartData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                        <div>
                            <h4 style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '12px' }}>Throughput (FPS) — Higher is better</h4>
                            <ResponsiveContainer width="100%" height={250}>
                                <BarChart data={chartData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                                    <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={11} angle={-20} textAnchor="end" height={60} />
                                    <YAxis stroke="var(--text-muted)" fontSize={12} />
                                    <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '8px' }} />
                                    <Bar dataKey="throughput" radius={[4, 4, 0, 0]}>
                                        {chartData.map((entry, i) => <Cell key={i} fill={COLORS[(i + 2) % COLORS.length]} />)}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            )}

            {/* History Table */}
            <div className="card mt-6">
                <div className="card-header">
                    <h3 className="card-title">Benchmark History</h3>
                </div>
                {benchmarks.length === 0 ? (
                    <p className="text-secondary">No benchmarks recorded yet</p>
                ) : (
                    <div className="table-container" style={{ border: 'none' }}>
                        <table>
                            <thead>
                                <tr>
                                    <th>Model</th>
                                    <th>Runtime</th>
                                    <th>Device</th>
                                    <th>Precision</th>
                                    <th>Latency (ms)</th>
                                    <th>P95 (ms)</th>
                                    <th>Throughput</th>
                                    <th>Memory</th>
                                    <th>Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {benchmarks.map(b => (
                                    <tr key={b.id}>
                                        <td style={{ fontWeight: 500 }}>{b.model_name}</td>
                                        <td><span className="badge badge-info">{b.runtime}</span></td>
                                        <td className="text-mono">{b.device}</td>
                                        <td><span className={`badge ${b.precision === 'fp32' ? 'badge-purple' : 'badge-success'}`}>{b.precision}</span></td>
                                        <td className="text-mono">{b.latency_mean_ms}</td>
                                        <td className="text-mono">{b.latency_p95_ms}</td>
                                        <td className="text-mono">{b.throughput_fps} FPS</td>
                                        <td className="text-mono">{b.memory_peak_mb} MB</td>
                                        <td className="text-secondary">{new Date(b.created_at).toLocaleDateString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}

function ResultCard({ label, value, accent }) {
    return (
        <div style={{
            padding: '16px',
            background: `var(--accent-${accent}-glow)`,
            borderRadius: '10px',
            textAlign: 'center',
        }}>
            <div style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: `var(--accent-${accent})` }}>{value}</div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>{label}</div>
        </div>
    );
}

function MetricRow({ label, value }) {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
            <span style={{ color: 'var(--text-tertiary)' }}>{label}</span>
            <span className="text-mono">{value}</span>
        </div>
    );
}
