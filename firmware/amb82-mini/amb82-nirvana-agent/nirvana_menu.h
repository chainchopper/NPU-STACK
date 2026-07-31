// NIRVANA MENU — Single-button manual navigation
// Button D29 (PF_10): TAP (<400ms) = next item, HOLD (400ms+) = select/back
// No auto-cycling. You control the pace.
#ifndef NIRVANA_MENU_H
#define NIRVANA_MENU_H

#include "nirvana_config.h"

extern int sdFileCount;

#define MENU_STATE_HOME         0
#define MENU_STATE_NIRVANA_AI   1
#define MENU_STATE_APPS         2
#define MENU_STATE_MARKETPLACE  3
#define MENU_STATE_FILE_EXPL    4
#define MENU_STATE_VOICE_MEMOS  5
#define MENU_STATE_SETTINGS     6
#define MENU_STATE_OTA          7

#define BTN_DEBOUNCE_MS    30
#define BTN_HOLD_MS        250     // Hold 250ms = select (fast, responsive)
#define MENU_TIMEOUT_MS    60000   // 60s auto-return

// ── State ──
int menuState = MENU_STATE_HOME;
int menuCursor = 0;
int subCursor = 0;
unsigned long lastMenuActivity = 0;

// Button
enum { BTN_IDLE, BTN_DOWN, BTN_HELD };
int btnState = BTN_IDLE;
unsigned long btnDownAt = 0;

// ── Read button. Returns: 0=nothing, 1=TAP (move), 2=HOLD (select/back) ──
int nirvana_menu_tick() {
    bool pressed = (digitalRead(ONBOARD_BUTTON) == LOW);
    unsigned long now = millis();
    int action = 0;

    if (btnState == BTN_IDLE && pressed) {
        btnDownAt = now;
        btnState = BTN_DOWN;
    }
    if (btnState == BTN_DOWN) {
        if (!pressed) {
            // Released before hold threshold → TAP
            action = 1;
            btnState = BTN_IDLE;
        } else if (now - btnDownAt >= BTN_HOLD_MS) {
            // Held past threshold → HOLD
            action = 2;
            btnState = BTN_HELD;
        }
    }
    if (btnState == BTN_HELD && !pressed) {
        btnState = BTN_IDLE;
    }

    if (action) lastMenuActivity = now;
    return action;
}

// ── Called from .ino. btnAction: 1=tap, 2=hold.
// Returns true if display needs redraw. ──
bool nirvana_menu_handle(int btnAction) {
    if (btnAction == 0) return false;

    if (menuState == MENU_STATE_HOME) {
        if (btnAction == 1) {
            // TAP = move cursor to next card
            menuCursor = (menuCursor + 1) % 7;
            return true;
        }
        if (btnAction == 2) {
            // HOLD = enter highlighted app
            menuState = menuCursor + 1;
            subCursor = 0;
            return true;
        }
    } else {
        // Sub-screen
        if (btnAction == 1) {
            // TAP = move sub-cursor (where applicable)
            int max = 0;
            if (menuState == MENU_STATE_FILE_EXPL)     max = sdFileCount;
            else if (menuState == MENU_STATE_SETTINGS)  max = 6;
            else if (menuState == MENU_STATE_MARKETPLACE) max = 4;
            else if (menuState == MENU_STATE_VOICE_MEMOS) max = sdFileCount;
            else return false; // No cursor on this screen
            if (max > 0) { subCursor = (subCursor + 1) % max; return true; }
        }
        if (btnAction == 2) {
            // HOLD on sub-screen = go back to home
            menuState = MENU_STATE_HOME;
            subCursor = 0;
            return true;
        }
    }
    return false;
}

// ── 60-second auto-return ──
bool nirvana_menu_timeout() {
    if (menuState != MENU_STATE_HOME &&
        millis() - lastMenuActivity > MENU_TIMEOUT_MS) {
        menuState = MENU_STATE_HOME;
        subCursor = 0;
        return true;
    }
    return false;
}

#endif
