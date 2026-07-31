// NIRVANA VISION — Camera JPEG capture + HTTP POST to backend
// Captures JPEG from Ameba VideoStream Channel 1 (JPEG encoder)
// Posts via multipart/form-data to Nirvana AI backend endpoint
// Backend receives frame, runs multimodal AI, returns TTS/RGB565
#ifndef NIRVANA_VISION_H
#define NIRVANA_VISION_H

#include "VideoStream.h"
#include "nirvana_config.h"
#include "nirvana_camera.h"

// ── Backend endpoint ──
#ifndef VISION_HOST
#define VISION_HOST  MQTT_HOST          // Same box as MQTT broker
#endif
#define VISION_PORT         5000
#define VISION_URI          "/api/nirvana/multimodal"
#define VISION_TIMEOUT_MS   8000

// ── State ──
bool visionUploading = false;
char visionStatus[64] = "Idle";
unsigned long visionLastUpload = 0;

// ── Build & send a multipart/form-data POST with JPEG frame ──
// Returns: true if frame sent and response received
bool nirvana_vision_send_frame() {
    if (WiFi.status() != WL_CONNECTED) {
        snprintf(visionStatus, sizeof(visionStatus), "No WiFi");
        Serial.println("[VISION] WiFi not connected");
        return false;
    }

    // ── Capture JPEG from camera channel 1 ──
    uint32_t jpgAddr = 0, jpgLen = 0;
    Camera.getImage(1, &jpgAddr, &jpgLen);
    if (jpgLen == 0 || jpgAddr == 0) {
        snprintf(visionStatus, sizeof(visionStatus), "No frame");
        Serial.println("[VISION] Camera returned empty frame");
        return false;
    }

    uint8_t* jpgBuf = (uint8_t*)jpgAddr;
    snprintf(visionStatus, sizeof(visionStatus), "Sending %lu B...", jpgLen);
    Serial.print("[VISION] JPEG captured: "); Serial.print(jpgLen);
    Serial.println(" bytes");

    // ── Connect to backend ──
    WiFiClient client;
    if (!client.connect(VISION_HOST, VISION_PORT)) {
        snprintf(visionStatus, sizeof(visionStatus), "Connect fail");
        Serial.println("[VISION] TCP connect failed");
        return false;
    }

    // ── Build multipart POST ──
    const char* boundary = "----NirvanaVisionOS";
    char headerBuf[512];
    char footerBuf[64];
    uint32_t bodyLen = 0;

    // Compute body size:
    //   --boundary\r\n
    //   Content-Disposition: form-data; name="camera"; filename="frame.jpg"\r\n
    //   Content-Type: image/jpeg\r\n\r\n
    //   {jpgLen bytes}
    //   \r\n--boundary--\r\n

    // Custom header (we send it raw)
    const char* partHeaderFmt =
        "--%s\r\n"
        "Content-Disposition: form-data; name=\"camera\"; filename=\"frame.jpg\"\r\n"
        "Content-Type: image/jpeg\r\n\r\n";
    const char* partFooterFmt = "\r\n--%s--\r\n";

    int headerLen = snprintf(headerBuf, sizeof(headerBuf), partHeaderFmt, boundary);
    int footerLen = snprintf(footerBuf, sizeof(footerBuf), partFooterFmt, boundary);
    bodyLen = headerLen + jpgLen + footerLen;

    // Send HTTP request line + headers
    client.print("POST " VISION_URI " HTTP/1.1\r\n");
    client.print("Host: " VISION_HOST "\r\n");
    client.print("User-Agent: NirvanaOS-Vision/3.3\r\n");
    client.print("Content-Type: multipart/form-data; boundary=");
    client.print(boundary);
    client.print("\r\n");
    client.print("Content-Length: ");
    client.print(bodyLen);
    client.print("\r\n");
    client.print("Connection: close\r\n\r\n");

    // Send body in 3 parts
    client.write((uint8_t*)headerBuf, headerLen);
    client.write(jpgBuf, jpgLen);
    client.write((uint8_t*)footerBuf, footerLen);
    client.flush();

    // ── Read response (just the first 256 bytes) ──
    unsigned long start = millis();
    char respBuf[256] = "";
    int respIdx = 0;
    while (client.connected() || client.available()) {
        if (client.available()) {
            char c = client.read();
            if (respIdx < 255) respBuf[respIdx++] = c;
            respBuf[respIdx] = 0;
        }
        if (millis() - start > VISION_TIMEOUT_MS) break;
    }
    client.stop();

    // Check for HTTP 200
    bool ok = (strstr(respBuf, "200 OK") != NULL) ||
              (strstr(respBuf, "200") != NULL);
    if (ok) {
        snprintf(visionStatus, sizeof(visionStatus), "OK (%lu B)", jpgLen);
        Serial.println("[VISION] Frame sent OK");
    } else {
        snprintf(visionStatus, sizeof(visionStatus), "HTTP err");
        Serial.print("[VISION] Response: "); Serial.println(respBuf);
    }

    visionLastUpload = millis();
    return ok;
}

#endif
