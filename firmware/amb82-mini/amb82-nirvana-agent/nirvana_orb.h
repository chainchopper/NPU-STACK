// NIRVANA ORB — Audio-reactive waveform engine on bit-banged ILI9341
// Pure math: RMS amplitude drives 3-layer parametric sine wave ring
// No LVGL, no canvas — direct pixel fill on our proven SPI driver
#ifndef NIRVANA_ORB_H
#define NIRVANA_ORB_H

#include "nirvana_config.h"
#include <math.h>

// ── Orb geometry ──
#define ORB_CX     120   // Center X
#define ORB_CY     140   // Center Y
#define ORB_R       85   // Base radius
#define NUM_WAVE    72    // Points per wave layer

// ── State ──
float orbAmplitude = 0.0f;     // Target RMS (0.0 – 1.0), set by mic/stream
float orbSmoothed  = 0.0f;     // Inertia-smoothed amplitude
uint32_t orbPhase  = 0;        // Continuous phase accumulator
unsigned long orbLastDraw = 0;

// ── Feed amplitude from audio source (call from loop or callback) ──
void nirvana_orb_feed(float rms) {
    if (rms > 1.0f) rms = 1.0f;
    if (rms < 0.0f) rms = 0.0f;
    orbAmplitude = rms;
}

// ── Draw one frame of the animated orb ──
// Call at ~30-40fps from loop(). Returns true if anything was drawn.
bool nirvana_orb_draw() {
    unsigned long now = millis();
    if (now - orbLastDraw < 25) return false;  // Cap at ~40fps
    orbLastDraw = now;

    // Smoothing — inertia so the ring pulses rather than jumps
    orbSmoothed += (orbAmplitude - orbSmoothed) * 0.25f;
    orbPhase += 12;

    // Clear orb area (square region around the ring)
    nirvana_display_fill_rect(ORB_CX - ORB_R - 4, ORB_CY - ORB_R - 4,
                              (ORB_R + 4) * 2, (ORB_R + 4) * 2, NIRVANA_BLACK);

    // ── Draw background circle (subtle guide ring) ──
    for (int a = 0; a < 360; a += 2) {
        float ra = a * M_PI / 180.0f;
        int px = ORB_CX + (int)(ORB_R * cosf(ra));
        int py = ORB_CY + (int)(ORB_R * sinf(ra));
        nirvana_display_fill_rect(px, py, 2, 2, 0x2104);  // Dim purple
    }

    // ── 3 wave layers with color morphing ──
    for (int layer = 0; layer < 3; layer++) {
        float phaseOffset = (layer * 2.0f * M_PI / 3.0f) + (orbPhase * 0.04f);
        float freqScale   = 1.5f + (layer * 0.5f);
        float rMul = 0.85f - layer * 0.1f;  // Inner layers closer to center

        // Color morph: cyan → purple as amplitude rises
        uint8_t rc = (uint8_t)(80 + orbSmoothed * 175);
        uint8_t gc = (uint8_t)(200 * (1.0f - orbSmoothed * 0.7f));
        uint8_t bc = (uint8_t)(200 + layer * 30);
        uint16_t color = ((rc >> 3) << 11) | ((gc >> 2) << 5) | (bc >> 3);

        int prevX = 0, prevY = 0;
        for (int i = 0; i <= NUM_WAVE; i++) {
            float t = (float)i / NUM_WAVE;
            float angle = t * 2.0f * M_PI;

            // Gaussian envelope — tapers to zero at edges
            float envelope = sinf(t * M_PI);

            // Compound sine
            float wave = sinf(angle * freqScale + phaseOffset);

            // Radius = base_radius scaled by amplitude and envelope
            float r = ORB_R * rMul * (0.3f + orbSmoothed * 0.7f * envelope * fabsf(wave));

            int px = ORB_CX + (int)(r * cosf(angle));
            int py = ORB_CY + (int)(r * sinf(angle));

            if (i > 0) {
                // Draw thick line segment between consecutive points
                int dx = px - prevX, dy = py - prevY;
                int steps = abs(dx) > abs(dy) ? abs(dx) : abs(dy);
                if (steps < 1) steps = 1;
                for (int s = 0; s <= steps; s++) {
                    int sx = prevX + (dx * s) / steps;
                    int sy = prevY + (dy * s) / steps;
                    nirvana_display_fill_rect(sx, sy, 3, 3, color);
                }
            }
            prevX = px; prevY = py;
        }
    }

    // ── Center dot (pulses with amplitude) ──
    int dotSize = 3 + (int)(orbSmoothed * 10);
    nirvana_display_fill_rect(ORB_CX - dotSize/2, ORB_CY - dotSize/2,
                              dotSize, dotSize, 0x07FF); // Bright cyan

    return true;
}

#endif
