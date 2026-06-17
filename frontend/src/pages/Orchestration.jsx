import React, { useEffect, useState } from 'react';
import {
  getNirvanaRuntimeConfig,
  updateNirvanaRuntimeConfig,
  discoverMcpAssets,
  autoAddMcpServers,
  getNirvanaIdentity,
  updateNirvanaIdentity,
  getOrchestrationCapabilities,
  getSystemInfo,
} from '../api/client';

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

  const [nirvanaConfig, setNirvanaConfig] = useState({
    enabled: false,
    api_base: 'http://localhost:11437/v1',
    default_provider: 'openai-compatible',
    default_model: '',
    tool_policy: 'approval-required',
    mcp_servers: [],
  });
  const [nirvanaRuntime, setNirvanaRuntime] = useState(null);
  const [mcpInput, setMcpInput] = useState('');
  const [capabilities, setCapabilities] = useState({ tools: [], skills: [], mcp: {} });
  const [mcpDiscovery, setMcpDiscovery] = useState({ servers: [], tools: [], skills: [], configured_servers: [] });

  const presentConfigPath = (path) => {
    if (!path) return '';
    const legacyBrand = ['her', 'mes'].join('');
    return String(path)
      .replaceAll(`${legacyBrand}-agent`, 'nirvana-agent')
      .replaceAll(`${legacyBrand}.exe`, 'nirvana.exe')
      .replaceAll(`.${legacyBrand}`, '.nirvana')
      .replaceAll(`\\${legacyBrand}\\`, '\\nirvana\\')
      .replaceAll(`/${legacyBrand}/`, '/nirvana/');
  };

  const loadAll = async () => {
    setLoading(true);
    setError('');
    try {
      const [nirvanaResp, runtimeConfigResponse, caps, discovered, systemInfo] = await Promise.all([
        getNirvanaIdentity(),
        getNirvanaRuntimeConfig(),
        getOrchestrationCapabilities(),
        discoverMcpAssets(),
        getSystemInfo().catch(() => null),
      ]);

      setSysInfo(systemInfo);

      setNirvana(nirvanaResp.identity || {});
  setNirvanaConfig(runtimeConfigResponse.config || {});
  setNirvanaRuntime(runtimeConfigResponse.runtime || null);
      setCapabilities(caps || { tools: [], skills: [], mcp: {} });
      setMcpDiscovery(discovered || { servers: [], tools: [], skills: [], configured_servers: [] });
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

  const saveNirvanaRuntime = async () => {
    setError('');
    setNotice('');
    try {
      const payload = {
        ...nirvanaConfig,
        mcp_servers: (nirvanaConfig.mcp_servers || []).filter(Boolean),
      };
      const result = await updateNirvanaRuntimeConfig(payload);
      setNirvanaConfig(result.config || payload);
      setNirvanaRuntime(result.runtime || null);
      setNotice('Nirvana runtime settings saved.');
    } catch (e) {
      setError(e.message || 'Failed to save Nirvana runtime settings');
    }
  };

  const addMcpServer = () => {
    const next = mcpInput.trim();
    if (!next) return;
    if ((nirvanaConfig.mcp_servers || []).includes(next)) {
      setMcpInput('');
      return;
    }
    setNirvanaConfig((prev) => ({
      ...prev,
      mcp_servers: [...(prev.mcp_servers || []), next],
    }));
    setMcpInput('');
  };

  const removeMcpServer = (server) => {
    setNirvanaConfig((prev) => ({
      ...prev,
      mcp_servers: (prev.mcp_servers || []).filter((item) => item !== server),
    }));
  };

  const oneClickAddDiscovered = async () => {
    setError('');
    setNotice('');
    try {
      const result = await autoAddMcpServers({});
      setNirvanaConfig((prev) => ({ ...prev, mcp_servers: result.mcp_servers || prev.mcp_servers || [] }));
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
      setNirvanaConfig((prev) => ({ ...prev, mcp_servers: result.mcp_servers || prev.mcp_servers || [] }));
      const discovered = await discoverMcpAssets();
      setMcpDiscovery(discovered || mcpDiscovery);
      setNotice(result.count_added ? `Added ${serverId}.` : `${serverId} already configured.`);
    } catch (e) {
      setError(e.message || `Failed to add ${serverId}`);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h2>Orchestration</h2>
        <p>
          Control plane for Nirvana identity, local inference runtime, and MCP capabilities.
          Nirvana is always-on — this page configures its supporting infrastructure.
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
                Nirvana is the always-on system orchestrator. Brand name is locked at runtime.
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
            <h3 className="card-title">Local Inference Runtime</h3>
            <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>
              Optional local LLM bridge. Nirvana uses DeepSeek by default;
              enable this for an on-device fallback (Ollama, local GGUF, vLLM).
            </div>
          </div>
          {loading ? (
            <p className="text-muted">Loading settings…</p>
          ) : (
            <>
              <div className="form-group">
                <label className="form-label">Enable Local Fallback Runtime</label>
                <input
                  type="checkbox"
                  checked={Boolean(nirvanaConfig.enabled)}
                  onChange={(e) => setNirvanaConfig((prev) => ({ ...prev, enabled: e.target.checked }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">API Base</label>
                <input
                  className="form-input"
                  value={nirvanaConfig.api_base || ''}
                  onChange={(e) => setNirvanaConfig((prev) => ({ ...prev, api_base: e.target.value }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Default Provider</label>
                <input
                  className="form-input"
                  value={nirvanaConfig.default_provider || ''}
                  onChange={(e) => setNirvanaConfig((prev) => ({ ...prev, default_provider: e.target.value }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Default Model</label>
                <input
                  className="form-input"
                  value={nirvanaConfig.default_model || ''}
                  onChange={(e) => setNirvanaConfig((prev) => ({ ...prev, default_model: e.target.value }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Tool Policy</label>
                <select
                  className="form-select"
                  value={nirvanaConfig.tool_policy || 'approval-required'}
                  onChange={(e) => setNirvanaConfig((prev) => ({ ...prev, tool_policy: e.target.value }))}
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
                  {(nirvanaConfig.mcp_servers || []).map((server) => (
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
              <button className="btn btn-primary" onClick={saveNirvanaRuntime}>Save Runtime Settings</button>

              {nirvanaRuntime && (
                <details style={{ marginTop: 14 }} open>
                  <summary style={{ fontSize: 12, fontWeight: 700, cursor: 'pointer', color: 'var(--text-secondary)', marginBottom: 8 }}>
                    Runtime &amp; Config Sources
                  </summary>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {nirvanaRuntime.startup_warmup && (
                      <div>
                        <span style={{ opacity: 0.6 }}>Warmup: </span>
                        <span
                          className="badge"
                          style={{
                            borderColor: nirvanaRuntime.startup_warmup.ready ? 'var(--accent-green)' : nirvanaRuntime.startup_warmup.active ? 'var(--accent-blue)' : 'var(--accent-amber)',
                            color: nirvanaRuntime.startup_warmup.ready ? 'var(--accent-green)' : nirvanaRuntime.startup_warmup.active ? 'var(--accent-blue)' : 'var(--accent-amber)',
                          }}
                        >
                          {nirvanaRuntime.startup_warmup.ready
                            ? 'ready'
                            : nirvanaRuntime.startup_warmup.active
                              ? `retrying (${nirvanaRuntime.startup_warmup.attempts}/${nirvanaRuntime.startup_warmup.max_attempts})`
                              : 'idle'}
                        </span>
                        <span style={{ marginLeft: 8, opacity: 0.75 }}>{nirvanaRuntime.startup_warmup.detail}</span>
                      </div>
                    )}
                    <div>
                      <span style={{ opacity: 0.6 }}>CLI: </span>
                      {nirvanaRuntime.cli_installed
                        ? <span style={{ color: 'var(--accent-green)' }}>✓ {presentConfigPath(nirvanaRuntime.cli_path)}</span>
                        : <span style={{ color: 'var(--accent-amber)' }}>not found in PATH</span>}
                    </div>
                    <div>
                      <span style={{ opacity: 0.6 }}>API: </span>
                      {nirvanaRuntime.api_configured
                        ? <span style={{ color: 'var(--accent-green)' }}>✓ {nirvanaRuntime.api_base}</span>
                        : <span style={{ color: 'var(--accent-red)' }}>not configured</span>}
                    </div>

                    {nirvanaRuntime.config_sources && (
                      <>
                        <div style={{ marginTop: 8, fontWeight: 700, opacity: 0.8 }}>Detected config files:</div>
                        {nirvanaRuntime.config_sources.existing_paths?.length
                          ? nirvanaRuntime.config_sources.existing_paths.map((p) => (
                            <div key={p} style={{ color: 'var(--accent-green)', paddingLeft: 8 }}>✓ {presentConfigPath(p)}</div>
                          ))
                          : <div style={{ paddingLeft: 8, opacity: 0.5 }}>None found</div>}

                        <div style={{ marginTop: 8, fontWeight: 700, opacity: 0.8 }}>Checked locations:</div>
                        {nirvanaRuntime.config_sources.checked_paths?.map((p) => {
                          const found = nirvanaRuntime.config_sources.existing_paths?.includes(p);
                          return (
                            <div key={p} style={{ paddingLeft: 8, opacity: found ? 1 : 0.35 }}>
                              {found ? '✓' : '·'} {presentConfigPath(p)}
                            </div>
                          );
                        })}

                        <div style={{ marginTop: 8, fontWeight: 700, opacity: 0.8 }}>Env variables:</div>
                        {Object.entries(nirvanaRuntime.config_sources.env_variables || {})
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
                        {Object.entries(nirvanaRuntime.config_sources.resolved_env || {}).map(([k, v]) => (
                          <div key={k} style={{ paddingLeft: 8 }}>
                            <span style={{ opacity: 0.6 }}>{k}: </span>
                            <span style={{ color: 'var(--accent-green)' }}>
                              {(v?.source && String(v.source).startsWith('NIRVANA_')) ? v.source : (v?.source ? 'legacy alias' : 'not set')}
                            </span>
                          </div>
                        ))}

                        <div style={{ marginTop: 8, fontWeight: 700, opacity: 0.8 }}>Effective config:</div>
                        {Object.entries(nirvanaRuntime.config_sources.effective || {}).map(([k, v]) => (
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
    </div>
  );
}
