// NIRVANA AUDIO — I2S Mic + Speaker for AMB82-Mini
// Uses Ameba Pro2 AudioStream (built-in RTL8735B codec)
// Supports AMIC / DMIC, AEC, AGC, NS
#ifndef NIRVANA_AUDIO_H
#define NIRVANA_AUDIO_H

#include "AudioStream.h"
#include "nirvana_config.h"

// ── Global audio objects ──
AudioSetting audioCfg(16000, 1, USE_AUDIO_AMIC);  // 16kHz Mono, analog mic
Audio audioDev;
bool audioReady = false;

// ── Initialize audio ──
bool nirvana_audio_init() {
    Serial.println("[AUD] Init audio codec...");

    audioDev.configAudio(audioCfg);
    audioDev.begin();

    // Voice-optimized DSP: echo cancellation + auto gain + noise suppression
    audioDev.configMicAEC(1, 5);
    audioDev.configMicAGC(1, 6);
    audioDev.configMicNS(1, 12);
    audioDev.setMicGain(40);

    audioDev.configSpkAGC(1, 6);
    audioDev.configSpkNS(1, 12);
    audioDev.setSpkGain(80);

    audioDev.muteMic(0);
    audioDev.muteSpk(0);

    audioReady = true;
    Serial.println("[AUD] Codec ready (16kHz AMIC + SPK, AEC+AGC+NS)");
    return true;
}

// ── Speaker: play raw PCM samples ──
// The Audio class produces PCM via its StreamIO output; actual playout
// happens through the internal DAC path on begin(). For TTS playback,
// stream PCM data through the audio pipeline.
MMFModule& nirvana_audio_stream() {
    return audioDev;
}

// ── Mic mute / unmute ──
void nirvana_mic_mute(bool m)   { audioDev.muteMic(m ? 1 : 0); }
void nirvana_spk_mute(bool m)   { audioDev.muteSpk(m ? 1 : 0); }

// ── Adjust gains at runtime ──
void nirvana_mic_gain(uint8_t g)   { audioDev.setMicGain(g); }
void nirvana_spk_gain(uint8_t g)   { audioDev.setSpkGain(g); }

// ── Print audio info to Serial ──
void nirvana_audio_info() {
    Serial.println("[AUD] 16kHz Mono AMIC | AEC+AGC+NS enabled");
    Serial.print(  "[AUD] Mic gain: 40  Spk gain: 80\n");
}

#endif
