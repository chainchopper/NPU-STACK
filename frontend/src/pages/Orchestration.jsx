import React, { useEffect, useMemo, useState } from 'react';
import {
  getHermesConfig,
  updateHermesConfig,
  discoverMcpAssets,
  autoAddMcpServers,
  getNirvanaIdentity,
  updateNirvanaIdentity,
  getOrchestrationCapabilities,
  listAutoResearchProfiles,
  createAutoResearchProfile,
  deleteAutoResearchProfile,
  listAutoResearchRuns,
  createAutoResearchRun,
  updateAutoResearchRun,
  getSystemInfo,
} from '../api/client';

const defaultProfile = {
  name: '',
  objective: '',
  max_iterations: 3,
  time_budget_minutes: 30,
  safety_mode: 'strict',
};

const statusColors = {
  queued: 'var(--accent-amber)',
  running: 'var(--accent-blue)',
  completed: 'var(--accent-green)',
  failed: 'var(--accent-red)',
  cancelled: 'var(--text-muted)',
};

export default function Orchestration() {
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [sysInfo, setSysInfo] = useState(null);

  const [nirvana, setNirvana] = useState({
    agent_name: 'Nirvana',
    agent_brand: 'NPU-STACK',
    identity_statement: '',
    mission: '',
  });

  const [hermesConfig, setHermesConfig] = useState({
    enabled: false,
    api_base: 'http://localhost:11437/v1',
    default_provider: 'openai-compatible',
    default_model: '',
    tool_policy: 'approval-required',
    mcp_servers: [],
  });
  const [hermesRuntime, setHermesRuntime] = useState(null);
  const [mcpInput, setMcpInput] = useState('');
  const [capabilities, setCapabilities] = useState({ tools: [], skills: [], mcp: {} });
  const [mcpDiscovery, setMcpDiscovery] = useState({ servers: [], tools: [], skills: [], configured_servers: [] });

  const [profiles, setProfiles] = useState([]);
  const [runs, setRuns] = useState([]);
  const [profileDraft, setProfileDraft] = useState(defaultProfile);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [runNotes, setRunNotes] = useState('');

  const activeProfile = useMemo(
    () => profiles.find((p) => p.id === selectedProfileId) || null,
    [profiles, selectedProfileId]
  );

  const presentConfigPath = (path) => {
    if (!path) return '';
    return String(path)
      .replaceAll('.hermes', '.runtime')
      .replaceAll('\\hermes\\', '\\runtime\\')
      .replaceAll('/hermes/', '/runtime/');
  };

  const loadAll = async () => {
    setLoading(true);
    setError('');
    try {
      const [nirvanaResp, hermes, caps, profileData, runData, discovered, systemInfo] = await Promise.all([
        getNirvanaIdentity(),
        getHermesConfig(),
        getOrchestrationCapabilities(),
        listAutoResearchProfiles(),
        listAutoResearchRuns(50),
        discoverMcpAssets(),
        getSystemInfo().catch(() => null),
      ]);

      setSysInfo(systemInfo);

      setNirvana(nirvanaResp.identity || {});
      setHermesConfig(hermes.config || {});
      setHermesRuntime(hermes.runtime || null);
      setCapabilities(caps || { tools: [], skills: [], mcp: {} });
      setProfiles(profileData.profiles || []);
      setRuns(runData.runs || []);
      setMcpDiscovery(discovered || { servers: [], tools: [], skills: [], configured_servers: [] });

      if (!selectedProfileId && profileData.profiles?.length) {
        setSelectedProfileId(profileData.profiles[0].id);
      }
    } catch (e) {
      setError(e.message || 'Failed to load orchestration state');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const saveNirvana = async () => {
    setError('');
    setNotice('');
    try {
      const result = await updateNirvanaIdentity({
        identity_statement: nirvana.identity_statement || '',
        mission: nirvana.mission || '',
      });
      setNirvana(result.identity || nirvana);
      setNotice('Nirvana identity updated.');
    } catch (e) {
      setError(e.message || 'Failed to save Nirvana identity');
    }
  };

  const saveHermes = async () => {
    setError('');
    setNotice('');
    try {
      const payload = {
        ...hermesConfig,
        mcp_servers: (hermesConfig.mcp_servers || []).filter(Boolean),
      };
      const result = await updateHermesConfig(payload);
      setHermesConfig(result.config || payload);
      setHermesRuntime(result.runtime || null);
      setNotice('Agent settings saved.');
    } catch (e) {
      setError(e.message || 'Failed to save agent settings');
    }
  };

  const addMcpServer = () => {
    const next = mcpInput.trim();
    if (!next) return;
    if ((hermesConfig.mcp_servers || []).includes(next)) {
      setMcpInput('');
      return;
    }
    setHermesConfig((prev) => ({
      ...prev,
      mcp_servers: [...(prev.mcp_servers || []), next],
    }));
    setMcpInput('');
  };

  const removeMcpServer = (server) => {
    setHermesConfig((prev) => ({
      ...prev,
      mcp_servers: (prev.mcp_servers || []).filter((item) => item !== server),
    }));
  };

  const oneClickAddDiscovered = async () => {
    setError('');
    setNotice('');
    try {
      const result = await autoAddMcpServers({});
      setHermesConfig((prev) => ({ ...prev, mcp_servers: result.mcp_servers || prev.mcp_servers || [] }));
      const discovered = await discoverMcpAssets();
      setMcpDiscovery(discovered || mcpDiscovery);
      setNotice(`Added ${result.count_added || 0} discovered MCP server(s).`);
    } catch (e) {
      setError(e.message || 'Failed to auto-add discovered MCP servers');
    }
  };

  const addSingleDiscoveredServer = async (serverId) => {
    setError('');
    setNotice('');
    try {
      const result = await autoAddMcpServers({ server_ids: [serverId] });
      setHermesConfig((prev) => ({ ...prev, mcp_servers: result.mcp_servers || prev.mcp_servers || [] }));
      const discovered = await discoverMcpAssets();
      setMcpDiscovery(discovered || mcpDiscovery);
      setNotice(result.count_added ? `Added ${serverId}.` : `${serverId} already configured.`);
    } catch (e) {
      setError(e.message || `Failed to add ${serverId}`);
    }
  };

  const submitProfile = async () => {
    if (!profileDraft.name.trim() || !profileDraft.objective.trim()) {
      setError('Profile name and objective are required.');
      return;
    }

    setError('');
    setNotice('');
    try {
      const result = await createAutoResearchProfile({
        ...profileDraft,
        name: profileDraft.name.trim(),
        objective: profileDraft.objective.trim(),
      });
      const created = result.profile;
      setProfiles((prev) => [created, ...prev]);
      setSelectedProfileId(created.id);
      setProfileDraft(defaultProfile);
      setNotice('AutoResearch profile created.');
    } catch (e) {
      setError(e.message || 'Failed to create profile');
    }
  };

  const removeProfile = async (profileId) => {
    setError('');
    setNotice('');
    try {
      await deleteAutoResearchProfile(profileId);
      setProfiles((prev) => prev.filter((p) => p.id !== profileId));
      if (selectedProfileId === profileId) {
        const remaining = profiles.filter((p) => p.id !== profileId);
        setSelectedProfileId(remaining[0]?.id || '');
      }
      setNotice('Profile removed.');
    } catch (e) {
      setError(e.message || 'Failed to remove profile');
    }
  };

  const queueRun = async () => {
    if (!selectedProfileId) {
      setError('Select a profile first.');
      return;
    }

    setError('');
    setNotice('');
    try {
      const result = await createAutoResearchRun({
        profile_id: selectedProfileId,
        notes: runNotes,
      });
      setRuns((prev) => [result.run, ...prev]);
      setRunNotes('');
      setNotice('Run queued.');
    } catch (e) {
      setError(e.message || 'Failed to queue run');
    }
  };

  const setRunStatus = async (runId, status) => {
    setError('');
    setNotice('');
    try {
      const result = await updateAutoResearchRun(runId, {
        status,
        result_summary: status === 'completed' ? 'Marked as completed from orchestration panel.' : null,
      });
      setRuns((prev) => prev.map((r) => (r.id === runId ? result.run : r)));
      setNotice(`Run updated to ${status}.`);
    } catch (e) {
      setError(e.message || 'Failed to update run');
    }
  };

  return (
    <div>
      <div className="page-header">
        <h2>Orchestration</h2>
        <p>
          Global Nirvana orchestration control plane with AutoResearch extension.
        </p>
      </div>

      {notice && (
        <div className="card" style={{ marginBottom: 12, borderColor: 'var(--accent-green)' }}>
          <div style={{ color: 'var(--accent-green)', fontSize: 13 }}>{notice}</div>
        </div>
      )}
      {error && (
        <div className="card" style={{ marginBottom: 12, borderColor: 'var(--accent-red)' }}>
          <div style={{ color: 'var(--accent-red)', fontSize: 13 }}>{error}</div>
        </div>
      )}

      {/* Runtime Recommendations */}
      {sysInfo && (
        <div className="card" style={{ marginBottom: 16, border: '2px solid #667eea', background: 'linear-gradient(135deg, rgba(102,126,234,0.08) 0%, rgba(102,126,234,0.04) 100%)' }}>
          <div className="card-header">
            <h3 className="card-title">Runtime Recommendations</h3>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
            {(sysInfo.amd_npu_available || (sysInfo.npu_available && sysInfo.processor?.toLowerCase?.()?.includes('ryzen'))) && (
              <div style={{ padding: 12, borderRadius: 8, background: 'rgba(102,126,234,0.1)', border: '1px solid rgba(102,126,234,0.3)' }}>
                <div style={{ fontWeight: 700, marginBottom: 6, color: '#667eea' }}>⚡ FastFlowLM (Ryzen AI NPU)</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                  Optimized for AMD Ryzen AI NPU. 10x power-efficient inference.
                </div>
                <a href="/fastflowlm" style={{ fontSize: 12, color: '#667eea', textDecoration: 'none', fontWeight: 700, cursor: 'pointer' }}>
                  Open FastFlowLM →
                </a>
              </div>
            )}
            {sysInfo.cuda_available && (
              <div style={{ padding: 12, borderRadius: 8, background: 'rgba(0,176,240,0.1)', border: '1px solid rgba(0,176,240,0.3)' }}>
                <div style={{ fontWeight: 700, marginBottom: 6, color: '#00b0f0' }}>🎮 NVIDIA CUDA</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                  {sysInfo.cuda_device} available for GPU-accelerated inference.
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {sysInfo.cuda_device_count} device(s) • {sysInfo.cuda_memory_gb} GB
                </div>
              </div>
            )}
            {sysInfo.rocm_available && (
              <div style={{ padding: 12, borderRadius: 8, background: 'rgba(240,128,0,0.1)', border: '1px solid rgba(240,128,0,0.3)' }}>
                <div style={{ fontWeight: 700, marginBottom: 6, color: '#f08000' }}>🔴 AMD ROCm</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                  AMD GPU acceleration via HIP runtime.
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  ROCm {sysInfo.rocm_version}
                </div>
              </div>
            )}
            {sysInfo.flm_available && (
              <div style={{ padding: 12, borderRadius: 8, background: 'rgba(76,175,80,0.1)', border: '1px solid rgba(76,175,80,0.3)' }}>
                <div style={{ fontWeight: 700, marginBottom: 6, color: '#4caf50' }}>✅ FastFlowLM Ready</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                  FastFlowLM runtime is installed and available.
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  Version {sysInfo.flm_version || 'latest'}
                </div>
              </div>
            )}
            {sysInfo.openvino_devices && sysInfo.openvino_devices.length > 0 && (
              <div style={{ padding: 12, borderRadius: 8, background: 'rgba(33,150,243,0.1)', border: '1px solid rgba(33,150,243,0.3)' }}>
                <div style={{ fontWeight: 700, marginBottom: 6, color: '#2196f3' }}>🚀 OpenVINO</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                  Intel optimization framework for CPUs & NPUs.
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {sysInfo.openvino_devices.join(', ')}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Nirvana Identity</h3>
          </div>

          {loading ? (
            <p className="text-muted">Loading Nirvana identity…</p>
          ) : (
            <>
              <div className="text-muted" style={{ fontSize: 12, marginBottom: 10 }}>
                Brand and agent name are locked at runtime (Nirvana / NPU-STACK).
              </div>
              <div className="form-group">
                <label className="form-label">Identity Statement</label>
                <textarea
                  className="form-input"
                  rows={4}
                  value={nirvana.identity_statement || ''}
                  onChange={(e) => setNirvana((prev) => ({ ...prev, identity_statement: e.target.value }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Mission</label>
                <textarea
                  className="form-input"
                  rows={2}
                  value={nirvana.mission || ''}
                  onChange={(e) => setNirvana((prev) => ({ ...prev, mission: e.target.value }))}
                />
              </div>
              <button className="btn btn-primary" onClick={saveNirvana}>Save Nirvana Identity</button>
            </>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Nirvana Agent Configuration</h3>
          </div>
          {loading ? (
            <p className="text-muted">Loading settings…</p>
          ) : (
            <>
              <div className="form-group">
                <label className="form-label">Enable Nirvana Agent</label>
                <input
                  type="checkbox"
                  checked={Boolean(hermesConfig.enabled)}
                  onChange={(e) => setHermesConfig((prev) => ({ ...prev, enabled: e.target.checked }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">API Base</label>
                <input
                  className="form-input"
                  value={hermesConfig.api_base || ''}
                  onChange={(e) => setHermesConfig((prev) => ({ ...prev, api_base: e.target.value }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Default Provider</label>
                <input
                  className="form-input"
                  value={hermesConfig.default_provider || ''}
                  onChange={(e) => setHermesConfig((prev) => ({ ...prev, default_provider: e.target.value }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Default Model</label>
                <input
                  className="form-input"
                  value={hermesConfig.default_model || ''}
                  onChange={(e) => setHermesConfig((prev) => ({ ...prev, default_model: e.target.value }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Tool Policy</label>
                <select
                  className="form-select"
                  value={hermesConfig.tool_policy || 'approval-required'}
                  onChange={(e) => setHermesConfig((prev) => ({ ...prev, tool_policy: e.target.value }))}
                >
                  <option value="approval-required">approval-required</option>
                  <option value="allowlisted-only">allowlisted-only</option>
                  <option value="open">open</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">MCP Servers</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    className="form-input"
                    value={mcpInput}
                    onChange={(e) => setMcpInput(e.target.value)}
                    placeholder="e.g. github, filesystem, docker"
                  />
                  <button className="btn btn-secondary" onClick={addMcpServer}>Add</button>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                  {(hermesConfig.mcp_servers || []).map((server) => (
                    <span key={server} className="badge badge-info" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                      {server}
                      <button
                        onClick={() => removeMcpServer(server)}
                        style={{ border: 'none', background: 'transparent', color: 'inherit', cursor: 'pointer', padding: 0 }}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              </div>
              <button className="btn btn-primary" onClick={saveHermes}>Save Agent Settings</button>

              {hermesRuntime && (
                <details style={{ marginTop: 14 }} open>
                  <summary style={{ fontSize: 12, fontWeight: 700, cursor: 'pointer', color: 'var(--text-secondary)', marginBottom: 8 }}>
                    Runtime &amp; Config Sources
                  </summary>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {hermesRuntime.startup_warmup && (
                      <div>
                        <span style={{ opacity: 0.6 }}>Warmup: </span>
                        <span
                          className="badge"
                          style={{
                            borderColor: hermesRuntime.startup_warmup.ready ? 'var(--accent-green)' : hermesRuntime.startup_warmup.active ? 'var(--accent-blue)' : 'var(--accent-amber)',
                            color: hermesRuntime.startup_warmup.ready ? 'var(--accent-green)' : hermesRuntime.startup_warmup.active ? 'var(--accent-blue)' : 'var(--accent-amber)',
                          }}
                        >
                          {hermesRuntime.startup_warmup.ready
                            ? 'ready'
                            : hermesRuntime.startup_warmup.active
                              ? `retrying (${hermesRuntime.startup_warmup.attempts}/${hermesRuntime.startup_warmup.max_attempts})`
                              : 'idle'}
                        </span>
                        <span style={{ marginLeft: 8, opacity: 0.75 }}>{hermesRuntime.startup_warmup.detail}</span>
                      </div>
                    )}
                    <div>
                      <span style={{ opacity: 0.6 }}>CLI: </span>
                      {hermesRuntime.cli_installed
                        ? <span style={{ color: 'var(--accent-green)' }}>✓ {hermesRuntime.cli_path}</span>
                        : <span style={{ color: 'var(--accent-amber)' }}>not found in PATH</span>}
                    </div>
                    <div>
                      <span style={{ opacity: 0.6 }}>API: </span>
                      {hermesRuntime.api_configured
                        ? <span style={{ color: 'var(--accent-green)' }}>✓ {hermesRuntime.api_base}</span>
                        : <span style={{ color: 'var(--accent-red)' }}>not configured</span>}
                    </div>

                    {hermesRuntime.config_sources && (
                      <>
                        <div style={{ marginTop: 8, fontWeight: 700, opacity: 0.8 }}>Detected config files:</div>
                        {hermesRuntime.config_sources.existing_paths?.length
                          ? hermesRuntime.config_sources.existing_paths.map((p) => (
                            <div key={p} style={{ color: 'var(--accent-green)', paddingLeft: 8 }}>✓ {presentConfigPath(p)}</div>
                          ))
                          : <div style={{ paddingLeft: 8, opacity: 0.5 }}>None found</div>}

                        <div style={{ marginTop: 8, fontWeight: 700, opacity: 0.8 }}>Checked locations:</div>
                        {hermesRuntime.config_sources.checked_paths?.map((p) => {
                          const found = hermesRuntime.config_sources.existing_paths?.includes(p);
                          return (
                            <div key={p} style={{ paddingLeft: 8, opacity: found ? 1 : 0.35 }}>
                              {found ? '✓' : '·'} {presentConfigPath(p)}
                            </div>
                          );
                        })}

                        <div style={{ marginTop: 8, fontWeight: 700, opacity: 0.8 }}>Env variables:</div>
                        {Object.entries(hermesRuntime.config_sources.env_variables || {})
                          .filter(([k]) => k.startsWith('NIRVANA_'))
                          .map(([k, v]) => (
                          <div key={k} style={{ paddingLeft: 8 }}>
                            <span style={{ opacity: 0.6 }}>{k}: </span>
                            {v
                              ? <span style={{ color: 'var(--accent-blue)' }}>{v}</span>
                              : <span style={{ opacity: 0.35 }}>not set</span>}
                          </div>
                        ))}

                        <div style={{ marginTop: 8, fontWeight: 700, opacity: 0.8 }}>Resolved sources:</div>
                        {Object.entries(hermesRuntime.config_sources.resolved_env || {}).map(([k, v]) => (
                          <div key={k} style={{ paddingLeft: 8 }}>
                            <span style={{ opacity: 0.6 }}>{k}: </span>
                            <span style={{ color: 'var(--accent-green)' }}>
                              {(v?.source && String(v.source).startsWith('NIRVANA_')) ? v.source : (v?.source ? 'legacy alias' : 'not set')}
                            </span>
                          </div>
                        ))}

                        <div style={{ marginTop: 8, fontWeight: 700, opacity: 0.8 }}>Effective config:</div>
                        {Object.entries(hermesRuntime.config_sources.effective || {}).map(([k, v]) => (
                          <div key={k} style={{ paddingLeft: 8 }}>
                            <span style={{ opacity: 0.6 }}>{k}: </span>
                            {v
                              ? <span style={{ color: 'var(--accent-green)' }}>{v}</span>
                              : <span style={{ opacity: 0.35 }}>—</span>}
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                </details>
              )}

              <details style={{ marginTop: 14 }} open>
                <summary style={{ fontSize: 12, fontWeight: 700, cursor: 'pointer', color: 'var(--text-secondary)', marginBottom: 8 }}>
                  MCP Discovery (Servers, Tools, Skills)
                </summary>
                <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                  <button className="btn btn-secondary" onClick={oneClickAddDiscovered}>One-click add discovered defaults</button>
                  <button className="btn btn-secondary" onClick={loadAll}>Rescan</button>
                </div>

                <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Servers</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
                  {(mcpDiscovery.servers || []).map((srv) => (
                    <div key={`${srv.id}-${srv.path || 'na'}`} className="card" style={{ margin: 0, padding: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                        <div>
                          <div style={{ fontWeight: 700 }}>{srv.label || srv.id}</div>
                          <div className="text-muted" style={{ fontSize: 12 }}>
                            {srv.id} · {srv.source}
                            {srv.path ? ` · ${presentConfigPath(srv.path)}` : ''}
                          </div>
                        </div>
                        <button
                          className="btn btn-secondary"
                          disabled={Boolean(srv.already_configured)}
                          onClick={() => addSingleDiscoveredServer(srv.id)}
                        >
                          {srv.already_configured ? 'Configured' : 'Add'}
                        </button>
                      </div>
                    </div>
                  ))}
                  {(mcpDiscovery.servers || []).length === 0 && <div className="text-muted">No servers discovered yet.</div>}
                </div>

                <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Tools</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                  {(mcpDiscovery.tools || []).map((tool) => (
                    <span key={tool.id} className="badge badge-info">{tool.id}</span>
                  ))}
                  {(mcpDiscovery.tools || []).length === 0 && <div className="text-muted">No local MCP tool definitions discovered.</div>}
                </div>

                <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Skills</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {(mcpDiscovery.skills || []).slice(0, 40).map((skill) => (
                    <div key={`${skill.id}-${skill.path}`} className="text-muted" style={{ fontSize: 12 }}>
                      • {skill.id} <span style={{ opacity: 0.7 }}>({skill.source})</span>
                    </div>
                  ))}
                  {(mcpDiscovery.skills || []).length > 40 && (
                    <div className="text-muted" style={{ fontSize: 12 }}>…and {(mcpDiscovery.skills || []).length - 40} more</div>
                  )}
                  {(mcpDiscovery.skills || []).length === 0 && <div className="text-muted">No skills discovered in common paths.</div>}
                </div>
              </details>
            </>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-header">
          <h3 className="card-title">Capabilities Catalog (Tools, Skills, MCP)</h3>
        </div>
        <div className="grid-2" style={{ gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Tools</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {(capabilities.tools || []).map((tool) => (
                <div key={tool.id} className="card" style={{ margin: 0 }}>
                  <div style={{ fontWeight: 700 }}>{tool.label}</div>
                  <div className="text-muted" style={{ fontSize: 12 }}>{tool.scope}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Skills</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {(capabilities.skills || []).map((skill) => (
                <div key={skill.id} className="card" style={{ margin: 0 }}>
                  <div style={{ fontWeight: 700 }}>{skill.label}</div>
                  <div className="text-muted" style={{ fontSize: 12 }}>{skill.description}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 16, alignItems: 'start' }}>
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">AutoResearch Profiles</h3>
          </div>
          <div className="form-group">
            <label className="form-label">Profile Name</label>
            <input
              className="form-input"
              value={profileDraft.name}
              onChange={(e) => setProfileDraft((prev) => ({ ...prev, name: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Objective</label>
            <textarea
              className="form-input"
              rows={3}
              value={profileDraft.objective}
              onChange={(e) => setProfileDraft((prev) => ({ ...prev, objective: e.target.value }))}
            />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div className="form-group">
              <label className="form-label">Max Iterations</label>
              <input
                type="number"
                className="form-input"
                min={1}
                max={200}
                value={profileDraft.max_iterations}
                onChange={(e) => setProfileDraft((prev) => ({ ...prev, max_iterations: Number(e.target.value || 1) }))}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Time Budget (min)</label>
              <input
                type="number"
                className="form-input"
                min={1}
                max={1440}
                value={profileDraft.time_budget_minutes}
                onChange={(e) => setProfileDraft((prev) => ({ ...prev, time_budget_minutes: Number(e.target.value || 1) }))}
              />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Safety Mode</label>
            <select
              className="form-select"
              value={profileDraft.safety_mode}
              onChange={(e) => setProfileDraft((prev) => ({ ...prev, safety_mode: e.target.value }))}
            >
              <option value="strict">strict</option>
              <option value="balanced">balanced</option>
              <option value="experimental">experimental</option>
            </select>
          </div>
          <button className="btn btn-primary" onClick={submitProfile}>Create Profile</button>
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {profiles.map((p) => (
              <div key={p.id} className="card" style={{ margin: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 8 }}>
                  <div>
                    <div style={{ fontWeight: 700 }}>{p.name}</div>
                    <div className="text-muted" style={{ fontSize: 12 }}>{p.objective}</div>
                  </div>
                  {p.id !== 'baseline-quick-loop' && (
                    <button className="btn btn-secondary" onClick={() => removeProfile(p.id)}>Remove</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">AutoResearch Runs</h3>
          </div>
          <div className="form-group">
            <label className="form-label">Profile</label>
            <select className="form-select" value={selectedProfileId} onChange={(e) => setSelectedProfileId(e.target.value)}>
              <option value="">Select profile…</option>
              {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          {activeProfile && (
            <div className="card" style={{ marginBottom: 12 }}>
              <div className="text-muted" style={{ fontSize: 12 }}>{activeProfile.objective}</div>
            </div>
          )}
          <div className="form-group">
            <label className="form-label">Notes</label>
            <textarea className="form-input" rows={2} value={runNotes} onChange={(e) => setRunNotes(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={queueRun}>Queue Run</button>

          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {runs.map((run) => (
              <div key={run.id} className="card" style={{ margin: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontWeight: 700 }}>{run.profile_name}</div>
                    <div className="text-muted" style={{ fontSize: 12 }}>Run ID: {run.id}</div>
                  </div>
                  <span
                    className="badge"
                    style={{ color: statusColors[run.status] || 'var(--text-secondary)', borderColor: statusColors[run.status] || 'var(--border-color)' }}
                  >
                    {run.status}
                  </span>
                </div>
                <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <button className="btn btn-secondary" onClick={() => setRunStatus(run.id, 'running')}>Mark running</button>
                  <button className="btn btn-secondary" onClick={() => setRunStatus(run.id, 'completed')}>Mark done</button>
                  <button className="btn btn-secondary" onClick={() => setRunStatus(run.id, 'failed')}>Mark failed</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
