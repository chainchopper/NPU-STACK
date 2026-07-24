"""
XiaoZhi Protocol Server — MQTT+UDP Hybrid Voice Control for NPU-STACK Fleet

Implements the server side of xiaozhi-esp32's MQTT+UDP hybrid protocol.
Devices (AMB82-Mini, ESP32-S3, etc.) send hello via MQTT; this server:
  1. Registers the device session
  2. Returns UDP audio channel parameters
  3. Routes audio through STT → LLM (Nirvana/DeepSeek) → TTS
  4. Handles MCP device control relay
  5. Sends alerts, emotion updates, system commands

Protocol docs: https://github.com/78/xiaozhi-esp32/blob/main/docs/mqtt-udp.md
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# ── paho-mqtt is required ──
try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False

# ── AES for UDP audio encryption ──
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ═══════════════════════════════════════════════════════════════
# Session Management
# ═══════════════════════════════════════════════════════════════

@dataclass
class VoiceSession:
    """A single device voice session."""
    session_id: str
    device_id: str
    device_topic: str          # MQTT topic for this device
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    # UDP audio channel
    udp_host: str = "0.0.0.0"
    udp_port: int = 0
    udp_key: str = ""          # AES-128 key (hex)
    udp_nonce: str = ""        # AES-128 nonce (hex)
    udp_active: bool = False

    # State
    listening: bool = False
    speaking: bool = False
    emotion: str = "neutral"

    # Capabilities (from device hello)
    features: Dict[str, bool] = field(default_factory=dict)
    audio_format: str = "opus"
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_frame_ms: int = 60


# In-memory session store
_sessions: Dict[str, VoiceSession] = {}          # session_id → session
_device_sessions: Dict[str, VoiceSession] = {}   # device_id → session
_lock = threading.Lock()


def _generate_session_id() -> str:
    return uuid.uuid4().hex[:16]


def _generate_aes_key() -> str:
    """Generate 128-bit AES key as hex string."""
    return secrets.token_hex(16)  # 32 hex chars = 16 bytes


def _generate_aes_nonce() -> str:
    """Generate 128-bit nonce as hex string."""
    return secrets.token_hex(16)


def create_session(device_id: str, device_topic: str) -> VoiceSession:
    """Create a new voice session for a device."""
    with _lock:
        # Close existing session for this device
        if device_id in _device_sessions:
            old_session = _device_sessions[device_id]
            if old_session.session_id in _sessions:
                del _sessions[old_session.session_id]

        session = VoiceSession(
            session_id=_generate_session_id(),
            device_id=device_id,
            device_topic=device_topic,
        )
        _sessions[session.session_id] = session
        _device_sessions[device_id] = session
        return session


def get_session(session_id: str) -> Optional[VoiceSession]:
    return _sessions.get(session_id)


def get_device_session(device_id: str) -> Optional[VoiceSession]:
    return _device_sessions.get(device_id)


def close_session(session_id: str):
    with _lock:
        session = _sessions.pop(session_id, None)
        if session and session.device_id in _device_sessions:
            del _device_sessions[session.device_id]


def list_sessions() -> List[Dict[str, Any]]:
    with _lock:
        return [
            {
                "session_id": s.session_id,
                "device_id": s.device_id,
                "listening": s.listening,
                "speaking": s.speaking,
                "emotion": s.emotion,
                "created_at": s.created_at,
                "last_activity": s.last_activity,
            }
            for s in _sessions.values()
        ]


# ═══════════════════════════════════════════════════════════════
# MQTT Protocol Handler
# ═══════════════════════════════════════════════════════════════

class XiaoZhiServer:
    """Persistent MQTT client that handles xiaozhi protocol messages."""

    def __init__(
        self,
        mqtt_broker: str = "127.0.0.1",
        mqtt_port: int = 1883,
        fleet_prefix: str = "npu-fleet",
        udp_host: str = "0.0.0.0",
        udp_port: int = 0,
        llm_callback: Optional[Callable] = None,
    ):
        self.broker = mqtt_broker
        self.port = mqtt_port
        self.fleet_prefix = fleet_prefix
        self.udp_host = udp_host
        self.udp_port = udp_port
        self.llm_callback = llm_callback  # async fn(text, session) → str
        self._client: Optional[mqtt.Client] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._started = False

    # ── START / STOP ──────────────────────────────────────

    def start(self) -> bool:
        """Start the MQTT listener in a background thread."""
        if not HAS_MQTT:
            print("[XiaoZhi] paho-mqtt not installed — cannot start")
            return False
        if self._running:
            return True

        client_id = f"npustack-xiaozhi-{uuid.uuid4().hex[:8]}"
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        try:
            self._client.connect(self.broker, self.port, keepalive=60)
        except Exception as e:
            print(f"[XiaoZhi] MQTT connect failed: {e}")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._mqtt_loop, daemon=True, name="xiaozhi-mqtt")
        self._thread.start()
        self._started = True
        print(f"[XiaoZhi] Server started — {self.broker}:{self.port}")
        print(f"[XiaoZhi] Subscribed to: {self.fleet_prefix}/#")
        return True

    def stop(self):
        """Stop the MQTT listener."""
        self._running = False
        if self._client:
            try:
                self._client.disconnect()
            except:
                pass
        if self._thread:
            self._thread.join(timeout=3)
        print("[XiaoZhi] Server stopped")

    def _mqtt_loop(self):
        """Background MQTT network loop."""
        while self._running:
            try:
                self._client.loop(timeout=0.5)
            except Exception as e:
                print(f"[XiaoZhi] MQTT loop error: {e}")
                time.sleep(1)

    # ── MQTT CALLBACKS ────────────────────────────────────

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            print(f"[XiaoZhi] MQTT connected to {self.broker}")
            # Subscribe to all fleet device topics
            topic = f"{self.fleet_prefix}/#"
            client.subscribe(topic)
            print(f"[XiaoZhi] Subscribed: {topic}")
        else:
            print(f"[XiaoZhi] MQTT connect failed: rc={reason_code}")

    def _on_disconnect(self, client, userdata, reason_code, properties=None):
        print(f"[XiaoZhi] MQTT disconnected (rc={reason_code}) — will auto-reconnect")
        if self._running:
            time.sleep(2)
            try:
                client.connect(self.broker, self.port, keepalive=60)
            except:
                pass

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        topic = msg.topic
        payload_str = msg.payload.decode("utf-8", errors="replace")

        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            # Not JSON — might be binary or a different protocol
            return

        msg_type = payload.get("type", "")
        if not msg_type:
            return

        # Extract device_id from topic: npu-fleet/{platform}/{device_id}
        # Or handle legacy topic formats
        device_id = payload.get("device_id", "")
        if not device_id:
            # Try to extract from topic
            parts = topic.split("/")
            if len(parts) >= 3:
                device_id = parts[-1]

        session = get_device_session(device_id) if device_id else None

        # ── Route by message type ──
        if msg_type == "hello":
            self._handle_hello(client, topic, payload, device_id, session)
        elif msg_type == "listen":
            self._handle_listen(client, topic, payload, session)
        elif msg_type == "abort":
            self._handle_abort(session)
        elif msg_type == "mcp":
            self._handle_mcp(client, topic, payload, session)
        elif msg_type == "goodbye":
            self._handle_goodbye(session)
        else:
            print(f"[XiaoZhi] Unknown type '{msg_type}' from {device_id}")

    # ── PROTOCOL HANDLERS ─────────────────────────────────

    def _handle_hello(self, client, topic, payload, device_id, session):
        """Device says hello — create session, return UDP config."""
        print(f"[XiaoZhi] HELLO from {device_id}")

        # Extract capabilities
        features = payload.get("features", {})
        transport = payload.get("transport", "udp")
        audio_params = payload.get("audio_params", {})

        # Create session
        session = create_session(device_id, topic)
        session.features = features
        session.audio_format = audio_params.get("format", "opus")
        session.audio_sample_rate = audio_params.get("sample_rate", 16000)
        session.audio_channels = audio_params.get("channels", 1)
        session.audio_frame_ms = audio_params.get("frame_duration", 60)

        if transport == "udp":
            session.udp_active = True
            session.udp_key = _generate_aes_key()
            session.udp_nonce = _generate_aes_nonce()
            session.udp_host = self.udp_host
            session.udp_port = self.udp_port

        # Build hello response
        response = {
            "type": "hello",
            "transport": transport,
            "session_id": session.session_id,
            "audio_params": {
                "format": "opus",
                "sample_rate": 24000,
                "channels": 1,
                "frame_duration": 60,
            },
        }

        if transport == "udp" and session.udp_active:
            response["udp"] = {
                "server": session.udp_host,
                "port": session.udp_port,
                "key": session.udp_key,
                "nonce": session.udp_nonce,
            }

        # Publish to device's topic
        client.publish(topic, json.dumps(response))
        print(f"[XiaoZhi] Hello response → {device_id} (session: {session.session_id})")

        # Also publish fleet-wide status
        status_topic = f"{self.fleet_prefix}/status"
        client.publish(status_topic, json.dumps({
            "event": "device_online",
            "device_id": device_id,
            "session_id": session.session_id,
            "features": features,
        }))

    def _handle_listen(self, client, topic, payload, session):
        """Device starts listening — audio will follow via UDP."""
        if not session:
            print(f"[XiaoZhi] Listen from unknown session — ignoring")
            return

        state = payload.get("state", "")
        mode = payload.get("mode", "manual")

        if state == "start":
            session.listening = True
            session.last_activity = time.time()
            print(f"[XiaoZhi] LISTEN START — {session.device_id} (mode: {mode})")

            # If we have an LLM callback, acknowledge and prepare
            if self.llm_callback:
                # Send the wake word response: "I'm listening"
                response = {
                    "session_id": session.session_id,
                    "type": "tts",
                    "state": "start",
                }
                client.publish(topic, json.dumps(response))

        elif state == "stop":
            session.listening = False
            print(f"[XiaoZhi] LISTEN STOP — {session.device_id}")

        elif state == "detect":
            # Wake word detected — send TTS confirmation
            text = payload.get("text", "")
            print(f"[XiaoZhi] LISTEN DETECT: '{text}' from {session.device_id}")

            if self.llm_callback and text.strip():
                # Process through LLM pipeline
                self._process_llm(client, topic, session, text)

    def _handle_abort(self, session):
        """Device aborted current operation."""
        if session:
            session.listening = False
            session.speaking = False
            print(f"[XiaoZhi] ABORT — {session.device_id}")

    def _handle_mcp(self, client, topic, payload, session):
        """Device sent MCP (device control) message."""
        mcp_payload = payload.get("payload", {})
        print(f"[XiaoZhi] MCP from {session.device_id if session else 'unknown'}: {mcp_payload}")

        # Relay to fleet command topic for device control
        fleet_topic = f"{self.fleet_prefix}/mcp"
        client.publish(fleet_topic, json.dumps({
            "source_device": session.device_id if session else "unknown",
            "payload": mcp_payload,
        }))

    def _handle_goodbye(self, session):
        """Device is disconnecting."""
        if session:
            print(f"[XiaoZhi] GOODBYE — {session.device_id}")
            close_session(session.session_id)

    def _process_llm(self, client, topic, session, text):
        """Process user text through LLM → TTS pipeline."""
        print(f"[XiaoZhi] LLM processing: '{text[:80]}...' from {session.device_id}")

        # Send LLM thinking status
        client.publish(topic, json.dumps({
            "session_id": session.session_id,
            "type": "llm",
            "emotion": "thinking",
        }))

        try:
            # Call the LLM callback (sync for now — could be async)
            import asyncio
            if callable(self.llm_callback):
                # Run sync in thread — real impl should use asyncio properly
                response_text = self.llm_callback(text, session.device_id)
            else:
                response_text = f"Nirvana heard: {text}"

            print(f"[XiaoZhi] LLM response: '{response_text[:80]}...'")

            # Send emotion
            emotion = "happy"
            if "?" in text:
                emotion = "curious"
            elif "!" in text:
                emotion = "excited"

            client.publish(topic, json.dumps({
                "session_id": session.session_id,
                "type": "llm",
                "emotion": emotion,
                "text": response_text,
            }))

            # Send TTS start
            client.publish(topic, json.dumps({
                "session_id": session.session_id,
                "type": "tts",
                "state": "start",
            }))

            # Send TTS sentence
            client.publish(topic, json.dumps({
                "session_id": session.session_id,
                "type": "tts",
                "state": "sentence_start",
                "text": response_text,
            }))

            # Send TTS stop
            client.publish(topic, json.dumps({
                "session_id": session.session_id,
                "type": "tts",
                "state": "stop",
            }))

            session.speaking = False
            session.emotion = emotion

        except Exception as e:
            print(f"[XiaoZhi] LLM error: {e}")
            # Send error alert to device
            client.publish(topic, json.dumps({
                "session_id": session.session_id,
                "type": "alert",
                "status": "Error",
                "message": f"LLM processing failed: {e}",
                "emotion": "sad",
            }))

    # ── PUBLIC METHODS (for REST API) ─────────────────────

    def send_tts(self, device_id: str, text: str) -> bool:
        """Send TTS text to a device."""
        session = get_device_session(device_id)
        if not session:
            print(f"[XiaoZhi] No session for {device_id}")
            return False

        topic = session.device_topic
        try:
            self._client.publish(topic, json.dumps({
                "session_id": session.session_id,
                "type": "tts",
                "state": "start",
            }))
            self._client.publish(topic, json.dumps({
                "session_id": session.session_id,
                "type": "tts",
                "state": "sentence_start",
                "text": text,
            }))
            self._client.publish(topic, json.dumps({
                "session_id": session.session_id,
                "type": "tts",
                "state": "stop",
            }))
            return True
        except Exception as e:
            print(f"[XiaoZhi] TTS send failed: {e}")
            return False

    def send_alert(self, device_id: str, status: str, message: str, emotion: str = "neutral") -> bool:
        """Send an alert to a device."""
        session = get_device_session(device_id)
        if not session:
            return False

        try:
            self._client.publish(session.device_topic, json.dumps({
                "session_id": session.session_id,
                "type": "alert",
                "status": status,
                "message": message,
                "emotion": emotion,
            }))
            return True
        except:
            return False

    def send_mcp(self, device_id: str, mcp_payload: Dict[str, Any]) -> bool:
        """Send MCP control to a device."""
        session = get_device_session(device_id)
        if not session:
            return False

        try:
            self._client.publish(session.device_topic, json.dumps({
                "session_id": session.session_id,
                "type": "mcp",
                "payload": mcp_payload,
            }))
            return True
        except:
            return False

    def send_system(self, device_id: str, command: str) -> bool:
        """Send system command (e.g. reboot) to device."""
        session = get_device_session(device_id)
        if not session:
            return False

        try:
            self._client.publish(session.device_topic, json.dumps({
                "session_id": session.session_id,
                "type": "system",
                "command": command,
            }))
            return True
        except:
            return False


# ═══════════════════════════════════════════════════════════════
# Global Instance
# ═══════════════════════════════════════════════════════════════

_xiaozhi_server: Optional[XiaoZhiServer] = None


def get_xiaozhi_server() -> Optional[XiaoZhiServer]:
    """Get the global XiaoZhi server instance."""
    return _xiaozhi_server


def init_xiaozhi_server(
    mqtt_broker: str = "127.0.0.1",
    mqtt_port: int = 1883,
    fleet_prefix: str = "npu-fleet",
    udp_host: str = "0.0.0.0",
    udp_port: int = 0,
    llm_callback: Optional[Callable] = None,
) -> XiaoZhiServer:
    """Initialize and start the XiaoZhi protocol server."""
    global _xiaozhi_server

    if _xiaozhi_server and _xiaozhi_server._started:
        return _xiaozhi_server

    server = XiaoZhiServer(
        mqtt_broker=mqtt_broker,
        mqtt_port=mqtt_port,
        fleet_prefix=fleet_prefix,
        udp_host=udp_host,
        udp_port=udp_port,
        llm_callback=llm_callback,
    )

    if server.start():
        _xiaozhi_server = server
        return server

    return None


def shutdown_xiaozhi_server():
    """Shutdown the XiaoZhi server."""
    global _xiaozhi_server
    if _xiaozhi_server:
        _xiaozhi_server.stop()
        _xiaozhi_server = None
