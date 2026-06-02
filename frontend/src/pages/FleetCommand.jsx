import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Send, RefreshCw, AlertCircle, CheckCircle,
  Clock, Zap, Shield, Cpu, ChevronDown, ChevronUp,
} from 'lucide-react';

function flattenEntries(value, prefix = '', acc = []) {
  if (value == null) return acc;

  if (Array.isArray(value)) {
    value.forEach((entry, index) => flattenEntries(entry, `${prefix}[${index}]`, acc));
    return acc;
  }

  if (typeof value === 'object') {
    Object.entries(value).forEach(([key, entry]) => {
      const nextKey = prefix ? `${prefix}.${key}` : key;
      flattenEntries(entry, nextKey, acc);
    });
    return acc;
  }

  acc.push([prefix || 'value', value]);
  return acc;
}

function formatValue(value) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (value == null || value === '') {
    return '—';
  }
  return String(value);
}

function summarizeResult(result) {
  if (!result || typeof result !== 'object') return 'No result payload';

  if (result.latest?.telemetry || result.registry_telemetry) {
    const entryCount = flattenEntries(result.latest?.telemetry || result.registry_telemetry).length;
    return `Telemetry snapshot • ${entryCount} metric${entryCount === 1 ? '' : 's'} • history ${result.history_count || 0}`;
  }

  if (result.stdout) {
    return result.stdout.trim().split('\n')[0].slice(0, 120);
  }

  if (result.note) return result.note;
  if (result.message) return result.message;
  if (result.error) return result.error;
  return result.status || 'Result captured';
}

function describeIntent(intent) {
  switch (intent) {
    case 'telemetry':
      return 'Telemetry poll and sensor snapshot';
    case 'shell':
      return 'Manual command execution';
    case 'reboot':
      return 'Remote reboot request';
    case 'firmware':
      return 'Firmware workflow';
    case 'provision':
      return 'Provisioning workflow';
    default:
      return 'Fleet status orchestration';
  }
}

