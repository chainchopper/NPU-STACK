import React, { useEffect, useMemo, useState } from 'react';
import {
  listAutoResearchProfiles,
  createAutoResearchProfile,
  deleteAutoResearchProfile,
  listAutoResearchRuns,
  createAutoResearchRun,
  updateAutoResearchRun,
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

export default function AutoResearch() {
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const [profiles, setProfiles] = useState([]);
  const [runs, setRuns] = useState([]);
  const [profileDraft, setProfileDraft] = useState(defaultProfile);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [runNotes, setRunNotes] = useState('');

  const [interopSettings, setInteropSettings] = useState({
    orchestration_model: 'nirvana-default',
    dataset_strategy: 'derive-and-cache',
    max_parallel_agents: 2,
    persist_intermediate_artifacts: true,
  });

  const activeProfile = useMemo(
    () => profiles.find((p) => p.id === selectedProfileId) || null,
    [profiles, selectedProfileId]
  );

  const loadAll = async () => {
    setLoading(true);
    setError('');
    try {
      const [profileData, runData] = await Promise.all([
        listAutoResearchProfiles(),
        listAutoResearchRuns(50),
      ]);
      const nextProfiles = profileData.profiles || [];
      setProfiles(nextProfiles);
      setRuns(runData.runs || []);
      if (!selectedProfileId && nextProfiles.length) {
        setSelectedProfileId(nextProfiles[0].id);
      }
    } catch (e) {
      setError(e.message || 'Failed to load AutoResearch state');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

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
      const remaining = profiles.filter((p) => p.id !== profileId);
      setProfiles(remaining);
      if (selectedProfileId === profileId) {
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
        result_summary: status === 'completed' ? 'Marked as completed from AutoResearch panel.' : null,
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
        <h2>AutoResearch</h2>
        <p>
          Dedicated research orchestration panel for profile design, execution, and interoperability settings.
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

      <div className="grid-2" style={{ marginBottom: 16, alignItems: 'start' }}>
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Research Profile Builder</h3>
          </div>

          {loading ? (
            <p className="text-muted">Loading profiles…</p>
          ) : (
            <>
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
            </>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Interoperability Settings</h3>
          </div>

          <div className="form-group">
            <label className="form-label">Orchestration Model</label>
            <select
              className="form-select"
              value={interopSettings.orchestration_model}
              onChange={(e) => setInteropSettings((prev) => ({ ...prev, orchestration_model: e.target.value }))}
            >
              <option value="nirvana-default">nirvana-default</option>
              <option value="compatibility-focused">compatibility-focused</option>
              <option value="exploration-heavy">exploration-heavy</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Dataset Creation Strategy</label>
            <select
              className="form-select"
              value={interopSettings.dataset_strategy}
              onChange={(e) => setInteropSettings((prev) => ({ ...prev, dataset_strategy: e.target.value }))}
            >
              <option value="derive-and-cache">derive-and-cache</option>
              <option value="rebuild-each-run">rebuild-each-run</option>
              <option value="manual-approval">manual-approval</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Max Parallel Agents</label>
            <input
              type="number"
              min={1}
              max={8}
              className="form-input"
              value={interopSettings.max_parallel_agents}
              onChange={(e) => setInteropSettings((prev) => ({ ...prev, max_parallel_agents: Number(e.target.value || 1) }))}
            />
          </div>
          <div className="form-group">
            <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={Boolean(interopSettings.persist_intermediate_artifacts)}
                onChange={(e) => setInteropSettings((prev) => ({ ...prev, persist_intermediate_artifacts: e.target.checked }))}
              />
              Persist intermediate research artifacts
            </label>
          </div>

          <div className="text-muted" style={{ fontSize: 12 }}>
            These settings scope run behavior and prepare cross-stack outputs (docs snippets, dataset derivatives, and orchestration hints).
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Run Queue</h3>
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
          <label className="form-label">Run Notes</label>
          <textarea className="form-input" rows={2} value={runNotes} onChange={(e) => setRunNotes(e.target.value)} />
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-primary" onClick={queueRun}>Queue Run</button>
          <button className="btn btn-secondary" onClick={loadAll}>Refresh Runs</button>
        </div>

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
  );
}
