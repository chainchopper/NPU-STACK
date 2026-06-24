import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  listDevices,
  getDeviceTelemetry,
  executeDeviceCommand,
  rebootDevice,
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

function flattenTelemetryEntries(value, prefix = '', acc = []) {
  if (value == null) return acc;
  if (Array.isArray(value)) {
    value.forEach((entry, index) => flattenTelemetryEntries(entry, `${prefix}[${index}]`, acc));
    return acc;
  }
  if (typeof value === 'object') {
    Object.entries(value).forEach(([key, entry]) => {
      flattenTelemetryEntries(entry, prefix ? `${prefix}.${key}` : key, acc);
    });
    return acc;
  }
  acc.push([prefix || 'value', value]);
  return acc;
}

function formatFleetValue(value) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (value == null || value === '') return '—';
  return String(value);
}

function formatRecordedAt(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function summarizeFleetAction(action) {
  if (!action) return '';
  return action.summary || `${action.intent || 'fleet'} · ${action.status || 'captured'}`;
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
  const [fleetDevices, setFleetDevices] = useState([]);
  const [fleetLoading, setFleetLoading] = useState(false);
  const [selectedFleetDeviceId, setSelectedFleetDeviceId] = useState('');
  const [fleetTelemetry, setFleetTelemetry] = useState(null);
  const [fleetTelemetryLoading, setFleetTelemetryLoading] = useState(false);
  const [fleetCommandInput, setFleetCommandInput] = useState('');
  const [fleetActionRunning, setFleetActionRunning] = useState(false);
  const [fleetActionResult, setFleetActionResult] = useState(null);
  const [autoSendFleetQuickActions, setAutoSendFleetQuickActions] = useState(false);

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

  const selectedFleetDevice = useMemo(
    () => fleetDevices.find((device) => device.id === selectedFleetDeviceId) || null,
    [fleetDevices, selectedFleetDeviceId],
  );

  const fleetCounts = useMemo(() => ({
    total: fleetDevices.length,
    paired: fleetDevices.filter((device) => device.paired).length,
    online: fleetDevices.filter((device) => ['online', 'reachable'].includes(device.status)).length,
    telemetryReady: fleetDevices.filter((device) => device.capabilities?.telemetry || device.capabilities?.sensor_poll || device.telemetry).length,
  }), [fleetDevices]);

  const fleetTelemetryLatest = fleetTelemetry?.latest || null;
  const fleetTelemetryEntries = useMemo(
    () => flattenTelemetryEntries(fleetTelemetryLatest?.telemetry || fleetTelemetry?.registry_telemetry || {}).slice(0, 12),
    [fleetTelemetryLatest, fleetTelemetry],
  );
  const fleetTelemetryHistory = fleetTelemetry?.history || [];
  const fleetProtocols = selectedFleetDevice?.capabilities?.protocols || [];
  const fleetTransportModes = selectedFleetDevice?.capabilities?.transport_modes || [];

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

  const refreshFleetDevices = async ({ quiet = false } = {}) => {
    setFleetLoading(true);
    try {
      const data = await listDevices(true);
      const nextDevices = data?.devices || [];
      setFleetDevices(nextDevices);
      setSelectedFleetDeviceId((prev) => {
        if (prev && nextDevices.some((device) => device.id === prev)) return prev;
        return nextDevices.find((device) => device.paired)?.id || nextDevices[0]?.id || '';
      });
      if (!quiet) {
        setNotice(`Fleet sidecar refreshed (${nextDevices.length} devices).`);
      }
    } catch (e) {
      if (!quiet) setError(e.message || 'Failed to refresh fleet devices');
    } finally {
      setFleetLoading(false);
    }
  };

  const loadFleetTelemetry = async (deviceId, { refresh = false, quiet = true } = {}) => {
    if (!deviceId) {
      setFleetTelemetry(null);
      return;
    }
    setFleetTelemetryLoading(true);
    try {
      const snapshot = await getDeviceTelemetry(deviceId, { limit: 12, refresh });
      setFleetTelemetry(snapshot);
      if (!quiet) setNotice(`Telemetry ${refresh ? 'refreshed' : 'loaded'} for ${deviceId}.`);
    } catch (e) {
      if (!quiet) setError(e.message || 'Failed to load fleet telemetry');
    } finally {
      setFleetTelemetryLoading(false);
    }
  };

  const hydrate = async () => {
    setLoading(true);
    setError('');
    try {
      const [profilesResp, statusResp, runtimeResp, fleetResp] = await Promise.all([
        listAgentProfiles(),
        getNirvanaStatus(),
        getNirvanaRuntimeDetails(),
        listDevices(true),
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
      const nextFleetDevices = fleetResp?.devices || [];
      setFleetDevices(nextFleetDevices);
      setSelectedFleetDeviceId((prev) => {
        if (prev && nextFleetDevices.some((device) => device.id === prev)) return prev;
        return nextFleetDevices.find((device) => device.paired)?.id || nextFleetDevices[0]?.id || '';
      });
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

  useEffect(() => {
    if (!selectedFleetDeviceId) {
      setFleetTelemetry(null);
      return;
    }
    loadFleetTelemetry(selectedFleetDeviceId, { refresh: false, quiet: true });
  }, [selectedFleetDeviceId]);

  const injectPrompt = async (prompt, { immediate = autoSendFleetQuickActions } = {}) => {
    const normalized = String(prompt || '').trim();
    if (!normalized) return;

    setInput(normalized);
    setError('');

    if (!immediate || !activeProfileId || chatting) {
      setNotice(
        !activeProfileId
          ? 'Quick action staged in the composer. Select an active agent profile before sending.'
          : chatting
            ? 'Quick action staged in the composer while Nirvana finishes the current turn.'
            : 'Prompt injected into the Nirvana console. Press Send to execute through agent chat.',
      );
      requestAnimationFrame(() => {
        composerRef.current?.focus();
      });
      return;
    }

    await send(normalized);
  };

  const runDirectFleetExec = async () => {
    if (!selectedFleetDevice || !fleetCommandInput.trim()) return;
    setFleetActionRunning(true);
    setError('');
    try {
      const result = await executeDeviceCommand(selectedFleetDevice.id, fleetCommandInput.trim());
      const payload = result?.results_by_device?.[selectedFleetDevice.id] || result;
      setFleetActionResult({ kind: 'exec', deviceId: selectedFleetDevice.id, payload });
      setNotice(`Direct exec dispatched to ${selectedFleetDevice.id}.`);
      await loadFleetTelemetry(selectedFleetDevice.id, { refresh: true, quiet: true });
    } catch (e) {
      setError(e.message || 'Direct fleet exec failed');
    } finally {
      setFleetActionRunning(false);
    }
  };

  const runDirectFleetReboot = async () => {
    if (!selectedFleetDevice) return;
    setFleetActionRunning(true);
    setError('');
    try {
      const result = await rebootDevice(selectedFleetDevice.id);
      const payload = result?.results_by_device?.[selectedFleetDevice.id] || result;
      setFleetActionResult({ kind: 'reboot', deviceId: selectedFleetDevice.id, payload });
      setNotice(`Reboot requested for ${selectedFleetDevice.id}.`);
    } catch (e) {
      setError(e.message || 'Direct fleet reboot failed');
    } finally {
      setFleetActionRunning(false);
    }
  };

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

  const send = async (overrideInput = '') => {
    const trimmed = String(overrideInput || input).trim();
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

      if (!overrideInput || input.trim() === trimmed) {
        setInput('');
      }
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
        fleet_action: res?.fleet_action || null,
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

      setNotice(runtimeMeta ? 'Nirvana' : '');
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
                <label className="form-label">Optional Model Override</label>
                <input
                  className="form-input"
                  value={profileDraft.preferred_model}
                  onChange={(e) => setProfileDraft((prev) => ({ ...prev, preferred_model: e.target.value }))}
                  placeholder="Leave blank to use Nirvana's own configured provider/model"
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
            <div><strong>Nirvana provider:</strong> {runtime?.current_provider || 'not configured'} · {runtime?.current_model || 'upstream-managed'}</div>
            <div style={{fontSize:10}}>Nirvana's model is managed by the Hermes agent provider config — separate from NPU-STACK training/benchmarking/playground models.</div>
            <div><strong>Config path:</strong> {presentRuntimePath(runtime?.config_path)}</div>
            <div><strong>Nirvana home:</strong> {presentRuntimePath(runtime?.nirvana_home)}</div>
            <div><strong>State dir:</strong> {presentRuntimePath(runtime?.webui_state_dir)}</div>
            <div><strong>Active profile runtime hint:</strong> {profileDraft.runtime_mode || 'auto'}</div>
            <div><strong>Profile model override:</strong> {profileDraft.preferred_model || 'none (defer to Nirvana config)'}</div>
            <div><strong>Provider/model source:</strong> Nirvana bridge config drives the real provider; the profile field above is only an optional override.</div>
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
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 12, marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>Fleet Copilot Sidecar</div>
                    <div className="text-muted" style={{ fontSize: 11 }}>
                      Same fleet control surface, embedded directly inside the Nirvana chat console.
                    </div>
                  </div>
                  <button className="btn btn-secondary" type="button" onClick={() => refreshFleetDevices()} disabled={fleetLoading || loading}>
                    {fleetLoading ? 'Refreshing…' : 'Refresh Fleet'}
                  </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8, marginBottom: 10 }}>
                  <div className="card" style={{ margin: 0, padding: 10, minHeight: 0 }}><strong>{fleetCounts.total}</strong><div className="text-muted" style={{ fontSize: 11 }}>Devices</div></div>
                  <div className="card" style={{ margin: 0, padding: 10, minHeight: 0 }}><strong>{fleetCounts.paired}</strong><div className="text-muted" style={{ fontSize: 11 }}>Paired</div></div>
                  <div className="card" style={{ margin: 0, padding: 10, minHeight: 0 }}><strong>{fleetCounts.online}</strong><div className="text-muted" style={{ fontSize: 11 }}>Online</div></div>
                  <div className="card" style={{ margin: 0, padding: 10, minHeight: 0 }}><strong>{fleetCounts.telemetryReady}</strong><div className="text-muted" style={{ fontSize: 11 }}>Telemetry Ready</div></div>
                </div>

                <div className="form-group" style={{ marginBottom: 10 }}>
                  <label className="form-label">Active Fleet Device</label>
                  <select
                    className="form-select"
                    value={selectedFleetDeviceId}
                    onChange={(e) => setSelectedFleetDeviceId(e.target.value)}
                  >
                    {fleetDevices.map((device) => (
                      <option key={device.id} value={device.id}>
                        {(device.nickname || device.chip || device.id)} · {device.connection} · {device.status}
                      </option>
                    ))}
                  </select>
                </div>

                {selectedFleetDevice && (
                  <div style={{ marginBottom: 12, padding: 12, borderRadius: 8, border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', marginBottom: 10 }}>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 700 }}>{selectedFleetDevice.nickname || selectedFleetDevice.chip || selectedFleetDevice.id}</div>
                        <div className="text-muted" style={{ fontSize: 11 }}>
                          {selectedFleetDevice.family || 'unknown'} · {selectedFleetDevice.connection || 'unknown transport'} · {selectedFleetDevice.status || 'unknown status'}
                        </div>
                      </div>
                      {selectedFleetDevice.paired && (
                        <div style={{ fontSize: 11, fontWeight: 700, padding: '4px 8px', borderRadius: 999, background: 'rgba(168, 85, 247, 0.18)', color: 'var(--accent-purple)' }}>
                          PAIRED
                        </div>
                      )}
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8, marginBottom: (fleetProtocols.length || fleetTransportModes.length) ? 10 : 0 }}>
                      <div><span className="text-muted" style={{ fontSize: 11 }}>Device ID</span><div style={{ fontSize: 12, fontFamily: 'var(--font-mono)' }}>{selectedFleetDevice.id}</div></div>
                      <div><span className="text-muted" style={{ fontSize: 11 }}>Endpoint</span><div style={{ fontSize: 12 }}>{selectedFleetDevice.port || selectedFleetDevice.drive || selectedFleetDevice.ip || selectedFleetDevice.address || selectedFleetDevice.host || '—'}</div></div>
                      <div><span className="text-muted" style={{ fontSize: 11 }}>Last Seen</span><div style={{ fontSize: 12 }}>{formatRecordedAt(selectedFleetDevice.last_agent_seen_at || selectedFleetDevice.last_seen)}</div></div>
                      <div><span className="text-muted" style={{ fontSize: 11 }}>Chip / Model</span><div style={{ fontSize: 12 }}>{selectedFleetDevice.chip || selectedFleetDevice.description || '—'}</div></div>
                    </div>

                    {(fleetProtocols.length > 0 || fleetTransportModes.length > 0) && (
                      <div style={{ display: 'grid', gap: 8 }}>
                        {!!fleetProtocols.length && (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                            {fleetProtocols.map((protocol) => (
                              <span key={`protocol-${protocol}`} style={{ fontSize: 11, padding: '4px 8px', borderRadius: 999, background: 'rgba(59,130,246,0.16)', color: 'var(--accent-blue)' }}>
                                {protocol}
                              </span>
                            ))}
                          </div>
                        )}
                        {!!fleetTransportModes.length && (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                            {fleetTransportModes.map((mode) => (
                              <span key={`transport-${mode}`} style={{ fontSize: 11, padding: '4px 8px', borderRadius: 999, background: 'rgba(168, 85, 247, 0.16)', color: 'var(--accent-purple)' }}>
                                {mode}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
                  <button type="button" className="btn btn-secondary" onClick={() => injectPrompt('refresh telemetry for all paired devices')} disabled={chatting}>
                    Ask: paired telemetry
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => injectPrompt('show fleet health for all devices')} disabled={chatting}>
                    Ask: fleet health
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => selectedFleetDevice && injectPrompt(`run "uptime" on ${selectedFleetDevice.id}`)} disabled={!selectedFleetDevice || chatting}>
                    Ask: uptime on device
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => selectedFleetDevice && injectPrompt(`reboot ${selectedFleetDevice.id}`)} disabled={!selectedFleetDevice || chatting}>
                    Ask: reboot device
                  </button>
                </div>

                <label className="form-label" style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10 }}>
                  <input
                    type="checkbox"
                    checked={autoSendFleetQuickActions}
                    onChange={(e) => setAutoSendFleetQuickActions(e.target.checked)}
                  />
                  Auto-send fleet quick actions through Nirvana immediately
                </label>

                <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                  <input
                    className="form-input"
                    value={fleetCommandInput}
                    onChange={(e) => setFleetCommandInput(e.target.value)}
                    placeholder="Direct fleet exec, e.g. uptime && uname -a"
                  />
                  <button type="button" className="btn btn-secondary" onClick={runDirectFleetExec} disabled={!selectedFleetDevice || !fleetCommandInput.trim() || fleetActionRunning}>
                    {fleetActionRunning ? 'Running…' : 'Direct Exec'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={runDirectFleetReboot} disabled={!selectedFleetDevice || fleetActionRunning}>
                    Reboot
                  </button>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                  <div style={{ fontSize: 12, fontWeight: 700 }}>Selected device telemetry</div>
                  <button type="button" className="btn btn-secondary" onClick={() => loadFleetTelemetry(selectedFleetDeviceId, { refresh: true, quiet: false })} disabled={!selectedFleetDeviceId || fleetTelemetryLoading}>
                    {fleetTelemetryLoading ? 'Refreshing…' : 'Refresh Telemetry'}
                  </button>
                </div>

                {fleetTelemetryLatest && (
                  <div style={{ marginBottom: 10, fontSize: 12, color: 'var(--text-muted)' }}>
                    Latest snapshot from <strong>{fleetTelemetryLatest.source || 'registry'}</strong> at {formatRecordedAt(fleetTelemetryLatest.recorded_at)} · history: {fleetTelemetry?.history_count || 0}
                  </div>
                )}

                {fleetTelemetry && fleetTelemetryEntries.length > 0 && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8, marginBottom: 10 }}>
                    {fleetTelemetryEntries.map(([key, value]) => (
                      <div key={key} className="card" style={{ margin: 0, padding: 10, minHeight: 0 }}>
                        <div className="text-muted" style={{ fontSize: 10, marginBottom: 4, fontFamily: 'var(--font-mono)' }}>{key}</div>
                        <div style={{ fontSize: 13, fontWeight: 700 }}>{formatFleetValue(value)}</div>
                      </div>
                    ))}
                  </div>
                )}

                {fleetTelemetry && !fleetTelemetryEntries.length && (
                  <div className="text-muted" style={{ fontSize: 12, marginBottom: 10 }}>
                    Telemetry is connected, but no metric values were returned yet.
                  </div>
                )}

                {!!fleetTelemetryHistory.length && (
                  <div style={{ marginBottom: 10, border: '1px solid var(--border-color)', borderRadius: 8, padding: 10 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Recent telemetry history</div>
                    <div style={{ display: 'grid', gap: 8, maxHeight: 180, overflowY: 'auto' }}>
                      {fleetTelemetryHistory.slice().reverse().slice(0, 6).map((entry, index) => {
                        const sample = flattenTelemetryEntries(entry?.telemetry || {}).slice(0, 3);
                        return (
                          <div key={`${entry?.recorded_at || 'entry'}-${index}`} style={{ paddingBottom: 8, borderBottom: index === Math.min(fleetTelemetryHistory.length, 6) - 1 ? 'none' : '1px solid var(--border-color)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                              <div style={{ fontSize: 12, fontWeight: 600 }}>{entry?.source || 'telemetry'}</div>
                              <div className="text-muted" style={{ fontSize: 11 }}>{formatRecordedAt(entry?.recorded_at)}</div>
                            </div>
                            <div className="text-muted" style={{ fontSize: 11, marginTop: 4 }}>
                              {sample.length
                                ? sample.map(([key, value]) => `${key}=${formatFleetValue(value)}`).join(' · ')
                                : 'No flattened metrics in this snapshot.'}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {fleetActionResult?.payload && (
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 10, fontSize: 12, whiteSpace: 'pre-wrap', fontFamily: 'var(--font-mono)' }}>
                    <div style={{ fontWeight: 700, marginBottom: 6 }}>
                      Last direct action ({fleetActionResult.kind}){fleetActionResult.deviceId ? ` · ${fleetActionResult.deviceId}` : ''}
                    </div>
                    {fleetActionResult.payload.stdout || fleetActionResult.payload.note || fleetActionResult.payload.message || fleetActionResult.payload.error || JSON.stringify(fleetActionResult.payload, null, 2)}
                  </div>
                )}
              </div>

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
                    {m.fleet_action && (
                      <div style={{ marginTop: 6, border: '1px solid var(--border-color)', borderRadius: 8, padding: 8, background: 'rgba(88, 166, 255, 0.08)' }}>
                        <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 4 }}>
                          Fleet action · {String(m.fleet_action.intent || 'unknown').toUpperCase()} · {m.fleet_action.status || 'captured'}
                        </div>
                        <div style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{summarizeFleetAction(m.fleet_action)}</div>
                        {!!m.fleet_action.results?.length && (
                          <div className="text-muted" style={{ fontSize: 11, marginTop: 6 }}>
                            {m.fleet_action.results.slice(0, 4).map((item) => `${item.device_id}: ${item.summary?.status || item.summary?.message || item.summary?.note || 'captured'}`).join(' · ')}
                          </div>
                        )}
                      </div>
                    )}
                    {m.runtime && (
                      <div className="text-muted" style={{ fontSize: 11, marginTop: 3 }}>
                        Nirvana
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            <div className="text-muted" style={{ fontSize: 12, marginBottom: 10 }}>
              Nirvana agents handle conversation, fleet commands, tool use, and orchestration — separate from the model training pipelines.
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
