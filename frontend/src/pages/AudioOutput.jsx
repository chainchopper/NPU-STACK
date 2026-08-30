import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MonitorSpeaker, Play, Square, Volume2, Wifi, WifiOff } from 'lucide-react';
import { audioWebsocketUrl, claimAudioPairing, createAudioPairingChallenge } from '../api/client';

const ENDPOINT_ID_KEY = 'nirvana-audio-endpoint-id';
const AUTH_TOKEN_KEY = 'nirvana-audio-endpoint-token';
const DEFAULT_CAPABILITIES = ['speech'];

function getStableEndpointId() {
  const existing = localStorage.getItem(ENDPOINT_ID_KEY);
  if (existing) return existing;
  const generated = globalThis.crypto?.randomUUID?.() || `browser-${Math.random().toString(36).slice(2)}-${Date.now()}`;
  localStorage.setItem(ENDPOINT_ID_KEY, generated);
  return generated;
}

function browserClientMetadata() {
  return {
    user_agent: typeof navigator !== 'undefined' ? navigator.userAgent.slice(0, 160) : 'browser',
    language: typeof navigator !== 'undefined' ? navigator.language || '' : '',
  };
}

export default function AudioOutput() {
  const [name, setName] = useState(() => localStorage.getItem('nirvana-audio-endpoint-name') || 'My Browser');
  const [endpointType, setEndpointType] = useState('browser');
  const [status, setStatus] = useState('connecting');
  const [enabled, setEnabled] = useState(false);
  const [endpoint, setEndpoint] = useState(null);
  const [lastMessage, setLastMessage] = useState('Waiting for Nirvana audio…');
  const [error, setError] = useState('');
  const [pairing, setPairing] = useState(null);
  const [pairingBusy, setPairingBusy] = useState(false);
  const wsRef = useRef(null);
  const heartbeatRef = useRef(null);
  const reconnectRef = useRef(null);
  const mountedRef = useRef(true);
  const endpointIdRef = useRef(getStableEndpointId());
  const enabledRef = useRef(enabled);
  const nameRef = useRef(name);
  const endpointTypeRef = useRef(endpointType);
  const authTokenRef = useRef(localStorage.getItem(AUTH_TOKEN_KEY) || '');

  useEffect(() => {
    enabledRef.current = enabled;
    nameRef.current = name;
    endpointTypeRef.current = endpointType;
  }, [enabled, name, endpointType]);

  const sendAck = useCallback((messageId, playbackStatus, detail = '') => {
    const ws = wsRef.current;
    if (ws?.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
      type: 'playback_ack',
      message_id: messageId,
      status: playbackStatus,
      ...(detail ? { error: detail } : {}),
    }));
  }, []);

  const playSpeech = useCallback((message) => {
    const speech = window.speechSynthesis;
    if (!enabledRef.current || !speech || typeof window.SpeechSynthesisUtterance === 'undefined') {
      sendAck(message.message_id, 'failed', 'Audio is not enabled or speech synthesis is unavailable');
      setLastMessage('Playback blocked — press Enable audio on this page first.');
      return;
    }

    speech.cancel();
    const utterance = new window.SpeechSynthesisUtterance(message.text || '');
    utterance.rate = Number(message.rate) || 1;
    utterance.volume = Number.isFinite(Number(message.volume)) ? Number(message.volume) : 1;
    if (message.voice) {
      const voice = speech.getVoices?.().find((item) => item.name === message.voice);
      if (voice) utterance.voice = voice;
    }
    utterance.onstart = () => sendAck(message.message_id, 'started');
    utterance.onend = () => {
      sendAck(message.message_id, 'ended');
      setLastMessage('Ready for the next Nirvana message.');
    };
    utterance.onerror = (event) => {
      const detail = event?.error || 'Speech synthesis failed';
      sendAck(message.message_id, 'failed', detail);
      setError(detail);
    };
    sendAck(message.message_id, 'accepted');
    setLastMessage(message.text || 'Nirvana sent an empty message.');
    speech.speak(utterance);
  }, [sendAck]);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current && [WebSocket.OPEN, WebSocket.CONNECTING].includes(wsRef.current.readyState)) return;

    setStatus('connecting');
    setError('');
    const ws = new WebSocket(audioWebsocketUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('connected');
      ws.send(JSON.stringify({
        type: 'register',
        endpoint_id: endpointIdRef.current,
        name: nameRef.current.trim() || 'My Browser',
        endpoint_type: endpointTypeRef.current,
        capabilities: DEFAULT_CAPABILITIES,
        client: browserClientMetadata(),
        ...(authTokenRef.current ? { auth_token: authTokenRef.current } : {}),
      }));
    };
    ws.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        setError('Received an invalid audio message from Nirvana.');
        return;
      }
      if (message.type === 'registered') {
        setEndpoint(message.endpoint);
        setStatus('connected');
        setError('');
        const interval = Math.max(5000, Number(message.heartbeat_interval_seconds || 15) * 1000);
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'heartbeat' }));
        }, interval);
        return;
      }
      if (message.type === 'speak') {
        playSpeech(message);
        return;
      }
      if (message.type === 'stop') {
        window.speechSynthesis?.cancel();
        setLastMessage('Playback stopped.');
        if (message.message_id) sendAck(message.message_id, 'ended');
        return;
      }
      if (message.type === 'error') setError(message.error || 'Audio endpoint error');
    };
    ws.onerror = () => {
      setStatus('error');
      setError('Could not connect to the Nirvana audio fabric.');
    };
    ws.onclose = () => {
      clearInterval(heartbeatRef.current);
      if (!mountedRef.current) return;
      setStatus('offline');
      reconnectRef.current = setTimeout(connect, 3000);
    };
  }, [playSpeech, sendAck]);

  const startPairing = async () => {
    setPairingBusy(true);
    setError('');
    try {
      const challenge = await createAudioPairingChallenge({ endpoint_id: endpointIdRef.current, endpoint_type: endpointType });
      setPairing(challenge);
      setLastMessage(`Pairing code ${challenge.pairing_code} is ready and expires soon.`);
    } catch (e) {
      setError(e.message || 'Could not create pairing challenge');
    } finally {
      setPairingBusy(false);
    }
  };

  const approvePairing = async () => {
    if (!pairing?.challenge_id || !pairing?.pairing_code) return;
    setPairingBusy(true);
    setError('');
    try {
      const result = await claimAudioPairing({
        challenge_id: pairing.challenge_id,
        pairing_code: pairing.pairing_code,
        endpoint_id: endpointIdRef.current,
        endpoint_type: endpointType,
        capabilities: DEFAULT_CAPABILITIES,
      });
      if (!result?.auth_token) throw new Error('Pairing did not return an endpoint credential');
      localStorage.setItem(AUTH_TOKEN_KEY, result.auth_token);
      authTokenRef.current = result.auth_token;
      setPairing(null);
      setLastMessage('Endpoint paired. Reconnecting with its new credential…');
      wsRef.current?.close();
    } catch (e) {
      setError(e.message || 'Could not approve pairing');
    } finally {
      setPairingBusy(false);
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectRef.current);
      clearInterval(heartbeatRef.current);
      window.speechSynthesis?.cancel();
      wsRef.current?.close();
    };
  }, [connect]);

  const saveIdentity = () => {
    localStorage.setItem('nirvana-audio-endpoint-name', name.trim() || 'My Browser');
    wsRef.current?.close();
    setLastMessage('Reconnecting with the updated endpoint identity…');
  };

  const statusLabel = status === 'connected' ? 'Online' : status === 'connecting' ? 'Connecting…' : 'Offline';

  return (
    <div>
      <div className="page-header">
        <h2>Audio Output</h2>
        <p>Turn this computer or phone into a Nirvana room speaker. No local XIAO speaker required.</p>
      </div>

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <div className="card">
          <div className="card-header">
            <h3 className="card-title"><MonitorSpeaker size={18} style={{ verticalAlign: 'middle', marginRight: 8 }} />Endpoint identity</h3>
            <span className={`badge ${status === 'connected' ? 'badge-success' : 'badge-warning'}`}>
              {status === 'connected' ? <Wifi size={12} /> : <WifiOff size={12} />}{statusLabel}
            </span>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="audio-endpoint-name">Room label</label>
            <input id="audio-endpoint-name" className="form-input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Living room computer" />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="audio-endpoint-type">Endpoint type</label>
            <select id="audio-endpoint-type" className="form-select" value={endpointType} onChange={(event) => setEndpointType(event.target.value)}>
              <option value="browser">Browser</option>
              <option value="computer">Computer</option>
              <option value="phone">Phone</option>
              <option value="monitor">Monitor</option>
              <option value="speaker">Speaker</option>
            </select>
          </div>
          <button type="button" className="btn btn-secondary" onClick={saveIdentity}>Save endpoint identity</button>
          <div className="text-muted" style={{ fontSize: 11, marginTop: 12, wordBreak: 'break-all' }}>
            Stable endpoint ID: {endpoint?.endpoint_id || endpointIdRef.current}
          </div>
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border-color)' }}>
            <div className="text-muted" style={{ fontSize: 11, marginBottom: 8 }}>Optional secure pairing</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button type="button" className="btn btn-secondary btn-sm" onClick={startPairing} disabled={pairingBusy}>Create pairing code</button>
              {pairing && <button type="button" className="btn btn-success btn-sm" onClick={approvePairing} disabled={pairingBusy}>Approve pairing</button>}
            </div>
            {pairing && <div style={{ marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 16, letterSpacing: '0.18em' }} aria-label="Pairing code">{pairing.pairing_code}</div>}
            <div className="text-muted" style={{ fontSize: 10, marginTop: 5 }}>The credential is stored only in this browser and is never shown by the endpoint API.</div>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><h3 className="card-title"><Volume2 size={18} style={{ verticalAlign: 'middle', marginRight: 8 }} />Playback</h3></div>
          <p className="text-muted" style={{ fontSize: 13, marginBottom: 14 }}>
            Browsers require a user gesture before they allow speech. Enable audio once, then leave this tab open in the room.
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" className={enabled ? 'btn btn-success' : 'btn btn-primary'} onClick={() => setEnabled(true)} disabled={enabled}>
              <Play size={15} />{enabled ? 'Audio enabled' : 'Enable audio'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => { window.speechSynthesis?.cancel(); setLastMessage('Playback stopped.'); }}>
              <Square size={15} />Stop playback
            </button>
          </div>
          <div style={{ marginTop: 16, padding: 12, border: '1px solid var(--border-color)', borderRadius: 8, minHeight: 80 }}>
            <div className="text-muted" style={{ fontSize: 11, marginBottom: 6 }}>Latest activity</div>
            <div style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{lastMessage}</div>
          </div>
          {error && <div role="alert" style={{ color: 'var(--accent-red)', fontSize: 12, marginTop: 12 }}>{error}</div>}
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3 className="card-title">How this works</h3>
        <p className="text-muted" style={{ fontSize: 13, marginTop: 8 }}>
          Nirvana sends a text speech message over the local WebSocket. This browser renders it through its selected system voice. Later audio adapters can add native speakers, Home Assistant, or binary audio without changing room membership.
        </p>
      </div>
    </div>
  );
}
