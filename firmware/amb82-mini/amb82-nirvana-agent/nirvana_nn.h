// NIRVANA NN ENGINE — Object Detection + Face Detection
// Uses Ameba Pro2 VIPLite NN accelerator (RTL8735B)
// Models: YOLOv4 Tiny, SCRFD, MobileFaceNet (from FWFS)
#ifndef NIRVANA_NN_H
#define NIRVANA_NN_H

#include "VideoStream.h"
#include "NNObjectDetection.h"
#include "NNFaceDetection.h"
#include "ObjectClassList.h"
#include "nirvana_config.h"

// ── Globals ──
NNObjectDetection nnOD;
NNFaceDetection   nnFace;

// Detection callback results (updated every frame)
volatile int   odCount = 0;
volatile char  odTopLabel[32] = "";
volatile int   odTopScore = 0;
volatile int   faceCount = 0;
volatile bool  nnOD_ready = false;
volatile bool  nnFace_ready = false;
volatile bool  nnModelOk = true;   // Set false if model fails to load

// ── Object detection callback ──
void _nirvana_od_callback(std::vector<ObjectDetectionResult> results) {
    odCount = nnOD.getResultCount();
    if (odCount > 0) {
        // Find highest-confidence object
        int best = 0, bestScore = 0;
        for (int i = 0; i < odCount; i++) {
            int s = results[i].score();
            if (s > bestScore) { bestScore = s; best = i; }
        }
        int t = results[best].type();
        strncpy((char*)odTopLabel, itemList[t].objectName, 31);
        odTopLabel[31] = 0;
        odTopScore = bestScore;
    } else {
        odTopLabel[0] = 0;
        odTopScore = 0;
    }
}

// ── Face detection callback ──
void _nirvana_face_callback(std::vector<FaceDetectionResult> results) {
    faceCount = results.size();
}

// ── Init object detection ──
bool nirvana_nn_od_init(VideoSetting& nnConfig) {
    Serial.println("[NN-OD] Init YOLOv7 Tiny...");

    nnOD.configVideo(nnConfig);
    // Try YOLOv7 Tiny (0x03) — different FWFS slot, may not be corrupt
    // If still broken, try YOLOv3 Tiny (0x01) or DEFAULT_YOLOV4TINY (0x02)
    nnOD.modelSelect(OBJECT_DETECTION, DEFAULT_YOLOV7TINY, NA_MODEL, NA_MODEL);
    nnOD.configThreshold(0.45, 0.35);
    nnOD.setResultCallback(_nirvana_od_callback);
    nnOD.begin();

    delay(200);
    uint16_t check = nnOD.getResultCount(); (void)check;

    nnOD_ready = true;
    Serial.println("[NN-OD] Init complete (check Serial for vipnn errors)");
    return true;
}

// ── Init face detection ──
bool nirvana_nn_face_init(VideoSetting& nnConfig) {
    Serial.println("[NN-FACE] Init SCRFD...");

    nnFace.configVideo(nnConfig);
    nnFace.modelSelect(FACE_DETECTION, NA_MODEL, DEFAULT_SCRFD, NA_MODEL);
    nnFace.setResultCallback(_nirvana_face_callback);
    nnFace.begin();

    nnFace_ready = true;
    Serial.println("[NN-FACE] SCRFD ready");
    return true;
}

// ── Stop NN pipelines ──
void nirvana_nn_od_stop()  { if (nnOD_ready)  { nnOD.end();  nnOD_ready  = false; } }
void nirvana_nn_face_stop(){ if (nnFace_ready){ nnFace.end();nnFace_ready= false; } }

#endif
