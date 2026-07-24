#ifndef NIRVANA_AUDIO_H
#define NIRVANA_AUDIO_H

// I2S audio for AMB82-Mini
// Mic input + Speaker output (Opus codec planned)

#if FEATURE_AUDIO
bool audioReady = false;
bool audioListening = false;

// ═══════════════ INIT ═══════════════
bool nirvana_audio_init() {
    // Ameba I2S setup:
    // I2S.begin(I2S_PHILIPS_MODE, AUDIO_SAMPLE_RATE, 16);
    // I2S.setPins(I2S_BCLK, I2S_LRCLK, I2S_MIC_DIN, I2S_SPKR_DOUT);

    Serial.println("[AUDIO] I2S initialized (placeholder)");
    audioReady = true;
    return true;
}

// ═══════════════ START LISTENING ═══════════════
void nirvana_audio_listen_start() {
    if (!audioReady) return;
    audioListening = true;
    Serial.println("[AUDIO] Listening started");
}

// ═══════════════ STOP LISTENING ═══════════════
void nirvana_audio_listen_stop() {
    audioListening = false;
    Serial.println("[AUDIO] Listening stopped");
}

// ═══════════════ PLAY AUDIO ═══════════════
void nirvana_audio_play(uint8_t* data, size_t length) {
    if (!audioReady) return;
    // I2S.write(data, length);
    Serial.printf("[AUDIO] Play %d bytes\n", length);
}

// ═══════════════ WAKE WORD DETECTION ═══════════════
// Use simple energy detection or NN-based wake word
bool nirvana_audio_wake_word_detected() {
    // Placeholder: check mic energy threshold
    // Or use Ameba NN engine for keyword spotting
    return false;
}

#else
bool nirvana_audio_init() { return false; }
void nirvana_audio_listen_start() {}
void nirvana_audio_listen_stop() {}
void nirvana_audio_play(uint8_t* data, size_t length) {}
bool nirvana_audio_wake_word_detected() { return false; }
#endif

#endif // NIRVANA_AUDIO_H
