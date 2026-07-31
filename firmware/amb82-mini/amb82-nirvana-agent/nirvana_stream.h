// NIRVANA STREAM — Lightweight WebSocket client for bi-directional audio
// Pure WiFiClient TCP, no external WebSocket library needed
// Protocol: mic PCM → server (masked binary frames), TTS PCM ← server (unmasked)
// Feeds audio amplitude into nirvana_orb for real-time waveform animation
#ifndef NIRVANA_STREAM_H
#define NIRVANA_STREAM_H

#include <WiFi.h>
#include "nirvana_config.h"

#define WS_HOST            MQTT_HOST
#define WS_PORT            8010                     // NPU-STACK backend port
#define WS_PATH            "/api/nirvana/stream"    // FastAPI WebSocket endpoint
#define WS_KEEPALIVE_MS    15000
#define WS_RECONNECT_MS    5000

// ── State ──
WiFiClient wsClient;
bool wsConnected = false;
unsigned long wsLastPing = 0;
unsigned long wsLastReconnect = 0;
char wsRecvBuf[2048];     // Receive buffer for TTS PCM + protocol headers
int  wsRecvLen = 0;

// ── Raw TCP send ──
static bool _ws_send(const uint8_t* data, size_t len) {
    if (!wsClient.connected()) return false;
    return wsClient.write(data, len) == (int)len;
}

// ── Send a masked WebSocket binary frame ──
// Client→Server frames MUST be masked per RFC 6455
void _ws_send_binary(const uint8_t* payload, size_t len) {
    if (!wsConnected || !wsClient.connected()) return;
    if (len == 0) return;

    uint8_t header[14];  // Max: 2 base + 8 extended + 4 mask = 14
    int hi = 0;

    // Byte 0: FIN=1, RSV=0, opcode=2 (binary)
    header[hi++] = 0x82;

    // Byte 1: MASK=1 + length
    if (len <= 125) {
        header[hi++] = 0x80 | (uint8_t)len;
    } else if (len <= 65535) {
        header[hi++] = 0x80 | 126;
        header[hi++] = (len >> 8) & 0xFF;
        header[hi++] = len & 0xFF;
    } else {
        header[hi++] = 0x80 | 127;
        for (int i = 7; i >= 0; i--) header[hi++] = (len >> (i * 8)) & 0xFF;
    }

    // Mask key (4 random bytes)
    uint8_t mask[4] = {0xAB, 0xCD, 0x12, 0x34};  // Fixed for simplicity
    memcpy(header + hi, mask, 4); hi += 4;

    // Send header + mask
    wsClient.write(header, hi);

    // Send masked payload in chunks
    uint8_t chunk[128];
    size_t pos = 0;
    while (pos < len) {
        size_t n = (len - pos > sizeof(chunk)) ? sizeof(chunk) : (len - pos);
        for (size_t i = 0; i < n; i++) {
            chunk[i] = payload[pos + i] ^ mask[(pos + i) % 4];
        }
        wsClient.write(chunk, n);
        pos += n;
    }
    wsClient.flush();
}

// ── Simple SHA1 → for Sec-WebSocket-Key (built-in) ──
// We use a fixed base64 key. Servers accept any valid-looking key.
// Standard testing key from RFC 6455 examples:
const char* ws_key = "dGhlIHNhbXBsZSBub25jZQ=="; // "the sample nonce" in b64

