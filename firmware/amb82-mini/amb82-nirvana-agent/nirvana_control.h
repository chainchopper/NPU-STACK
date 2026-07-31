// NIRVANA CONTROL — Voice + MQTT + Serial remote command interface
// Voice: speak "Nirvana" + command into the mic (PCM→WebSocket→STT→action)
// MQTT: publish to npu-fleet/amb82/command {"cmd":"settings"}
// Serial: type "home", "ai", "settings", "rec", etc. USB port
#ifndef NIRVANA_CONTROL_H
#define NIRVANA_CONTROL_H

#include "nirvana_config.h"
#include "nirvana_menu.h"

// ── Command map ──
#define CMD_HOME        "home"
#define CMD_AI          "ai"
#define CMD_SETTINGS    "settings"
#define CMD_EXPLORER    "explorer"
#define CMD_MEMOS       "memos"
#define CMD_STORE       "store"
#define CMD_APPS        "apps"
#define CMD_OTA         "ota"
#define CMD_RECORD      "record"
#define CMD_STOP_REC    "stop"
#define CMD_SNAPSHOT    "snapshot"
#define CMD_BACK        "back"
#define CMD_NEXT        "next"
#define CMD_SELECT      "select"
#define CMD_UP          "up"
#define CMD_DOWN        "down"
#define CMD_VOLUME_UP   "volup"
#define CMD_VOLUME_DOWN "voldown"
#define CMD_BRIGHT_UP   "brightup"
#define CMD_BRIGHT_DOWN "brightdown"

// ── Last recognized command (for display) ──
char lastCommand[32] = "";

// ── Execute a command string (from any source: voice, MQTT, serial) ──
bool nirvana_control_exec(const char* cmd) {
    if (!cmd || cmd[0] == 0) return false;

    strncpy(lastCommand, cmd, 31); lastCommand[31] = 0;
    Serial.print("[CTRL] "); Serial.println(cmd);

    // Navigation
    if (strcmp(cmd, CMD_HOME) == 0 || strcmp(cmd, "go home") == 0) {
        menuState = MENU_STATE_HOME; subCursor = 0; return true;
    }
    if (strcmp(cmd, CMD_AI) == 0 || strcmp(cmd, "nirvana") == 0 || strcmp(cmd, "camera") == 0) {
        menuState = MENU_STATE_NIRVANA_AI; subCursor = 0; return true;
    }
    if (strcmp(cmd, CMD_SETTINGS) == 0) {
        menuState = MENU_STATE_SETTINGS; subCursor = 0; return true;
    }
    if (strcmp(cmd, CMD_EXPLORER) == 0 || strcmp(cmd, "files") == 0) {
        menuState = MENU_STATE_FILE_EXPL; subCursor = 0; return true;
    }
    if (strcmp(cmd, CMD_MEMOS) == 0 || strcmp(cmd, "recorder") == 0) {
        menuState = MENU_STATE_VOICE_MEMOS; subCursor = 0; return true;
    }
    if (strcmp(cmd, CMD_STORE) == 0 || strcmp(cmd, "marketplace") == 0) {
        menuState = MENU_STATE_MARKETPLACE; subCursor = 0; return true;
    }
    if (strcmp(cmd, CMD_APPS) == 0 || strcmp(cmd, "workspace") == 0) {
        menuState = MENU_STATE_APPS; subCursor = 0; return true;
    }
    if (strcmp(cmd, CMD_OTA) == 0 || strcmp(cmd, "update") == 0) {
        menuState = MENU_STATE_OTA; subCursor = 0; return true;
    }
    if (strcmp(cmd, CMD_BACK) == 0 || strcmp(cmd, "go back") == 0) {
        menuState = MENU_STATE_HOME; subCursor = 0; return true;
    }
    if (strcmp(cmd, CMD_NEXT) == 0 || strcmp(cmd, "down") == 0) {
        menuCursor = (menuCursor + 1) % 7; return true;
    }
    if (strcmp(cmd, CMD_SELECT) == 0 || strcmp(cmd, "enter") == 0 || strcmp(cmd, "open") == 0) {
        menuState = menuCursor + 1; subCursor = 0; return true;
    }

    // Actions
    if (strcmp(cmd, CMD_SNAPSHOT) == 0 || strcmp(cmd, "take picture") == 0) {
        extern void nirvana_vision_send_frame();
        nirvana_vision_send_frame();
        return true;
    }
    if (strcmp(cmd, CMD_RECORD) == 0 || strcmp(cmd, "start recording") == 0) {
        extern const char* nirvana_recorder_start();
        nirvana_recorder_start();
        return true;
    }
    if (strcmp(cmd, CMD_STOP_REC) == 0 || strcmp(cmd, "stop recording") == 0) {
        extern const char* nirvana_recorder_stop();
        nirvana_recorder_stop();
        extern int nirvana_sd_list(char names[][32], int maxFiles);
        extern int sdFileCount;
        extern char sdFiles[12][32];
        sdFileCount = nirvana_sd_list(sdFiles, 12);
        return true;
    }

    // Settings quick-adjust
    if (strcmp(cmd, CMD_VOLUME_UP) == 0) {
        extern uint8_t nvCfg_volume;  // accessed via nirvana_config_storage
        return true;
    }

    return false;
}

// ── Serial command parser (call from loop) ──
// Type commands in Serial Monitor: "home", "ai", "settings", "snapshot", etc.
void nirvana_control_serial() {
    static char serialBuf[64];
    static int  serialIdx = 0;

    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (serialIdx > 0) {
                serialBuf[serialIdx] = 0;
                nirvana_control_exec(serialBuf);
                serialIdx = 0;
            }
        } else if (serialIdx < 63) {
            serialBuf[serialIdx++] = c;
        }
    }
}

// ── MQTT command callback (called from nirvana_wifi.h when command topic received) ──
// Topic: npu-fleet/amb82/command
// Payload: JSON {"cmd":"settings"} or plain text "settings"
void nirvana_control_mqtt(const char* topic, const uint8_t* payload, unsigned int length) {
    char buf[64];
    unsigned int len = (length < 63) ? length : 63;
    memcpy(buf, payload, len);
    buf[len] = 0;

    // Try JSON first: {"cmd":"settings"}
    const char* cmdStart = strstr(buf, "\"cmd\":\"");
    if (cmdStart) {
        cmdStart += 7;
        char cmd[32]; int i = 0;
        while (*cmdStart && *cmdStart != '"' && i < 31) cmd[i++] = *cmdStart++;
        cmd[i] = 0;
        if (nirvana_control_exec(cmd)) return;
    }

    // Fallback: treat entire payload as command
    nirvana_control_exec(buf);
}

#endif
