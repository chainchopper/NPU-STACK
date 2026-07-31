// NIRVANA MENU SYSTEM — Auto-cycling single-button navigation
// Cursor moves automatically every 2s — just press to select, hold to go back.
// Button D29 (PF_10): Short press = SELECT/ENTER, Long press = GO BACK/CANCEL
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
#define BTN_LONG_PRESS_MS  600
#define AUTO_CYCLE_MS      2000   // Cursor advances every 2 seconds
#define MENU_TIMEOUT_MS    30000   // Auto-return to home after 30s idle

// ── Menu State ──
int menuState = MENU_STATE_HOME;
int menuCursor = 0;            // Selected item within home screen
int subCursor = 0;             // Selected item within sub-screens
unsigned long lastAutoCycle = 0;
unsigned long lastBtnCheck = 0;
unsigned long lastMenuActivity = 0;

// Button state machine
enum { BTN_IDLE, BTN_PRESSED, BTN_HELD };
int btnState = BTN_IDLE;
unsigned long btnPressStart = 0;

// ── Button Read + State Machine ──
// Returns: 0=nothing, 1=short press (select), 2=long press (back)
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
            // Released before threshold → SHORT (select)
            action = 1;
            btnState = BTN_IDLE;
        } else if (millis() - btnPressStart >= BTN_LONG_PRESS_MS) {
            // Held past threshold → LONG (back)
            action = 2;
            btnState = BTN_HELD;
        }
        break;
    case BTN_HELD:
        if (!pressed) btnState = BTN_IDLE;
        break;
    }

    if (action) lastMenuActivity = millis();
    return action;
}

// ── Auto-advance cursor on home screen ──
// Returns true if cursor moved (needs redraw)
bool nirvana_menu_auto_cycle() {
    unsigned long now = millis();
    if (menuState != MENU_STATE_HOME) return false;
    if (now - lastAutoCycle < AUTO_CYCLE_MS) return false;
    lastAutoCycle = now;

    menuCursor = (menuCursor + 1) % 7;
    return true;
}

// ── Menu Navigation (called AFTER .ino handles special cases) ──
// On home: short=enter highlighted item, long ignored (auto-cycle moves cursor)
// On sub-screens: short=back, long=back (both go home)
// Returns true if display needs redraw
bool nirvana_menu_handle(int btnAction) {
    if (btnAction == 0) return false;

    if (menuState == MENU_STATE_HOME) {
        if (btnAction == 1 || btnAction == 2) {
            // Short or long on home = SELECT highlighted item
            menuState = menuCursor + 1;
            menuCursor = 0;
            subCursor = 0;
            return true;
        }
    } else {
        // Sub-screen: any press = GO BACK to home
        // (unless handled specially in .ino before reaching here)
        menuState = MENU_STATE_HOME;
        menuCursor = 0;
        subCursor = 0;
        return true;
    }
    return false;
}

// ── Auto-return to home after timeout ──
bool nirvana_menu_timeout() {
    if (menuState != MENU_STATE_HOME &&
        millis() - lastMenuActivity > MENU_TIMEOUT_MS) {
        menuState = MENU_STATE_HOME;
        menuCursor = 0;
        subCursor = 0;
        return true;
    }
    return false;
}

#endif