const FleetCommand = () => {
  const [userInput, setUserInput] = useState('');
  const [templates, setTemplates] = useState([]);
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Fleet Command Center ready. Use natural language to control your edge devices.',
      timestamp: new Date(),
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState({});
  const [fleetStatus, setFleetStatus] = useState(null);
  const [backendUrl] = useState(import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8010');
  const [expandedJobId, setExpandedJobId] = useState(null);

  const quickRecipes = useMemo(
    () => ([
      { id: 'telemetry-paired', label: 'Poll paired telemetry', prompt: 'refresh telemetry for all paired devices' },
      { id: 'linux-uptime', label: 'Run uptime on Linux edge', prompt: 'run "uptime" on all linux devices' },
      { id: 'fleet-status', label: 'Audit fleet health', prompt: 'show fleet health for all devices' },
      { id: 'reboot-linux', label: 'Reboot Linux edge nodes', prompt: 'reboot all linux devices' },
    ]),
    []
  );

  // ── Fleet Status Query ────────────────────────────────────

  const refreshFleetStatus = useCallback(async () => {
    try {
      const response = await fetch(`${backendUrl}/api/devices`);
      if (!response.ok) return;
      const data = await response.json();
      setFleetStatus({
        total: data.count || 0,
        online: (data.devices || []).filter(
          (d) => d.status === 'online' || d.status === 'reachable'
        ).length,
        paired: data.paired_count || 0,
        devices: data.devices || [],
      });
    } catch {
      // ignore
    }
  }, [backendUrl]);

  useEffect(() => {
    refreshFleetStatus();
    const interval = setInterval(refreshFleetStatus, 10000);
    return () => clearInterval(interval);
  }, [refreshFleetStatus]);

  useEffect(() => {
    const loadTemplates = async () => {
      try {
        const response = await fetch(`${backendUrl}/api/fleet/command/templates`);
        if (!response.ok) return;
        const data = await response.json();
        setTemplates(data.templates || []);
      } catch {
        // ignore
      }
    };

    loadTemplates();
  }, [backendUrl]);

  // ── Command Submission ────────────────────────────────────

  const handleSendCommand = useCallback(
    async (command) => {
      if (!command.trim()) return;

      // Add user message
      const userMsg = {
        id: `msg-${Date.now()}`,
        role: 'user',
        content: command,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setUserInput('');
      setLoading(true);

      try {
        // 1. Parse the command
        const parseResp = await fetch(`${backendUrl}/api/fleet/command/parse`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command, use_agent: true }),
        });

        if (!parseResp.ok) throw new Error('Parse failed');
        const parsedCmd = await parseResp.json();

        // 2. Execute the command
        const execResp = await fetch(`${backendUrl}/api/fleet/command/execute`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            parsed_command: parsedCmd,
            dry_run: false,
          }),
        });

        if (!execResp.ok) throw new Error('Execution failed');
        const result = await execResp.json();

        // Track the job
        setJobs((prev) => ({ ...prev, [result.job_id]: result }));
        setExpandedJobId(result.job_id);

        // Add assistant response
        const targetList = parsedCmd.target_devices?.length ? parsedCmd.target_devices.join(', ') : 'No devices resolved';
        const assistantMsg = {
          id: `msg-${Date.now()}`,
          role: 'assistant',
          content: `Command parsed as ${result.intent.toUpperCase()}.
Mode: ${describeIntent(parsedCmd.intent)}
Targets: ${targetList}
Job ID: ${result.job_id}
Confidence: ${(parsedCmd.confidence * 100).toFixed(0)}%

Reasoning: ${parsedCmd.reasoning_summary || 'Heuristic planner'}

Executing on ${result.target_count} device(s)...`,
          timestamp: new Date(),
          jobId: result.job_id,
          parsed: parsedCmd,
        };
        setMessages((prev) => [...prev, assistantMsg]);

        // Poll job status
        const pollInterval = setInterval(async () => {
          try {
            const statusResp = await fetch(`${backendUrl}/api/fleet/command/jobs/${result.job_id}`);
            if (!statusResp.ok) return;
            const jobStatus = await statusResp.json();
            setJobs((prev) => ({ ...prev, [result.job_id]: jobStatus }));

            if (jobStatus.status === 'complete' || jobStatus.status === 'failed') {
              clearInterval(pollInterval);
            }
          } catch {
            // ignore
          }
        }, 2000);
      } catch (error) {
        const errorMsg = {
          id: `msg-${Date.now()}`,
          role: 'assistant',
          content: `⚠️ Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
          timestamp: new Date(),
          isError: true,
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setLoading(false);
      }
    },
    [backendUrl]
  );

  // ── Job Result Matrix ─────────────────────────────────────

  const jobResultsMatrix = useMemo(() => {
    return Object.values(jobs).map((job) => ({
      jobId: job.job_id,
      intent: job.intent,
      status: job.status,
      targetCount: job.target_count,
      completedAt: job.completed_at,
      resultsByDevice: job.results_by_device || {},
    }));
  }, [jobs]);

  const telemetryCapableDevices = useMemo(
    () => (fleetStatus?.devices || []).filter((device) => device.capabilities?.telemetry || device.capabilities?.sensor_poll || device.telemetry).length,
    [fleetStatus]
  );

  return (
    <div>
      <div className="page-header">
        <h2>Fleet Command</h2>
        <p>Natural-language command center for edge fleet orchestration.</p>
      </div>

      <div className="metrics-grid" style={{ marginBottom: 16 }}>
        <div className="metric-card blue">
          <div className="metric-icon"><Cpu size={20} /></div>
          <div className="metric-value">{fleetStatus?.total ?? 0}</div>
          <div className="metric-label">Fleet Devices</div>
        </div>
        <div className="metric-card green">
          <div className="metric-icon"><Zap size={20} /></div>
          <div className="metric-value">{fleetStatus?.online ?? 0}</div>
          <div className="metric-label">Online</div>
        </div>
        <div className="metric-card amber">
          <div className="metric-icon"><Shield size={20} /></div>
          <div className="metric-value">{fleetStatus?.paired ?? 0}</div>
          <div className="metric-label">Paired</div>
        </div>
        <div className="metric-card purple">
          <div className="metric-icon"><RefreshCw size={20} /></div>
          <div className="metric-value">{telemetryCapableDevices}</div>
          <div className="metric-label">Telemetry Ready</div>
        </div>
      </div>

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <div className="card" style={{ maxHeight: 680, overflowY: 'auto' }}>
          <div className="card-header">
            <h3 className="card-title">Command Feed</h3>
            <button className="btn btn-secondary" onClick={refreshFleetStatus}>
              <RefreshCw size={14} /> Refresh Fleet
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {messages.map((msg) => (
              <div key={msg.id} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <div
                  className="card"
                  style={{
                    margin: 0,
                    maxWidth: '86%',
                    borderColor: msg.role === 'user' ? 'var(--accent-blue)' : 'var(--border-color)',
                    background: msg.role === 'user' ? 'var(--accent-blue-glow)' : 'var(--bg-secondary)',
                  }}
                >
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                    {msg.role === 'user' ? 'You' : 'Fleet Agent'}
                  </div>
                  <div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{msg.content}</div>
                </div>
              </div>
            ))}
            {loading && <div className="text-muted" style={{ fontSize: 12 }}>Running command…</div>}
          </div>

          {templates.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Quick Recipes</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {templates.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => handleSendCommand(template.example || template.label)}
                  >
                    {template.label}
                  </button>
                ))}
                {quickRecipes.map((recipe) => (
                  <button
                    key={recipe.id}
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => handleSendCommand(recipe.prompt)}
                  >
                    {recipe.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendCommand(userInput);
            }}
            style={{ display: 'flex', gap: 8, marginTop: 14 }}
          >
            <input
              type="text"
              className="form-input"
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="refresh telemetry for all paired devices"
              disabled={loading}
            />
            <button type="submit" className="btn btn-primary" disabled={loading || !userInput.trim()}>
              <Send size={14} /> Send
            </button>
          </form>
        </div>

        <div className="card" style={{ maxHeight: 680, overflowY: 'auto' }}>
          <div className="card-header">
            <h3 className="card-title">Execution Jobs</h3>
          </div>

          {jobResultsMatrix.length === 0 && (
            <div className="text-muted" style={{ fontSize: 12 }}>
              No command jobs yet. Send a command to populate execution telemetry.
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {jobResultsMatrix.map((job) => (
              <div
                key={job.jobId}
                className="card"
                style={{ margin: 0, cursor: 'pointer' }}
                onClick={() => setExpandedJobId(expandedJobId === job.jobId ? null : job.jobId)}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {job.status === 'complete' ? (
                      <CheckCircle size={15} style={{ color: 'var(--accent-green)' }} />
                    ) : job.status === 'failed' ? (
                      <AlertCircle size={15} style={{ color: 'var(--accent-red)' }} />
                    ) : (
                      <Clock size={15} style={{ color: 'var(--accent-amber)' }} />
                    )}
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 12 }}>{job.intent.toUpperCase()}</div>
                      <div className="text-muted" style={{ fontSize: 11 }}>{job.targetCount} target device(s) · {job.status} · {describeIntent(job.intent)}</div>
                    </div>
                  </div>
                  {expandedJobId === job.jobId ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </div>

                {expandedJobId === job.jobId && (
                  <div style={{ marginTop: 10, borderTop: '1px solid var(--border-color)', paddingTop: 8 }}>
                    {Object.entries(job.resultsByDevice).length === 0 && (
                      <div className="text-muted" style={{ fontSize: 12 }}>No per-device output captured yet.</div>
                    )}
                    {Object.entries(job.resultsByDevice).map(([deviceId, result]) => (
                      <div key={deviceId} style={{ fontSize: 12, marginBottom: 10, padding: 10, borderRadius: 10, background: 'var(--bg-secondary)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 6 }}>
                          <strong>{deviceId}</strong>
                          <span className="text-muted">{result?.transport || result?.source || result?.status || 'captured'}</span>
                        </div>
                        <div style={{ marginBottom: 6, color: 'var(--text-secondary)' }}>{summarizeResult(result)}</div>

                        {result?.latest?.telemetry && (
                          <div className="fleet-detail-grid" style={{ marginBottom: 6 }}>
                            {flattenEntries(result.latest.telemetry).slice(0, 10).map(([key, value]) => (
                              <React.Fragment key={`${job.jobId}-${deviceId}-${key}`}>
                                <span className="fleet-detail-label">{key}</span>
                                <span>{formatValue(value)}</span>
                              </React.Fragment>
                            ))}
                          </div>
                        )}

                        {result?.stdout && (
                          <div style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{result.stdout.trim()}</div>
                        )}
                        {result?.note && <div className="text-muted">{result.note}</div>}
                        {result?.error && <div style={{ color: 'var(--accent-red)' }}>{result.error}</div>}
                        {result?.stderr && <div style={{ color: 'var(--accent-amber)', whiteSpace: 'pre-wrap' }}>{result.stderr.trim()}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default FleetCommand;
