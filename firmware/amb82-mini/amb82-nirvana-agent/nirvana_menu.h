// NIRVANA MENU SYSTEM — Single-button navigation state machine
// Button D29 (PF_10): Short press = next item, Long press = select/enter
// 7 screens: Home, Nirvana AI, Workspace, Marketplace, Explorer, Memos, Settings
#ifndef NIRVANA_MENU_H
#define NIRVANA_MENU_H

#include "nirvana_config.h"

extern int sdFileCount;  // Defined in main .ino via nirvana_sd.h

#define MENU_STATE_HOME         0
#define MENU_STATE_NIRVANA_AI   1
#define MENU_STATE_APPS         2
#define MENU_STATE_MARKETPLACE  3
#define MENU_STATE_FILE_EXPL    4
#define MENU_STATE_VOICE_MEMOS  5
#define MENU_STATE_SETTINGS     6
#define MENU_STATE_OTA          7
#define MENU_STATE_COUNT        8

#define BTN_DEBOUNCE_MS    50
#define BTN_LONG_PRESS_MS  800
#define MENU_TIMEOUT_MS    30000    // Auto-return to home after 30s idle

// ── Menu State ──
int menuState = MENU_STATE_HOME;
int menuCursor = 0;            // Selected item within home screen
int subCursor = 0;             // Selected item within sub-screens
unsigned long lastBtnCheck = 0;
unsigned long lastMenuActivity = 0;

// Button state machine
enum { BTN_IDLE, BTN_PRESSED, BTN_HELD, BTN_RELEASED };
int btnState = BTN_IDLE;
unsigned long btnPressStart = 0;
bool btnWasPressed = false;

// ── Button Read + State Machine ──
// Call this in loop(). Returns: 0=nothing, 1=short press, 2=long press
int nirvana_menu_tick() {
    int action = 0;
    bool pressed = (digitalRead(ONBOARD_BUTTON) == LOW);

    switch (btnState) {
    case BTN_IDLE:
        if (pressed) {
            btnPressStart = millis();
            btnState = BTN_PRESSED;
        }
        break;
    case BTN_PRESSED:
        if (!pressed) {
            // Released before long-press threshold → short press
            if (millis() - btnPressStart < BTN_LONG_PRESS_MS) {
                action = 1; // SHORT
            }
            btnState = BTN_IDLE;
        } else if (millis() - btnPressStart >= BTN_LONG_PRESS_MS) {
            action = 2; // LONG
            btnState = BTN_HELD;
        }
        break;
    case BTN_HELD:
        if (!pressed) {
            btnState = BTN_IDLE;
        }
        break;
    }

    if (action) lastMenuActivity = millis();
    return action;
}

// ── Menu Navigation ──
// Returns true if the display needs redrawing
// In sub-screens: short press = cycle sub-cursor, long press = back to home
// In home: short = move cursor, long = enter
bool nirvana_menu_handle(int btnAction) {
    if (btnAction == 0) return false;

    if (menuState == MENU_STATE_HOME) {
        if (btnAction == 1) {  // Short: move cursor
            menuCursor = (menuCursor + 1) % 7;
            return true;
        }
        if (btnAction == 2) {  // Long: enter
            menuState = menuCursor + 1;
            menuCursor = 0;
            return true;
        }
    } else {
        // Sub-screen navigation
        if (btnAction == 1) {  // Short: cycle sub-cursor
            subCursor++;
            // Wrap based on screen
            int max = 0;
            if (menuState == MENU_STATE_FILE_EXPL)     max = sdFileCount;
            else if (menuState == MENU_STATE_SETTINGS)  max = 6;
            else if (menuState == MENU_STATE_MARKETPLACE) max = 4;
            else if (menuState == MENU_STATE_NIRVANA_AI)  return false; // No cursor
            else if (menuState == MENU_STATE_APPS)        return false; // No cursor
            else if (menuState == MENU_STATE_VOICE_MEMOS) max = sdFileCount;
            else if (menuState == MENU_STATE_OTA)         return false; // No cursor
            if (max > 0) subCursor %= max;
            return true;
        }
        if (btnAction == 2) {  // Long: back to home
            menuState = MENU_STATE_HOME;
            menuCursor = 0;
            subCursor = 0;
            return true;
        }
    }
    return false;
}

// ── Auto-return to home after timeout ──
bool nirvana_menu_timeout() {
    if (menuState != MENU_STATE_HOME &&
        millis() - lastMenuActivity > MENU_TIMEOUT_MS) {
        menuState = MENU_STATE_HOME;
        menuCursor = 0;
        return true;
    }
    return false;
}

#endif
