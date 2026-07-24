#ifndef NIRVANA_CAMERA_H
#define NIRVANA_CAMERA_H

#include <Arduino.h>
// Ameba camera API: <VideoStream.h>, <NNObjectDetection.h>
// See: https://www.amebaiot.com/en/amebad-arduino-camera/

#if FEATURE_CAMERA
// Include Ameba camera libraries
// Note: These only compile with AmebaD board package
// #include <VideoStream.h>
// #include <NNObjectDetection.h>

bool cameraReady = false;
unsigned long lastCapture = 0;
#define CAPTURE_INTERVAL_MS 5000  // 5s between captures

// ═══════════════ INIT ═══════════════
bool nirvana_camera_init() {
    // CameraConfig config;
    // config.setPins(CAM_I2C_SDA, CAM_I2C_SCL);
    // VideoSetting configH264(VIDEO_H264, 640, 480, 10);
    // VideoSetting configJPEG(VIDEO_JPEG, 320, 240, 5);
    // Camera.begin(config, configH264, configJPEG);

    Serial.println("[CAM] OV5647 initialized (placeholder — compile with Ameba SDK)");
    cameraReady = true;
    return true;
}

// ═══════════════ CAPTURE JPEG ═══════════════
bool nirvana_camera_capture(uint8_t** buffer, size_t* length) {
    if (!cameraReady) return false;
    // Camera.getImage(buffer, length);
    Serial.println("[CAM] Capture (placeholder)");
    return true;
}

// ═══════════════ NN OBJECT DETECTION ═══════════════
bool nirvana_camera_detect() {
    if (!cameraReady) return false;
    // NNObjectDetectionResult result = NNObjectDetection.detect();
    // Serial.printf("[NPU] Found %d objects\n", result.count());
    // for (int i = 0; i < result.count(); i++) {
    //     Serial.printf("  %s: %.2f @ (%d,%d,%d,%d)\n",
    //         result.label(i), result.confidence(i),
    //         result.x(i), result.y(i), result.w(i), result.h(i));
    // }
    Serial.println("[NPU] Detection (placeholder)");
    return true;
}

// ═══════════════ STREAM MJPEG ═══════════════
// RTSP or MJPEG over HTTP for fleet dashboard
void nirvana_camera_stream() {
    // Placeholder for video streaming
    // Use RTSP: rtsp://<ip>:554/stream
}

#else
bool nirvana_camera_init() { return false; }
bool nirvana_camera_capture(uint8_t** buffer, size_t* length) { return false; }
bool nirvana_camera_detect() { return false; }
#endif

#endif // NIRVANA_CAMERA_H
