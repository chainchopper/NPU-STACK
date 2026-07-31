// NIRVANA CAMERA — CSI OV5647/GC2053 driver for AMB82-Mini
// Uses Ameba Pro2 VideoStream + StreamIO pipeline
// Channel 0: H264 FHD RTSP | Channel 3: RGB 576x320 NN input
#ifndef NIRVANA_CAMERA_H
#define NIRVANA_CAMERA_H

#include "VideoStream.h"
#include "StreamIO.h"
#include "nirvana_config.h"

#define CAM_CH_MAIN   0  // H264 FHD stream
#define CAM_CH_NN     3  // RGB low-res for NN input
#define CAM_NN_W      576
#define CAM_NN_H      320
#define CAM_NN_FPS    10

// ── Global pipeline objects ──
VideoSetting camConfig(VIDEO_FHD, 30, VIDEO_H264, 0);   // FHD H264
VideoSetting camConfigNN(CAM_NN_W, CAM_NN_H, CAM_NN_FPS, VIDEO_RGB, 0);

StreamIO camStreamer(1, 1);   // Main channel → RTSP
StreamIO camStreamerNN(1, 1); // NN channel → Object Detection

bool camReady = false;

// ── Initialize camera (ISP auto-configures on Ameba SDK) ──
bool nirvana_camera_init() {
    Serial.println("[CAM] Init CSI camera...");

    // Main channel: FHD H264 @ 30fps
    camConfig.setBitrate(2 * 1024 * 1024);  // 2 Mbps
    Camera.configVideoChannel(CAM_CH_MAIN, camConfig);

    // NN channel: RGB 576×320 @ 10fps
    Camera.configVideoChannel(CAM_CH_NN, camConfigNN);

    Camera.videoInit();
    Serial.println("[CAM] CSI ready (FHD H264 + RGB NN)");
    camReady = true;
    return true;
}

// ── Start streaming main channel ──
bool nirvana_camera_start(int ch) {
    if (!camReady) return false;
    Camera.channelBegin(ch);
    char buf[32];
    snprintf(buf, sizeof(buf), "[CAM] Channel %d streaming", ch);
    Serial.println(buf);
    return true;
}

// ── Capture JPEG snapshot to buffer ──
// Returns: true if image captured, data in *addr + *len
bool nirvana_snapshot(uint32_t* addr, uint32_t* len) {
    if (!camReady) return false;
    // Channel 1 = JPEG encoder
    Camera.getImage(1, addr, len);
    return (*len > 0);
}

// ── StreamIO helper: pipe camera channel to output module ──
void nirvana_camera_pipe_to(int ch, MMFModule& output) {
    // Use existing streamer or create ad-hoc
    StreamIO* sio = (ch == CAM_CH_NN) ? &camStreamerNN : &camStreamer;
    sio->registerInput(Camera.getStream(ch));
    sio->registerOutput(output);
    if (ch == CAM_CH_NN) {
        sio->setStackSize();
        sio->setTaskPriority();
    }
    if (sio->begin() != 0) {
        Serial.println("[CAM] StreamIO link failed");
    }
}

#endif
