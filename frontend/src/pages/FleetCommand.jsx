import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Send, RefreshCw, Copy, Download, AlertCircle, CheckCircle,
  Clock, Zap, Shield, Wifi, Cpu, Terminal, ChevronDown, ChevronUp,
} from 'lucide-react';

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

        // Add assistant response
        const assistantMsg = {
          id: `msg-${Date.now()}`,
          role: 'assistant',
          content: `Command parsed as: **${result.intent.toUpperCase()}**
Intent: ${parsedCmd.intent}
Targets: ${parsedCmd.target_devices.join(', ')}
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

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 80px)', background: '#f8f9fa' }}>
      {/* Sidebar: Fleet Status */}
      <div style={{ width: 280, borderRight: '1px solid #e0e0e0', background: '#fff', overflow: 'auto' }}>
        <div style={{ padding: 16 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 600 }}>Fleet Status</h3>
          {fleetStatus ? (
            <div style={{ fontSize: 12, lineHeight: 1.8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <Cpu size={14} style={{ color: '#2196F3' }} />
                <span>Total: {fleetStatus.total}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <Zap size={14} style={{ color: '#4CAF50' }} />
                <span>Online: {fleetStatus.online}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Shield size={14} style={{ color: '#FF9800' }} />
                <span>Paired: {fleetStatus.paired}</span>
              </div>
            </div>
          ) : (
            <div style={{ color: '#999', fontSize: 12 }}>Loading fleet status...</div>
          )}

          <div style={{ margin: '16px 0 0 0', paddingTop: 12, borderTop: '1px solid #f0f0f0' }}>
            <button
              onClick={refreshFleetStatus}
              style={{
                width: '100%',
                padding: '8px 12px',
                fontSize: 12,
                border: '1px solid #e0e0e0',
                background: '#f5f5f5',
                borderRadius: 4,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
              }}
            >
              <RefreshCw size={12} />
              Refresh Status
            </button>
          </div>

          {/* Device List */}
          {fleetStatus && fleetStatus.devices.length > 0 && (
            <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #f0f0f0' }}>
              <h4 style={{ margin: '0 0 8px 0', fontSize: 12, fontWeight: 600 }}>Devices</h4>
              <div style={{ fontSize: 11, maxHeight: 300, overflow: 'auto' }}>
                {fleetStatus.devices.map((d) => (
                  <div
                    key={d.device_id}
                    style={{
                      padding: '6px 8px',
                      marginBottom: 4,
                      background: '#f5f5f5',
                      borderRadius: 3,
                      borderLeft: '3px solid ' + (d.status === 'online' ? '#4CAF50' : '#999'),
                    }}
                  >
                    <div style={{ fontWeight: 500 }}>{d.family.toUpperCase()}</div>
                    <div style={{ color: '#666', fontSize: 10 }}>{d.chip}</div>
                    <div style={{ color: '#999', fontSize: 10 }}>
                      {d.status} • {d.connection_type}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main: Chat + Job Matrix */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Chat Messages */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: 16,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          {messages.map((msg) => (
            <div key={msg.id}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <div
                  style={{
                    maxWidth: '70%',
                    padding: '12px 16px',
                    borderRadius: 8,
                    background: msg.role === 'user' ? '#2196F3' : '#f0f0f0',
                    color: msg.role === 'user' ? '#fff' : '#333',
                    fontSize: 13,
                    lineHeight: 1.5,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {msg.content}
                </div>
              </div>
              {msg.isError && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    color: '#d32f2f',
                    fontSize: 12,
                    marginTop: 4,
                  }}
                >
                  <AlertCircle size={14} />
                  Error communicating with backend
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div style={{ display: 'flex', gap: 4 }}>
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: '#999',
                  animation: 'pulse 1s infinite',
                }}
              />
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: '#999',
                  animation: 'pulse 1s infinite 0.2s',
                }}
              />
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: '#999',
                  animation: 'pulse 1s infinite 0.4s',
                }}
              />
            </div>
          )}

          {templates.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#555', marginBottom: 8 }}>
                Quick Recipes
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {templates.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    onClick={() => handleSendCommand(template.example || template.label)}
                    style={{
                      border: '1px solid #dbe4ff',
                      background: '#eef4ff',
                      color: '#2457c5',
                      borderRadius: 999,
                      padding: '6px 10px',
                      fontSize: 11,
                      cursor: 'pointer',
                    }}
                  >
                    {template.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Job Results Matrix */}
        {jobResultsMatrix.length > 0 && (
          <div style={{ borderTop: '1px solid #e0e0e0', padding: 12, maxHeight: 200, overflowY: 'auto', background: '#fafafa' }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Job Results</div>
            {jobResultsMatrix.map((job) => (
              <div
                key={job.jobId}
                style={{
                  marginBottom: 8,
                  padding: 8,
                  background: '#fff',
                  borderRadius: 4,
                  border: '1px solid #e0e0e0',
                  cursor: 'pointer',
                }}
                onClick={() => setExpandedJobId(expandedJobId === job.jobId ? null : job.jobId)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1 }}>
                    {job.status === 'complete' ? (
                      <CheckCircle size={14} style={{ color: '#4CAF50' }} />
                    ) : job.status === 'failed' ? (
                      <AlertCircle size={14} style={{ color: '#d32f2f' }} />
                    ) : (
                      <Clock size={14} style={{ color: '#FF9800' }} />
                    )}
                    <span style={{ fontSize: 11, fontWeight: 500 }}>
                      {job.intent.toUpperCase()} ({job.targetCount} devices)
                    </span>
                    <span style={{ fontSize: 10, color: '#999' }}>
                      [{job.status}]
                    </span>
                  </div>
                  {expandedJobId === job.jobId ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </div>

                {expandedJobId === job.jobId && (
                  <div style={{ marginTop: 8, fontSize: 10, color: '#666' }}>
                    {Object.entries(job.resultsByDevice).map(([deviceId, result]) => (
                      <div key={deviceId} style={{ marginLeft: 8, padding: '4px 0' }}>
                        <strong>{deviceId}:</strong>{' '}
                        {typeof result === 'object' ? JSON.stringify(result) : String(result)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Input Area */}
        <div style={{ borderTop: '1px solid #e0e0e0', padding: 12, background: '#fff' }}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendCommand(userInput);
            }}
            style={{ display: 'flex', gap: 8 }}
          >
            <input
              type="text"
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="e.g., 'provision all ESP32 devices', 'update firmware on device-1', 'check fleet status'"
              disabled={loading}
              style={{
                flex: 1,
                padding: '10px 12px',
                fontSize: 13,
                border: '1px solid #e0e0e0',
                borderRadius: 4,
                outline: 'none',
              }}
              onFocus={(e) => (e.target.style.borderColor = '#2196F3')}
              onBlur={(e) => (e.target.style.borderColor = '#e0e0e0')}
            />
            <button
              type="submit"
              disabled={loading || !userInput.trim()}
              style={{
                padding: '10px 16px',
                fontSize: 13,
                fontWeight: 500,
                background: '#2196F3',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.6 : 1,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Send size={14} />
              Send
            </button>
          </form>
          <div style={{ fontSize: 11, color: '#999', marginTop: 8 }}>
            💡 Tip: Describe what you want to do naturally. The agent will parse your command and execute it on the fleet.
          </div>
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.6; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  );
};

export default FleetCommand;
