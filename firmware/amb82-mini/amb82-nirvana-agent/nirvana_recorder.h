// NIRVANA RECORDER — WAV capture to SD card via I2S mic
// Writes 16kHz Mono 16-bit PCM RIFF/WAV files to /recordings/
// Full WAV header patching on stop (chunk sizes rewritten)
//
// REAL PCM HOOK: The Ameba Audio class streams PCM via StreamIO/MMF.
// To capture raw samples, you need to either:
//   a) Pipe Audio → custom MMF sink module that writes to SD
//   b) Use I2S DMA buffer (hal_i2s.h) to read raw samples
// For now, this writes a valid WAV skeleton and simulates capture
// with silence. The REC button + file index + SD integration all work.
#ifndef NIRVANA_RECORDER_H
#define NIRVANA_RECORDER_H

#include "ff.h"
#include "nirvana_config.h"
#include "nirvana_sd.h"
#include "AudioStream.h"

#define REC_DIR         "/recordings/"
#define REC_SAMPLE_RATE 16000
#define REC_BITS        16
#define REC_CHANNELS    1
#define REC_BUFFER_SIZE 1024   // PCM samples per write chunk

// ── WAV Header (little-endian, packed) ──
typedef struct __attribute__((packed)) {
    char     riff[4];        // "RIFF"
    uint32_t fileSize;       // 36 + dataSize
    char     wave[4];        // "WAVE"
    char     fmt_[4];        // "fmt "
    uint32_t fmtSize;        // 16
    uint16_t audioFormat;    // 1 = PCM
    uint16_t numChannels;    // 1
    uint32_t sampleRate;     // 16000
    uint32_t byteRate;       // sampleRate * numChannels * bits/8
    uint16_t blockAlign;     // numChannels * bits/8
    uint16_t bitsPerSample;  // 16
    char     data[4];        // "data"
    uint32_t dataSize;       // bytes of PCM
} WavHeader;

// ── Recorder State ──
FIL     recFile;
bool    recActive = false;
char    recFilename[64];
uint32_t recBytesWritten = 0;
unsigned long recLastCapture = 0;

// ── Build WAV header ──
void _rec_make_header(WavHeader* h, uint32_t dataBytes) {
    memcpy(h->riff, "RIFF", 4);
    h->fileSize = 36 + dataBytes;
    memcpy(h->wave, "WAVE", 4);
    memcpy(h->fmt_, "fmt ", 4);
    h->fmtSize = 16;
    h->audioFormat = 1;
    h->numChannels = REC_CHANNELS;
    h->sampleRate = REC_SAMPLE_RATE;
    h->byteRate = REC_SAMPLE_RATE * REC_CHANNELS * (REC_BITS / 8);
    h->blockAlign = REC_CHANNELS * (REC_BITS / 8);
    h->bitsPerSample = REC_BITS;
    memcpy(h->data, "data", 4);
    h->dataSize = dataBytes;
}

// ── Ensure /recordings/ directory exists on SD ──
void _rec_ensure_dir() {
    DIR d;
    if (f_opendir(&d, REC_DIR) != FR_OK) {
        f_mkdir(REC_DIR);
        Serial.println("[REC] Created /recordings/");
    } else {
        f_closedir(&d);
    }
}

// ── Generate filename: /recordings/memo_XXXXXXXX.wav ──
void _rec_make_name() {
    // Use uptime as unique ID (seconds since boot)
    unsigned long ts = millis() / 1000;
    snprintf(recFilename, sizeof(recFilename),
             "%smemo_%lu.wav", REC_DIR, ts);
}

// ── START recording ──
// Returns filename on success, NULL on failure
const char* nirvana_recorder_start() {
    if (recActive) return NULL;
    if (!sdReady) {
        Serial.println("[REC] No SD card");
        return NULL;
    }

    _rec_ensure_dir();
    _rec_make_name();
    recBytesWritten = 0;

    // Open file, write placeholder header
    FRESULT res = f_open(&recFile, recFilename,
                         FA_WRITE | FA_CREATE_ALWAYS);
    if (res != FR_OK) {
        Serial.print("[REC] Open failed: "); Serial.println(res);
        return NULL;
    }

    WavHeader hdr;
    _rec_make_header(&hdr, 0);  // dataSize=0 placeholder
    UINT bw;
    f_write(&recFile, &hdr, sizeof(WavHeader), &bw);

    // Sync to flush header immediately
    f_sync(&recFile);

    recActive = true;
    recLastCapture = millis();

    Serial.print("[REC] Started → "); Serial.println(recFilename);
    return recFilename;
}

// ── TICK: capture PCM chunk from mic → SD ──
// Call from loop() at ~50Hz. Writes ~256 samples per call.
// REAL IMPL: Replace _rec_capture() with I2S DMA buffer read.
void nirvana_recorder_tick() {
    if (!recActive) return;

    // Throttle to ~50 writes/sec (256 samples * 50 = 12800 sps, close to 16k)
    unsigned long now = millis();
    if (now - recLastCapture < 20) return;
    recLastCapture = now;

    // ── SIMULATED CAPTURE (replace with real I2S DMA read) ──
    // Real implementation reads from Ameba audio pipeline:
    //   int16_t pcm[256];
    //   size_t n = audio_read_pcm(pcm, 256);  // from I2S DMA buffer
    //   f_write(&recFile, pcm, n * 2, &bw);

    int16_t silence[256] = {0};  // 256 samples of silence = placeholder
    UINT bw;
    f_write(&recFile, silence, sizeof(silence), &bw);
    recBytesWritten += bw;
}

// ── STOP recording — patch header with final size ──
// Returns filename of completed recording
const char* nirvana_recorder_stop() {
    if (!recActive) return NULL;

    recActive = false;

    // Calculate final sizes
    WavHeader hdr;
    _rec_make_header(&hdr, recBytesWritten);

    // Rewind to byte 0 and rewrite header
    f_lseek(&recFile, 0);
    UINT bw;
    f_write(&recFile, &hdr, sizeof(WavHeader), &bw);

    // Flush & close
    f_sync(&recFile);
    f_close(&recFile);

    char sz[16];
    nirvana_sd_fmt_size(recBytesWritten, sz, sizeof(sz));
    Serial.print("[REC] Stopped: "); Serial.print(recFilename);
    Serial.print("  "); Serial.print(sz); Serial.print(" PCM\n");

    return recFilename;
}

// ── Check recording state ──
bool nirvana_recorder_is_active() { return recActive; }

// ── Get current recording elapsed seconds ──
uint32_t nirvana_recorder_elapsed() {
    if (!recActive) return 0;
    // bytes / byteRate = seconds
    uint32_t byteRate = REC_SAMPLE_RATE * REC_CHANNELS * (REC_BITS/8);
    return recBytesWritten / byteRate;
}

#endif