// ── Connect + HTTP WebSocket upgrade handshake ──
bool nirvana_stream_connect() {
    if (wsConnected && wsClient.connected()) return true;

    wsClient.stop();
    Serial.print("[WS] Connecting to ws://"); Serial.print(WS_HOST);
    Serial.print(":"); Serial.println(WS_PORT);

    if (!wsClient.connect(WS_HOST, WS_PORT)) {
        Serial.println("[WS] TCP connect failed");
        return false;
    }

    // Send HTTP upgrade request
    wsClient.print("GET " WS_PATH " HTTP/1.1\r\n");
    wsClient.print("Host: " WS_HOST ":"); wsClient.print(WS_PORT); wsClient.print("\r\n");
    wsClient.print("Upgrade: websocket\r\n");
    wsClient.print("Connection: Upgrade\r\n");
    wsClient.print("Sec-WebSocket-Key: "); wsClient.print(ws_key); wsClient.print("\r\n");
    wsClient.print("Sec-WebSocket-Version: 13\r\n");
    wsClient.print("\r\n");
    wsClient.flush();

    // Read response (timeout 3s)
    unsigned long start = millis();
    wsRecvLen = 0;
    while (millis() - start < 3000) {
        if (wsClient.available()) {
            char c = wsClient.read();
            if (wsRecvLen < (int)sizeof(wsRecvBuf) - 1) wsRecvBuf[wsRecvLen++] = c;
            wsRecvBuf[wsRecvLen] = 0;
        }
        // Check for \r\n\r\n (end of HTTP headers)
        if (strstr(wsRecvBuf, "\r\n\r\n")) break;
        delay(1);
    }

    // Check for 101 Switching Protocols
    if (strstr(wsRecvBuf, "101") || strstr(wsRecvBuf, "switching", 10)) {
        wsConnected = true;
        wsLastPing = millis();
        Serial.println("[WS] Connected! Bi-directional audio stream ready");
        return true;
    }

    Serial.println("[WS] Handshake failed:");
    Serial.println(wsRecvBuf);
    wsClient.stop();
    return false;
}

// ── Send microphone PCM chunk to server ──
// samples: int16_t array, count: number of samples
void nirvana_stream_send_audio(const int16_t* samples, size_t count) {
    if (!wsConnected) return;
    _ws_send_binary((const uint8_t*)samples, count * 2);
}

// ── Receive TTS PCM from server, returns bytes written to outBuf ──
// Call from loop(). Writes received audio into outBuf.
// Returns: number of int16_t samples received, or 0 if none
int nirvana_stream_recv_audio(int16_t* outBuf, size_t maxSamples) {
    if (!wsConnected || !wsClient.connected()) return 0;

    int samplesRead = 0;
    size_t maxBytes = maxSamples * 2;

    while (wsClient.available() && (size_t)samplesRead * 2 < maxBytes) {
        uint8_t b = wsClient.read();

        // Quick WebSocket frame parser (server→client, unmasked)
        static enum { WS_HDR, WS_LEN, WS_PAYLOAD } state = WS_HDR;
        static size_t payloadLen = 0, payloadIdx = 0;
        static uint8_t payloadBuf[2048];

        switch (state) {
        case WS_HDR:
            // Skip first byte (FIN+opcode), check for binary/text
            state = WS_LEN;
            break;
        case WS_LEN:
            payloadLen = b & 0x7F;
            if (payloadLen == 126) { /* need 2 more bytes - defer */ }
            if (payloadLen == 0) { state = WS_HDR; break; }
            payloadIdx = 0;
            state = WS_PAYLOAD;
            break;
        case WS_PAYLOAD:
            if (payloadIdx < sizeof(payloadBuf)) {
                payloadBuf[payloadIdx++] = b;
            }
            if (payloadIdx >= payloadLen) {
                // Frame complete — copy to output
                size_t copy = (payloadLen < maxBytes - samplesRead * 2)
                              ? payloadLen : (maxBytes - samplesRead * 2);
                memcpy((uint8_t*)outBuf + samplesRead * 2, payloadBuf, copy);
                samplesRead += copy / 2;
                payloadLen = 0;
                state = WS_HDR;
            }
            break;
        }
    }

    return samplesRead;
}

// ── Compute RMS amplitude from PCM buffer ──
float nirvana_stream_rms(const int16_t* samples, size_t count) {
    if (count == 0) return 0.0f;
    double sum = 0;
    for (size_t i = 0; i < count; i++) {
        sum += (double)samples[i] * samples[i];
    }
    return sqrtf(sum / count) / 32768.0f;
}

// ── Tick: keep-alive ping + reconnect logic ──
// Call from loop()
void nirvana_stream_tick() {
    unsigned long now = millis();

    // Reconnect if needed
    if (!wsConnected && (now - wsLastReconnect > WS_RECONNECT_MS)) {
        wsLastReconnect = now;
        nirvana_stream_connect();
    }

    // Ping keep-alive every 15s
    if (wsConnected && (now - wsLastPing > WS_KEEPALIVE_MS)) {
        wsLastPing = now;
        // Send empty ping frame
        uint8_t ping[] = {0x89, 0x00};  // PING opcode, no payload
        wsClient.write(ping, 2);
    }

    // Check if connection dropped
    if (wsConnected && !wsClient.connected()) {
        wsConnected = false;
        Serial.println("[WS] Disconnected");
    }
}

#endif
