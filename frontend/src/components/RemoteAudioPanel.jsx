import React, { useEffect, useMemo, useState } from 'react';
import { Headphones, Radio, RefreshCw, Send, ShieldCheck, Trash2, Users } from 'lucide-react';
import {
  createManagedAudioProfile,
  createAudioGroup,
  deleteManagedAudioProfile,
  deleteAudioGroup,
  listManagedAudioEntities,
  listManagedAudioProfiles,
  listAudioEndpoints,
  listAudioGroups,
  routeAudio,
  testManagedAudioProfile,
  updateAudioGroup,
  updateManagedAudioProfile,
} from '../api/client';

function endpointLabel(endpoint) {
  return `${endpoint.name || endpoint.endpoint_id} · ${endpoint.endpoint_type || 'browser'}`;
}

export default function RemoteAudioPanel({ onSelectionChange }) {
  const [endpoints, setEndpoints] = useState([]);
  const [groups, setGroups] = useState([]);
  const [haProfiles, setHaProfiles] = useState([]);
  const [haEntities, setHaEntities] = useState([]);
  const [selectedHAProfileId, setSelectedHAProfileId] = useState('');
  const [haForm, setHaForm] = useState({ name: '', base_url: '', token: '', entity_id: '', engine: 'speak' });
  const [haBusy, setHaBusy] = useState(false);
  const [targetMode, setTargetMode] = useState('endpoint');
  const [selectedEndpointId, setSelectedEndpointId] = useState('');
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [speakResponses, setSpeakResponses] = useState(false);
  const [roomName, setRoomName] = useState('');
  const [roomMembers, setRoomMembers] = useState([]);
  const [editRoomName, setEditRoomName] = useState('');
  const [testText, setTestText] = useState('Hello from Nirvana.');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const onlineEndpoints = useMemo(() => endpoints.filter((endpoint) => endpoint.online), [endpoints]);

  const refresh = async ({ quiet = false } = {}) => {
    setLoading(true);
    if (!quiet) setError('');
    try {
      const [endpointResponse, groupResponse, profileResponse] = await Promise.all([
        listAudioEndpoints(),
        listAudioGroups(),
        listManagedAudioProfiles(),
      ]);
      const nextEndpoints = endpointResponse?.endpoints || [];
      const nextGroups = groupResponse?.groups || [];
      const nextProfiles = profileResponse?.profiles || [];
      setEndpoints(nextEndpoints);
      setGroups(nextGroups);
      setHaProfiles(nextProfiles);
      setSelectedHAProfileId((current) => current && nextProfiles.some((item) => item.id === current)
        ? current : (nextProfiles[0]?.id || ''));
      setSelectedEndpointId((current) => current && nextEndpoints.some((item) => item.endpoint_id === current)
        ? current : (nextEndpoints.find((item) => item.online)?.endpoint_id || nextEndpoints[0]?.endpoint_id || ''));
      setSelectedGroupId((current) => current && nextGroups.some((item) => item.id === current)
        ? current : (nextGroups[0]?.id || ''));
      if (!quiet) setNotice(`Audio destinations refreshed (${nextEndpoints.filter((item) => item.online).length} online).`);
    } catch (e) {
      setError(e.message || 'Failed to load audio destinations');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh({ quiet: true });
  }, []);

  useEffect(() => {
    onSelectionChange?.({
      speakResponse: speakResponses,
      audioEndpointId: targetMode === 'endpoint' ? selectedEndpointId : '',
      audioGroupId: targetMode === 'group' ? selectedGroupId : '',
    });
  }, [onSelectionChange, speakResponses, targetMode, selectedEndpointId, selectedGroupId]);

  useEffect(() => {
    const selected = groups.find((group) => group.id === selectedGroupId);
    setEditRoomName(selected?.name || '');
  }, [groups, selectedGroupId]);

  useEffect(() => {
    const selected = haProfiles.find((profile) => profile.id === selectedHAProfileId);
    if (!selected || haForm.name) return;
    setHaForm({
      name: selected.name || '',
      base_url: selected.base_url || '',
      token: '',
      entity_id: selected.entity_id || '',
      engine: selected.engine || 'speak',
      enabled: selected.enabled ?? true,
    });
  }, [haProfiles, selectedHAProfileId, haForm.name]);

  const sendTestSpeech = async () => {
    const text = testText.trim();
    if (!text || (targetMode === 'endpoint' ? !selectedEndpointId : !selectedGroupId)) return;
    setSending(true);
    setError('');
    setNotice('');
    try {
      const result = await routeAudio({
        text,
        ...(targetMode === 'endpoint' ? { endpoint_id: selectedEndpointId } : { group_id: selectedGroupId }),
        source: 'agents-test',
      });
      const delivered = (result?.results || []).filter((item) => item.status === 'delivered').length;
      setNotice(`Audio dispatched: ${delivered}/${result?.target_count || 0} destination(s) accepted it.`);
      await refresh({ quiet: true });
    } catch (e) {
      setError(e.message || 'Failed to send test speech');
    } finally {
      setSending(false);
    }
  };

  const createRoom = async () => {
    const name = roomName.trim();
    if (!name || !roomMembers.length) return;
    setLoading(true);
    setError('');
    try {
      const result = await createAudioGroup({ name, endpoint_ids: roomMembers });
      const room = result?.group;
      if (room) {
        setGroups((current) => [...current, room]);
        setSelectedGroupId(room.id);
        setTargetMode('group');
        setRoomName('');
        setRoomMembers([]);
        setNotice(`Room “${room.name}” saved.`);
      }
    } catch (e) {
      setError(e.message || 'Failed to save room');
    } finally {
      setLoading(false);
    }
  };

  const removeRoom = async () => {
    if (!selectedGroupId) return;
    const room = groups.find((item) => item.id === selectedGroupId);
    if (!room || !window.confirm(`Delete room “${room.name}”?`)) return;
    setLoading(true);
    try {
      await deleteAudioGroup(selectedGroupId);
      setGroups((current) => current.filter((item) => item.id !== selectedGroupId));
      setSelectedGroupId('');
      setNotice('Audio room deleted.');
    } catch (e) {
      setError(e.message || 'Failed to delete room');
    } finally {
      setLoading(false);
    }
  };

  const editRoom = async () => {
    if (!selectedGroupId || !editRoomName.trim()) return;
    setLoading(true);
    setError('');
    try {
      const room = groups.find((item) => item.id === selectedGroupId);
      const result = await updateAudioGroup(selectedGroupId, {
        name: editRoomName.trim(),
        endpoint_ids: room?.endpoint_ids || [],
      });
      if (result?.group) setGroups((current) => current.map((item) => item.id === selectedGroupId ? result.group : item));
      setNotice('Audio room updated.');
    } catch (e) {
      setError(e.message || 'Failed to update room');
    } finally {
      setLoading(false);
    }
  };

  const updateHAForm = (key, value) => setHaForm((current) => ({ ...current, [key]: value }));

  const saveHAProfile = async () => {
    if (!haForm.name.trim() || !haForm.base_url.trim() || (!selectedHAProfileId && !haForm.token.trim())) return;
    setHaBusy(true);
    setError('');
    try {
      const payload = { ...haForm, name: haForm.name.trim(), base_url: haForm.base_url.trim(), token: haForm.token.trim() || undefined };
      const result = selectedHAProfileId
        ? await updateManagedAudioProfile(selectedHAProfileId, payload)
        : await createManagedAudioProfile(payload);
      const profile = result?.profile;
      if (profile) {
        setHaProfiles((current) => selectedHAProfileId
          ? current.map((item) => item.id === profile.id ? profile : item)
          : [...current, profile]);
        setSelectedHAProfileId(profile.id);
        setHaForm((current) => ({ ...current, token: '' }));
        setNotice(selectedHAProfileId ? 'Home Assistant profile updated; token field cleared.' : 'Home Assistant profile saved; token field cleared.');
        await refresh({ quiet: true });
      }
    } catch (e) {
      setError(e.message || 'Failed to save Home Assistant profile');
    } finally {
      setHaBusy(false);
    }
  };

  const selectHAProfile = (profileId) => {
    const profile = haProfiles.find((item) => item.id === profileId);
    setSelectedHAProfileId(profileId);
    setHaEntities([]);
    setHaForm({
      name: profile?.name || '',
      base_url: profile?.base_url || '',
      token: '',
      entity_id: profile?.entity_id || '',
      engine: profile?.engine || 'speak',
      enabled: profile?.enabled ?? true,
    });
  };

  const discoverHAEntities = async () => {
    if (!selectedHAProfileId) return;
    setHaBusy(true);
    setError('');
    try {
      const result = await listManagedAudioEntities(selectedHAProfileId);
      setHaEntities(result?.entities || []);
      setNotice(`Found ${(result?.entities || []).length} Home Assistant media player(s).`);
    } catch (e) {
      setError(e.message || 'Failed to discover Home Assistant media players');
    } finally {
      setHaBusy(false);
    }
  };

  const testHAProfile = async () => {
    if (!selectedHAProfileId || !testText.trim()) return;
    setHaBusy(true);
    setError('');
    try {
      await testManagedAudioProfile(selectedHAProfileId, { text: testText.trim() });
      setNotice('Home Assistant accepted the test speech.');
      await refresh({ quiet: true });
    } catch (e) {
      setError(e.message || 'Home Assistant test speech failed');
    } finally {
      setHaBusy(false);
    }
  };

  const removeHAProfile = async () => {
    if (!selectedHAProfileId) return;
    const profile = haProfiles.find((item) => item.id === selectedHAProfileId);
    if (!profile || !window.confirm(`Remove Home Assistant profile “${profile.name}”?`)) return;
    setHaBusy(true);
    try {
      await deleteManagedAudioProfile(selectedHAProfileId);
      setHaProfiles((current) => current.filter((item) => item.id !== selectedHAProfileId));
      setSelectedHAProfileId('');
      setHaForm({ name: '', base_url: '', token: '', entity_id: '', engine: 'speak' });
      setNotice('Home Assistant profile removed.');
      await refresh({ quiet: true });
    } catch (e) {
      setError(e.message || 'Failed to remove Home Assistant profile');
    } finally {
      setHaBusy(false);
    }
  };

  return (
    <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 12, marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700 }}><Headphones size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />Room audio fabric</div>
          <div className="text-muted" style={{ fontSize: 11, marginTop: 3 }}>Speak through nearby computers and phones instead of a speaker attached to the XIAO.</div>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => refresh()} disabled={loading}><RefreshCw size={13} />Refresh</button>
      </div>

      <details style={{ marginBottom: 10 }}>
        <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--text-secondary)' }}><ShieldCheck size={13} style={{ verticalAlign: 'middle', marginRight: 5 }} />Manage Home Assistant endpoints</summary>
        <div style={{ marginTop: 8, padding: 10, border: '1px solid var(--border-color)', borderRadius: 6 }}>
          <div className="text-muted" style={{ fontSize: 11, marginBottom: 8 }}>Tokens are write-only here and encrypted by the backend. They are never returned to the browser.</div>
          <select className="form-select" aria-label="Home Assistant profile" value={selectedHAProfileId} onChange={(event) => selectHAProfile(event.target.value)}>
            <option value="">New Home Assistant profile</option>
            {haProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name} · {profile.health || 'unknown'}</option>)}
          </select>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8, marginTop: 8 }}>
            <input className="form-input" aria-label="Home Assistant name" value={haForm.name} onChange={(event) => updateHAForm('name', event.target.value)} placeholder="Home Assistant" />
            <input className="form-input" aria-label="Home Assistant URL" value={haForm.base_url} onChange={(event) => updateHAForm('base_url', event.target.value)} placeholder="http://homeassistant.local:8123" />
            <input className="form-input" aria-label="Home Assistant token" type="password" autoComplete="new-password" value={haForm.token} onChange={(event) => updateHAForm('token', event.target.value)} placeholder={selectedHAProfileId ? 'Token unchanged' : 'Long-lived token'} />
            <input className="form-input" aria-label="Home Assistant media player" value={haForm.entity_id} onChange={(event) => updateHAForm('entity_id', event.target.value)} placeholder="media_player.kitchen" />
            <input className="form-input" aria-label="Home Assistant TTS engine" value={haForm.engine} onChange={(event) => updateHAForm('engine', event.target.value)} placeholder="speak" />
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
            <button type="button" className="btn btn-secondary btn-sm" onClick={saveHAProfile} disabled={haBusy || !haForm.name.trim() || !haForm.base_url.trim() || (!selectedHAProfileId && !haForm.token.trim())}>{selectedHAProfileId ? 'Save / rotate token' : 'Add Home Assistant'}</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={discoverHAEntities} disabled={haBusy || !selectedHAProfileId}>Discover media players</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={testHAProfile} disabled={haBusy || !selectedHAProfileId}><Send size={13} />Test HA speech</button>
            <button type="button" className="btn btn-danger btn-sm" onClick={removeHAProfile} disabled={haBusy || !selectedHAProfileId}><Trash2 size={13} />Remove</button>
          </div>
          {haEntities.length > 0 && <select className="form-select" aria-label="Discovered media players" style={{ marginTop: 8 }} value={haForm.entity_id} onChange={(event) => updateHAForm('entity_id', event.target.value)}>
            <option value="">Use Home Assistant default player</option>
            {haEntities.map((entity) => <option key={entity.entity_id} value={entity.entity_id}>{entity.name} · {entity.entity_id}</option>)}
          </select>}
        </div>
      </details>

      <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
        <button type="button" className={`fleet-toggle ${targetMode === 'endpoint' ? 'active' : ''}`} data-active={targetMode === 'endpoint'} onClick={() => setTargetMode('endpoint')}><Radio size={13} />One endpoint</button>
        <button type="button" className={`fleet-toggle ${targetMode === 'group' ? 'active' : ''}`} data-active={targetMode === 'group'} onClick={() => setTargetMode('group')}><Users size={13} />Room / group</button>
      </div>

      {targetMode === 'endpoint' ? (
        <select className="form-select" aria-label="Audio endpoint" value={selectedEndpointId} onChange={(event) => setSelectedEndpointId(event.target.value)}>
          {!endpoints.length && <option value="">No audio endpoints configured</option>}
          {endpoints.map((endpoint) => <option key={endpoint.endpoint_id} value={endpoint.endpoint_id}>{endpoint.online ? '● ' : '○ '}{endpointLabel(endpoint)}</option>)}
        </select>
      ) : (
        <div style={{ display: 'flex', gap: 8 }}>
          <select className="form-select" aria-label="Audio room" value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>
            {!groups.length && <option value="">No rooms saved yet</option>}
            {groups.map((group) => <option key={group.id} value={group.id}>{group.name} · {group.endpoint_ids.length} endpoint(s)</option>)}
          </select>
          <button type="button" className="btn btn-danger btn-sm" onClick={removeRoom} disabled={!selectedGroupId || loading}>Delete</button>
        </div>
      )}

      <label className="form-label" style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10 }}>
        <input type="checkbox" checked={speakResponses} onChange={(event) => setSpeakResponses(event.target.checked)} />
        Speak Nirvana responses through this destination
      </label>

      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <input className="form-input" aria-label="Test speech" value={testText} onChange={(event) => setTestText(event.target.value)} placeholder="Test phrase" />
        <button type="button" className="btn btn-primary" onClick={sendTestSpeech} disabled={sending || !testText.trim() || (targetMode === 'endpoint' ? !selectedEndpointId : !selectedGroupId)}><Send size={14} />{sending ? 'Sending…' : 'Test speech'}</button>
      </div>

      <details style={{ marginTop: 10 }}>
        <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--text-secondary)' }}>Create a saved room</summary>
        <div style={{ marginTop: 8 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <input className="form-input" aria-label="New room name" value={roomName} onChange={(event) => setRoomName(event.target.value)} placeholder="Downstairs" />
            <button type="button" className="btn btn-secondary" onClick={createRoom} disabled={loading || !roomName.trim() || !roomMembers.length}>Save room</button>
          </div>
          {onlineEndpoints.length ? onlineEndpoints.map((endpoint) => (
            <label key={endpoint.endpoint_id} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12, marginBottom: 5 }}>
              <input type="checkbox" checked={roomMembers.includes(endpoint.endpoint_id)} onChange={(event) => setRoomMembers((current) => event.target.checked ? [...current, endpoint.endpoint_id] : current.filter((id) => id !== endpoint.endpoint_id))} />
              {endpointLabel(endpoint)}
            </label>
          )) : <div className="text-muted" style={{ fontSize: 12 }}>Open `/audio-output` on a computer or phone first.</div>}
        </div>
      </details>

      {selectedGroupId && (
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <input className="form-input" aria-label="Edit room name" value={editRoomName} onChange={(event) => setEditRoomName(event.target.value)} />
          <button type="button" className="btn btn-secondary" onClick={editRoom} disabled={loading || !editRoomName.trim()}>Update room name</button>
        </div>
      )}

      {notice && <div style={{ color: 'var(--accent-green)', fontSize: 11, marginTop: 10 }}>{notice}</div>}
      {error && <div role="alert" style={{ color: 'var(--accent-red)', fontSize: 11, marginTop: 10 }}>{error}</div>}
    </div>
  );
}
