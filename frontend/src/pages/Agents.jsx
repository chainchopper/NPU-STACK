import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  listAgentProfiles,
  createAgentProfile,
  updateAgentProfile,
  deleteAgentProfile,
  listAgentSessions,
  createAgentSession,
  updateAgentSession,
  deleteAgentSession,
  getNirvanaStatus,
  getNirvanaRuntimeDetails,
  prepareNirvanaRuntime,
  launchNirvana,
  chatWithNirvana,
} from '../api/client';

const DEFAULT_PROFILE = {
  name: '',
  description: '',
  system_prompt: '',
  use_fleet_tools: false,
  use_orchestration_context: true,
  preferred_model: '',
  runtime_mode: 'auto',
};

const sessionTimeFormatter = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

function toProfileDraft(profile) {
  return profile ? {
    name: profile.name || '',
    description: profile.description || '',
    system_prompt: profile.system_prompt || '',
    use_fleet_tools: Boolean(profile.use_fleet_tools),
    use_orchestration_context: profile.use_orchestration_context !== false,
    preferred_model: profile.preferred_model || '',
    runtime_mode: profile.runtime_mode || 'auto',
  } : DEFAULT_PROFILE;
}

function sortSessions(items = []) {
  return [...items].sort((a, b) => {
    const pinDelta = Number(Boolean(b?.pinned)) - Number(Boolean(a?.pinned));
    if (pinDelta !== 0) return pinDelta;
    return String(b?.updated_at || b?.created_at || '').localeCompare(String(a?.updated_at || a?.created_at || ''));
  });
}

function sessionPreview(session) {
  return session?.last_message_preview || session?.messages?.[session.messages.length - 1]?.content || 'No messages yet.';
}

function formatSessionTime(session) {
  const value = session?.updated_at || session?.created_at;
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return sessionTimeFormatter.format(date);
}

function downloadTextFile(content, fileName, mimeType = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function presentRuntimePath(path) {
  if (!path) return 'N/A';
  const legacyBrand = ['her', 'mes'].join('');
  return String(path)
    .replaceAll(`${legacyBrand}-agent`, 'nirvana-agent')
    .replaceAll(`${legacyBrand}.exe`, 'nirvana.exe')
    .replaceAll(`.${legacyBrand}`, '.nirvana')
    .replaceAll(`\\${legacyBrand}\\`, '\\nirvana\\')
    .replaceAll(`/${legacyBrand}/`, '/nirvana/');
}

function buildSessionMarkdown(profile, session) {
  const header = [
    `# ${session?.title || 'Agent Session'}`,
    '',
    `- Profile: ${profile?.name || session?.profile_name || 'Unknown Agent'}`,
    `- Session ID: ${session?.id || 'unknown'}`,
    `- Updated: ${session?.updated_at || session?.created_at || 'unknown'}`,
    '',
    '---',
    '',
  ];

  const body = (session?.messages || []).flatMap((message) => {
    const label = message?.role === 'user' ? 'You' : 'Nirvana';
    const lines = [
      `## ${label}`,
      '',
      String(message?.content || ''),
      '',
    ];
    if (message?.runtime) {
      lines.push(
        `- Runtime: ${message.runtime.engine || 'unknown'}`,
        `- Model: ${message.runtime.model_file || 'unknown'}`,
        `- Mode: ${message.runtime.runtime_mode || 'auto'}`,
        '',
      );
    }
    return lines;
  });

  return [...header, ...body].join('\n');
}

export default function Agents() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [chatting, setChatting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const [profiles, setProfiles] = useState([]);
  const [activeProfileId, setActiveProfileId] = useState('');
  const [profileDraft, setProfileDraft] = useState(DEFAULT_PROFILE);
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState('');
  const [sessionFilter, setSessionFilter] = useState('');
  const [sessionTitleDraft, setSessionTitleDraft] = useState('');

  const [agentStatus, setAgentStatus] = useState(null);
  const [runtime, setRuntime] = useState(null);

  const [input, setInput] = useState('');
  const transcriptRef = useRef(null);
  const composerRef = useRef(null);

  const activeProfile = useMemo(
    () => profiles.find((p) => p.id === activeProfileId) || null,
    [profiles, activeProfileId],
  );

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) || null,
    [sessions, activeSessionId],
  );

  const hasDraftChanges = useMemo(() => {
    if (!activeProfile) return false;
    return JSON.stringify(profileDraft) !== JSON.stringify(toProfileDraft(activeProfile));
  }, [activeProfile, profileDraft]);

  const filteredSessions = useMemo(() => {
    const needle = sessionFilter.trim().toLowerCase();
    if (!needle) return sessions;
    return sessions.filter((session) => {
      const haystack = [
        session?.title,
        session?.last_message_preview,
        session?.profile_name,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [sessions, sessionFilter]);

  const messages = activeSession?.messages || [];

  const hydrate = async () => {
    setLoading(true);
    setError('');
    try {
      const [profilesResp, statusResp, runtimeResp] = await Promise.all([
        listAgentProfiles(),
        getNirvanaStatus(),
        getNirvanaRuntimeDetails(),
      ]);

      const nextProfiles = profilesResp?.profiles || [];
      setProfiles(nextProfiles);

      const nextActive = (activeProfileId && nextProfiles.some((p) => p.id === activeProfileId))
        ? activeProfileId
        : (nextProfiles[0]?.id || '');
      setActiveProfileId(nextActive);
      const selected = nextProfiles.find((p) => p.id === nextActive) || null;
      setProfileDraft(toProfileDraft(selected));

      setAgentStatus(statusResp || null);
      setRuntime(runtimeResp || null);
    } catch (e) {
      setError(e.message || 'Failed to load agents state');
    } finally {
      setLoading(false);
    }
  };

  const ensureSessionsForProfile = async (profileId, preferredSessionId = '') => {
    if (!profileId) {
      setSessions([]);
      setActiveSessionId('');
      return [];
    }

    let nextSessions = (await listAgentSessions(profileId))?.sessions || [];
    if (!nextSessions.length) {
      const created = await createAgentSession({ profile_id: profileId });
      if (created?.session) {
        nextSessions = [created.session];
      }
    }

    const sortedSessions = sortSessions(nextSessions);
    setSessions(sortedSessions);

    const nextActive = (preferredSessionId && sortedSessions.some((session) => session.id === preferredSessionId))
      ? preferredSessionId
      : (activeSessionId && sortedSessions.some((session) => session.id === activeSessionId)
        ? activeSessionId
        : (sortedSessions[0]?.id || ''));
    setActiveSessionId(nextActive);
    return sortedSessions;
  };

  const refreshRuntime = async () => {
    try {
      const [statusResp, runtimeResp] = await Promise.all([getNirvanaStatus(), getNirvanaRuntimeDetails()]);
      setAgentStatus(statusResp || null);
      setRuntime(runtimeResp || null);
    } catch {
      // no-op
    }
  };

  useEffect(() => {
    hydrate();
  }, []);

  useEffect(() => {
    if (!activeProfile) {
      setProfileDraft(DEFAULT_PROFILE);
      setSessions([]);
      setActiveSessionId('');
      setSessionTitleDraft('');
      return;
    }
    setProfileDraft(toProfileDraft(activeProfile));
    setInput('');
    ensureSessionsForProfile(activeProfile.id).catch((e) => {
      setError(e.message || 'Failed to load agent sessions');
    });
  }, [activeProfile]);

  useEffect(() => {
    setSessionTitleDraft(activeSession?.title || '');
  }, [activeSessionId, activeSession?.title]);

  useEffect(() => {
    if (!transcriptRef.current) return;
    transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
  }, [messages.length, activeSessionId, chatting]);

  useEffect(() => {
    if (!composerRef.current || !activeProfileId) return;
    composerRef.current.focus();
  }, [activeProfileId, activeSessionId]);

  const resetProfileDraft = () => {
    if (!activeProfile) return;
    setProfileDraft(toProfileDraft(activeProfile));
    setNotice('Profile draft reset.');
    setError('');
  };

  const saveCurrentProfile = async () => {
    if (!activeProfile) return;
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const result = await updateAgentProfile(activeProfile.id, profileDraft);
      const updated = result?.profile;
      setProfiles((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setSessions((prev) => prev.map((session) => (
        session.profile_id === activeProfile.id
          ? { ...session, profile_name: updated.name || session.profile_name }
          : session
      )));
      setNotice('Agent profile saved.');
    } catch (e) {
      setError(e.message || 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  const createProfile = async () => {
    const baseName = `Agent ${profiles.length + 1}`;
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const result = await createAgentProfile({
        ...DEFAULT_PROFILE,
        name: baseName,
      });
      const created = result?.profile;
      if (!created) return;
      setProfiles((prev) => [created, ...prev]);
      setActiveProfileId(created.id);
      setNotice('New agent profile created.');
    } catch (e) {
      setError(e.message || 'Failed to create profile');
    } finally {
      setSaving(false);
    }
  };

  const removeCurrentProfile = async () => {
    if (!activeProfile) return;
    const ok = window.confirm(`Delete profile "${activeProfile.name}"?`);
    if (!ok) return;

    setSaving(true);
    setError('');
    setNotice('');
    try {
      await deleteAgentProfile(activeProfile.id);
      const nextProfiles = profiles.filter((p) => p.id !== activeProfile.id);
      setProfiles(nextProfiles);
      setSessions((prev) => prev.filter((session) => session.profile_id !== activeProfile.id));
      setActiveSessionId('');
      setActiveProfileId(nextProfiles[0]?.id || '');
      setNotice('Agent profile deleted.');
    } catch (e) {
      setError(e.message || 'Failed to delete profile');
    } finally {
      setSaving(false);
    }
  };

  const createSessionForActiveProfile = async ({ quiet = false } = {}) => {
    if (!activeProfile) return null;
    const result = await createAgentSession({ profile_id: activeProfile.id });
    const created = result?.session;
    if (!created) return null;
    setSessions((prev) => sortSessions([created, ...prev.filter((session) => session.id !== created.id)]));
    setActiveSessionId(created.id);
    if (!quiet) {
      setNotice('New agent session created.');
    }
    return created;
  };

  const removeCurrentSession = async () => {
    if (!activeSession || !activeProfile) return;
    const ok = window.confirm(`Delete session "${activeSession.title}"?`);
    if (!ok) return;

    setSaving(true);
    setError('');
    setNotice('');
    try {
      await deleteAgentSession(activeSession.id);
      let nextSessions = sessions.filter((session) => session.id !== activeSession.id);
      let nextActiveId = nextSessions[0]?.id || '';

      if (!nextSessions.length) {
        const created = await createAgentSession({ profile_id: activeProfile.id });
        if (created?.session) {
          nextSessions = [created.session];
          nextActiveId = created.session.id;
        }
      }

      setSessions(sortSessions(nextSessions));
      setActiveSessionId(nextActiveId);
      setNotice('Agent session deleted.');
    } catch (e) {
      setError(e.message || 'Failed to delete session');
    } finally {
      setSaving(false);
    }
  };

  const renameActiveSession = async () => {
    if (!activeSession) return;

    const trimmed = sessionTitleDraft.trim();
    const nextTitle = trimmed || 'New Session';
    if (nextTitle === activeSession.title) return;

    setSaving(true);
    setError('');
    setNotice('');
    try {
      const result = await updateAgentSession(activeSession.id, { title: nextTitle });
      const updated = result?.session;
      if (!updated) {
        throw new Error('Rename did not return an updated session');
      }
      setSessions((prev) => sortSessions(prev.map((session) => (
        session.id === updated.id ? { ...session, ...updated } : session
      ))));
      setSessionTitleDraft(updated.title || nextTitle);
      setNotice('Agent session renamed.');
    } catch (e) {
      setError(e.message || 'Failed to rename session');
    } finally {
      setSaving(false);
    }
  };

  const togglePinnedSession = async (session) => {
    if (!session) return;
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const result = await updateAgentSession(session.id, { pinned: !session.pinned });
      const updated = result?.session;
      if (!updated) {
        throw new Error('Pin toggle did not return an updated session');
      }
      setSessions((prev) => sortSessions(prev.map((item) => (
        item.id === updated.id ? { ...item, ...updated } : item
      ))));
      setNotice(updated.pinned ? 'Session pinned.' : 'Session unpinned.');
    } catch (e) {
      setError(e.message || 'Failed to update session pin state');
    } finally {
      setSaving(false);
    }
  };

  const exportActiveSession = (format = 'md') => {
    if (!activeSession) return;
    const safeTitle = String(activeSession.title || 'agent-session')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'agent-session';
    const exportBaseName = `agent-session-export-${safeTitle}`;

    if (format === 'json') {
      downloadTextFile(
        JSON.stringify(
          {
            profile: activeProfile,
            session: activeSession,
          },
          null,
          2,
        ),
        `${exportBaseName}.json`,
        'application/json;charset=utf-8',
      );
      setNotice('Session exported as JSON.');
      return;
    }

    downloadTextFile(
      buildSessionMarkdown(activeProfile, activeSession),
      `${exportBaseName}.md`,
      'text/markdown;charset=utf-8',
    );
    setNotice('Session exported as Markdown.');
  };

  const send = async () => {
    const trimmed = input.trim();
    if (!trimmed || chatting || !activeProfileId) return;

    let sessionId = activeSessionId;
    let baseMessages = messages;

    setError('');
    setNotice('');

    try {
      if (!sessionId) {
        const created = await createSessionForActiveProfile({ quiet: true });
        if (!created?.id) {
          throw new Error('Failed to create a session for this profile');
        }
        sessionId = created.id;
        baseMessages = created.messages || [];
      }

      const timestamp = new Date().toISOString();
      const userMsg = { role: 'user', content: trimmed, created_at: timestamp };
      const nextMessages = [...baseMessages, userMsg];

      setSessions((prev) => sortSessions(prev.map((session) => (
        session.id === sessionId
          ? {
            ...session,
            messages: nextMessages,
            message_count: nextMessages.length,
            last_message_preview: trimmed.slice(0, 160),
            updated_at: timestamp,
            last_message_at: timestamp,
          }
          : session
      ))));

      setInput('');
      setChatting(true);

      const res = await chatWithNirvana({
        messages: nextMessages.map((m) => ({ role: m.role, content: m.content })),
        temperature: 0.7,
        max_tokens: 600,
        profile_id: activeProfileId,
        session_id: sessionId,
        use_fleet_tools: profileDraft.use_fleet_tools,
        use_orchestration_context: profileDraft.use_orchestration_context,
        runtime_mode: profileDraft.runtime_mode,
        preferred_model: profileDraft.preferred_model,
      });

      const reply = res?.response || res?.choices?.[0]?.message?.content || 'No response from Nirvana.';
      const runtimeMeta = res?.nirvana_runtime || null;
      const assistantTimestamp = new Date().toISOString();
      const assistantMessage = {
        role: 'assistant',
        content: reply,
        runtime: runtimeMeta,
        created_at: assistantTimestamp,
      };
      const persistedSession = res?.agent_session || null;

      setSessions((prev) => sortSessions(prev.map((session) => (
        session.id === sessionId
          ? {
            ...session,
            title: persistedSession?.title || session.title,
            messages: [...nextMessages, assistantMessage],
            message_count: persistedSession?.message_count || (nextMessages.length + 1),
            last_message_preview: reply.slice(0, 160),
            updated_at: persistedSession?.updated_at || assistantTimestamp,
            last_message_at: assistantTimestamp,
          }
          : session
      ))));

      setNotice(runtimeMeta ? `Verified runtime: ${runtimeMeta.engine} (${runtimeMeta.model_file || 'default'})` : '');
      await ensureSessionsForProfile(activeProfileId, persistedSession?.id || sessionId);
    } catch (e) {
      const errorTimestamp = new Date().toISOString();
      const errorMessage = {
        role: 'assistant',
        content: `Error: ${e.message}`,
        created_at: errorTimestamp,
      };

      if (sessionId) {
        setSessions((prev) => sortSessions(prev.map((session) => (
          session.id === sessionId
            ? {
              ...session,
              messages: [...(session.messages || baseMessages), errorMessage],
              message_count: (session.messages || baseMessages).length + 1,
              last_message_preview: errorMessage.content.slice(0, 160),
              updated_at: errorTimestamp,
              last_message_at: errorTimestamp,
            }
            : session
        ))));
      }
      setError(e.message || 'Chat failed');
    } finally {
      setChatting(false);
      await refreshRuntime();
    }
  };

  const prepareEmbeddedNirvana = async () => {
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const result = await prepareNirvanaRuntime();
      setNotice(result?.message || 'Prepared isolated Nirvana runtime.');
      await refreshRuntime();
    } catch (e) {
      setError(e.message || 'Failed to prepare Nirvana runtime');
    } finally {
      setSaving(false);
    }
  };

  const launchEmbeddedNirvana = async () => {
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const result = await launchNirvana();
      setNotice(result?.message || 'Nirvana WebUI launched.');
      await refreshRuntime();
    } catch (e) {
      setError(e.message || 'Failed to launch Nirvana WebUI');
    } finally {
      setSaving(false);
    }
  };

  const openEmbeddedNirvana = () => {
    const target = runtime?.webui_url || agentStatus?.webui_url;
    if (!target) {
      setError('Nirvana WebUI URL is not available yet. Prepare and launch the bridge first.');
      return;
    }
    window.open(target, '_blank', 'noopener,noreferrer');
  };

  const copyCommand = async (command) => {
    try {
      await navigator.clipboard.writeText(command);
      setNotice(`Copied: ${command}`);
      setError('');
    } catch (e) {
      setError(e.message || 'Failed to copy command');
    }
  };

  return (
    <div>
      <div className="page-header">
        <h2>Agents</h2>
        <p>
          Nirvana control center for multi-agent profiles, persistent orchestration sessions, and the absorbed
          upstream Nirvana CLI/WebUI bridge.
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

      <div className="grid-2" style={{ alignItems: 'start', gap: 14 }}>
        <div className="card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 className="card-title">Agent Profiles</h3>
            <button className="btn btn-secondary" onClick={createProfile} disabled={saving || loading}>New Profile</button>
          </div>

          {loading ? (
            <p className="text-muted">Loading agent profiles…</p>
          ) : (
            <>
              <div className="form-group">
                <label className="form-label">Active Profile</label>
                <select
                  className="form-select"
                  value={activeProfileId}
                  onChange={(e) => setActiveProfileId(e.target.value)}
                >
                  {(profiles || []).map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Name</label>
                <input
                  className="form-input"
                  value={profileDraft.name}
                  onChange={(e) => setProfileDraft((prev) => ({ ...prev, name: e.target.value }))}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Description</label>
                <input
                  className="form-input"
                  value={profileDraft.description}
                  onChange={(e) => setProfileDraft((prev) => ({ ...prev, description: e.target.value }))}
                />
              </div>

              <div className="form-group">
                <label className="form-label">System Prompt</label>
                <textarea
                  className="form-input"
                  rows={5}
                  value={profileDraft.system_prompt}
                  onChange={(e) => setProfileDraft((prev) => ({ ...prev, system_prompt: e.target.value }))}
                />
              </div>

              <div className="grid-2" style={{ gap: 10 }}>
                <label className="form-label" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={Boolean(profileDraft.use_orchestration_context)}
                    onChange={(e) => setProfileDraft((prev) => ({ ...prev, use_orchestration_context: e.target.checked }))}
                  />
                  Include orchestration context
                </label>

                <label className="form-label" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={Boolean(profileDraft.use_fleet_tools)}
                    onChange={(e) => setProfileDraft((prev) => ({ ...prev, use_fleet_tools: e.target.checked }))}
                  />
                  Include fleet tool context
                </label>
              </div>

              <div className="form-group">
                <label className="form-label">Runtime Preference</label>
                <select
                  className="form-select"
                  value={profileDraft.runtime_mode}
                  onChange={(e) => setProfileDraft((prev) => ({ ...prev, runtime_mode: e.target.value }))}
                >
                  <option value="auto">auto</option>
                  <option value="local">local</option>
                  <option value="external">external</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Preferred Runtime Model</label>
                <input
                  className="form-input"
                  value={profileDraft.preferred_model}
                  onChange={(e) => setProfileDraft((prev) => ({ ...prev, preferred_model: e.target.value }))}
                  placeholder="Optional external runtime model override"
                />
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                <button className="btn btn-primary" onClick={saveCurrentProfile} disabled={!activeProfile || saving}>Save Profile</button>
                <button className="btn btn-secondary" onClick={resetProfileDraft} disabled={!activeProfile || saving || !hasDraftChanges}>Reset Draft</button>
                <button className="btn btn-secondary" onClick={removeCurrentProfile} disabled={!activeProfile || saving}>Delete</button>
                <button className="btn btn-secondary" onClick={hydrate} disabled={loading || saving}>Refresh</button>
              </div>
            </>
          )}
        </div>

        <div className="card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 className="card-title">Nirvana Bridge</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-secondary" onClick={prepareEmbeddedNirvana} disabled={saving}>Prepare Runtime</button>
              <button className="btn btn-secondary" onClick={launchEmbeddedNirvana} disabled={saving}>Launch UI</button>
              <button className="btn btn-primary" onClick={openEmbeddedNirvana} disabled={!runtime?.webui_url && !agentStatus?.webui_url}>Open Nirvana</button>
            </div>
          </div>
          <div className="text-muted" style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div><strong>Bridge status:</strong> {runtime?.webui_running ? 'running' : runtime?.prepared ? 'prepared, not started' : 'not prepared'}</div>
            <div><strong>WebUI URL:</strong> {runtime?.webui_url || agentStatus?.webui_url || 'N/A'}</div>
            <div><strong>Setup state:</strong> {runtime?.setup_state || 'not started'}</div>
            <div><strong>Onboarding complete:</strong> {runtime?.completed ? 'yes' : 'no'}</div>
            <div><strong>Provider ready:</strong> {runtime?.provider_ready ? 'yes' : 'no'}</div>
            <div><strong>Chat ready:</strong> {runtime?.chat_ready ? 'yes' : 'no'}</div>
            <div><strong>Active provider:</strong> {runtime?.current_provider || 'not configured'}</div>
            <div><strong>Active model:</strong> {runtime?.current_model || profileDraft.preferred_model || 'upstream-managed'}</div>
            <div><strong>Config path:</strong> {presentRuntimePath(runtime?.config_path)}</div>
            <div><strong>Nirvana home:</strong> {presentRuntimePath(runtime?.nirvana_home)}</div>
            <div><strong>State dir:</strong> {presentRuntimePath(runtime?.webui_state_dir)}</div>
            <div><strong>Active profile runtime hint:</strong> {profileDraft.runtime_mode || 'auto'}</div>
            <div><strong>Preferred model hint:</strong> {profileDraft.preferred_model || 'none'}</div>
          </div>

          {!!runtime?.recommended_commands?.length && (
            <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 700 }}>Upstream CLI parity</div>
              {runtime.recommended_commands.map((item) => (
                <div key={item.id || item.command} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                    <code style={{ fontSize: 12 }}>{item.command}</code>
                    <button className="btn btn-secondary" onClick={() => copyCommand(item.command)} type="button">Copy</button>
                  </div>
                  <div className="text-muted" style={{ fontSize: 11, marginTop: 6 }}>{item.description}</div>
                </div>
              ))}
            </div>
          )}

          {!!runtime?.log_excerpt && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Latest bridge log excerpt</div>
              <pre style={{ margin: 0, maxHeight: 160, overflow: 'auto', fontSize: 11, whiteSpace: 'pre-wrap' }}>{runtime.log_excerpt}</pre>
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 14, minHeight: 380 }}>
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <div>
            <h3 className="card-title">Agent Chat Console</h3>
            <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
              Profile: {activeProfile?.name || 'None selected'} · Session: {activeSession?.title || 'No session'}{activeSession?.pinned ? ' · pinned' : ''}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-secondary" onClick={() => createSessionForActiveProfile()} disabled={!activeProfile || saving || chatting}>New Session</button>
            <button className="btn btn-secondary" onClick={() => togglePinnedSession(activeSession)} disabled={!activeSession || saving || chatting}>
              {activeSession?.pinned ? 'Unpin Session' : 'Pin Session'}
            </button>
            <button className="btn btn-secondary" onClick={() => exportActiveSession('md')} disabled={!activeSession}>Export Markdown</button>
            <button className="btn btn-secondary" onClick={() => exportActiveSession('json')} disabled={!activeSession}>Export JSON</button>
            <button className="btn btn-secondary" onClick={removeCurrentSession} disabled={!activeSession || saving || chatting}>Delete Session</button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '280px minmax(0, 1fr)', gap: 12 }}>
          <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8, maxHeight: 480, overflowY: 'auto' }}>
            <div className="form-group" style={{ marginBottom: 8 }}>
              <input
                className="form-input"
                value={sessionFilter}
                onChange={(e) => setSessionFilter(e.target.value)}
                placeholder="Filter sessions..."
              />
            </div>

            {filteredSessions.length === 0 ? (
              <div className="text-muted" style={{ fontSize: 12 }}>No sessions for this profile yet.</div>
            ) : (
              filteredSessions.map((session) => (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => setActiveSessionId(session.id)}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    border: '1px solid var(--border-color)',
                    borderRadius: 8,
                    padding: 10,
                    marginBottom: 8,
                    background: session.id === activeSessionId ? 'rgba(88, 166, 255, 0.12)' : 'transparent',
                    cursor: 'pointer',
                    color: 'inherit',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {session.pinned ? '📌 ' : ''}{session.title}
                    </div>
                    <div className="text-muted" style={{ fontSize: 11, flexShrink: 0 }}>{formatSessionTime(session)}</div>
                  </div>
                  <div className="text-muted" style={{ fontSize: 10, marginTop: 4 }}>
                    {session.message_count || 0} message{(session.message_count || 0) === 1 ? '' : 's'}
                  </div>
                  <div className="text-muted" style={{ fontSize: 11, marginTop: 6, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {sessionPreview(session)}
                  </div>
                </button>
              ))
            )}
          </div>

          <div>
            <div className="form-group" style={{ marginBottom: 10 }}>
              <label className="form-label">Session Title</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  className="form-input"
                  value={sessionTitleDraft}
                  onChange={(e) => setSessionTitleDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      renameActiveSession();
                    }
                  }}
                  placeholder="Session title"
                  disabled={!activeSession}
                />
                <button className="btn btn-secondary" onClick={renameActiveSession} disabled={!activeSession || saving}>
                  Rename
                </button>
              </div>
            </div>

            <div ref={transcriptRef} style={{ maxHeight: 360, overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: 8, padding: 10, marginBottom: 10 }}>
              {messages.length === 0 ? (
                <div className="text-muted">Start chatting with the selected profile and session.</div>
              ) : (
                messages.map((m, idx) => (
                  <div key={`${m.role}-${idx}-${m.created_at || 'now'}`} style={{ marginBottom: 8 }}>
                    <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 2 }}>{m.role === 'user' ? 'You' : 'Nirvana'}</div>
                    <div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{m.content}</div>
                    {m.runtime && (
                      <div className="text-muted" style={{ fontSize: 11, marginTop: 3 }}>
                        engine: {m.runtime.engine} · model: {m.runtime.model_file} · mode: {m.runtime.runtime_mode || 'auto'} · mock: {String(m.runtime.uses_mock_responses)}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            <div className="text-muted" style={{ fontSize: 12, marginBottom: 10 }}>
              Chat executes through the real upstream Nirvana WebUI bridge using the selected profile draft immediately — including unsaved runtime hints and preferred model overrides.
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <textarea
                ref={composerRef}
                className="form-input"
                rows={3}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="Ask the selected agent profile..."
              />
              <button className="btn btn-primary" onClick={send} disabled={chatting || !input.trim() || !activeProfileId}>
                {chatting ? 'Sending…' : 'Send'}
              </button>
            </div>

            <div className="text-muted" style={{ fontSize: 11, marginTop: 8 }}>
              Press Enter to send. Use Shift+Enter for a newline.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
