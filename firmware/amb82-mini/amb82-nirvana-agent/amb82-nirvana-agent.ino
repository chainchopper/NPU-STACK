// ╔══════════════════════════════════════════════════════════╗
// ║   NIRVANA OS — AMB82-Mini FULL STACK                   ║
// ║   RTL8735B Cortex-M33 @ 500MHz + VIPLite NN Engine     ║
// ║   Menu-driven UI with button navigation (D29)           ║
// ║   ILI9341 + CSI + I2S + NN + MQTT + SD                 ║
// ║   Bit-banged SPI LCD — zero peripheral conflicts       ║
// ╚══════════════════════════════════════════════════════════╝

#include "nirvana_config.h"
#include "nirvana_ili9341.h"
#include "nirvana_wifi.h"
#include "nirvana_camera.h"
#include "nirvana_audio.h"
#include "nirvana_nn.h"
#include "nirvana_menu.h"
#include "nirvana_sd.h"
#include "nirvana_orb.h"
#include "nirvana_ota.h"
#include "nirvana_recorder.h"
#include "nirvana_vision.h"
#include "nirvana_config_storage.h"
#include "nirvana_stream.h"
#include "nirvana_control.h"
#include "nirvana_ble.h"
#include "nirvana_ai.h"

unsigned long lastStatus=0, lastLed=0, lastRender=0;
bool ledState=false, needsRedraw=true;
char agentIP[20]="";
char agentSSID[40]="";

// SD file listing
char sdFiles[12][32];
int  sdFileCount=0;
uint32_t sdTotal=0, sdFree=0;

void setup(){
    Serial.begin(115200); delay(2000);
    Serial.println("\n╔═══════════════════════════════════════╗");
    Serial.println("║  NIRVANA OS v3.1 — AMB82-Mini FULL   ║");
    Serial.println("║  Menu+Btn | CSI | I2S | NN | SD      ║");
    Serial.println("╚═══════════════════════════════════════╝");
    Serial.print("  Device: "); Serial.println(NIRVANA_DEVICE_ID);

    // ── Button (D29, active low) ──
    pinMode(ONBOARD_BUTTON, INPUT_PULLUP);
    Serial.println("[BTN] D29 ready");

    // ── LEDs ──
    pinMode(ONBOARD_LED_BLUE, OUTPUT);
    pinMode(ONBOARD_LED_GREEN, OUTPUT);
    digitalWrite(ONBOARD_LED_BLUE, HIGH);
    digitalWrite(ONBOARD_LED_GREEN, LOW);
    Serial.println("[LED] OK");

    // ── Display ──
    nirvana_display_init();
    nirvana_splash("Booting...", NIRVANA_VERSION);

    // ── WiFi + MQTT ──
    if (nirvana_wifi_connect()) {
        snprintf(agentIP,sizeof(agentIP),"%d.%d.%d.%d",
            WiFi.localIP()[0],WiFi.localIP()[1],WiFi.localIP()[2],WiFi.localIP()[3]);
        strncpy(agentSSID,WiFi.SSID(),sizeof(agentSSID)-1);agentSSID[sizeof(agentSSID)-1]=0;
        if (nirvana_mqtt_connect()) {
            digitalWrite(ONBOARD_LED_GREEN, HIGH);
            Serial.println("[MQTT] Fleet registered");
        }
    }

    // ── BLE keyboard/mouse input (scan for HID devices) ──
    nirvana_ble_init();

    // ── WebSocket audio stream (background, auto-reconnects) ──
    nirvana_stream_connect();

    // ── Camera ──
    nirvana_camera_init();
    // ── Audio ──
    nirvana_audio_init();
    // ── NN — init model but only start pipeline if model loaded OK ──
    nirvana_nn_od_init(camConfigNN);
    // Wait a moment for vipnn errors to appear (if model is corrupt)
    delay(500);
    // Check Serial output — if you see "nbg magic not match", model is corrupt.
    // We still set up the pipeline to avoid compile errors, but CH3 won't
    // consume frames usefully if VIPLite is dead.
    if (nnOD_ready) {
        nirvana_camera_pipe_to(CAM_CH_NN, nnOD);
        nirvana_camera_start(CAM_CH_NN);
    } else {
        Serial.println("[NN-OD] SKIPPED — model failed, VIPLite offline");
        nnModelOk = false;
    }
    // ── SD Card ──
    if (nirvana_sd_init()) {
        sdFileCount = nirvana_sd_list(sdFiles, 12);
        nirvana_sd_space(&sdTotal, &sdFree);
    }

    // ── Config Storage (load from SD, apply brightness) ──
    nirvana_cfg_load();
    nirvana_cfg_apply_brightness();

    // ── AI Providers + Voice Profiles ──
    nirvana_ai_init_defaults();
    if (WiFi.status() == WL_CONNECTED) {
        nirvana_ai_fetch_voice_profiles();
    }

    // ── Show home screen ──
    nirvana_home_screen(0);
    lastRender = millis();
    menuState = MENU_STATE_HOME;
    menuCursor = 0;

    digitalWrite(ONBOARD_LED_BLUE, LOW);
    Serial.println("\n>>> NIRVANA OS READY <<<\n");
    Serial.println("  Commands: home ai settings explorer memos store ota");
    Serial.println("            snapshot record stop back next select");
    Serial.println("  Or type them via MQTT: npu-fleet/amb82/command");
    Serial.println("  Or say 'Nirvana go home' into the mic");
}

void loop(){
    nirvana_mqtt_loop();
    unsigned long now = millis();

    // ── Fleet heartbeat (30s) ──
    if (now - lastStatus > 30000) { lastStatus = now; nirvana_publish_status(); }

    // ── OTA auto-check (every 60 min, WiFi required) ──
    nirvana_ota_auto_check();

    // ── Blue LED pulse (1s) ──
    if (now - lastLed > 1000) {
        lastLed = now; ledState = !ledState;
        digitalWrite(ONBOARD_LED_BLUE, ledState ? HIGH : LOW);
    }

    // ── Serial command input (type commands in Serial Monitor) ──
    nirvana_control_serial();

    // ── Button reading ──
    int btnAction = nirvana_menu_tick();

    // ── Sub-screen ACTIONS: hold on sub-screen = perform screen-specific action ──
    // (Instead of going back — we intercept hold BEFORE menu_handle)
    if (btnAction == 2) {
        if (menuState == MENU_STATE_NIRVANA_AI) {
            Serial.println("[BTN] Snapshot");
            nirvana_vision_send_frame();
            lastMenuActivity = millis(); needsRedraw = true; btnAction = 0;
        }
        else if (menuState == MENU_STATE_VOICE_MEMOS) {
            if (nirvana_recorder_is_active()) {
                nirvana_recorder_stop();
                sdFileCount = nirvana_sd_list(sdFiles, 12);
            } else {
                nirvana_recorder_start();
            }
            lastMenuActivity = millis(); needsRedraw = true; btnAction = 0;
        }
        else if (menuState == MENU_STATE_MARKETPLACE) {
            Serial.print("[STORE] Download slot "); Serial.println(subCursor);
            lastMenuActivity = millis(); needsRedraw = true; btnAction = 0;
        }
        else if (menuState == MENU_STATE_FILE_EXPL && sdFileCount > 0) {
            Serial.print("[SD] Open: "); Serial.println(sdFiles[subCursor]);
            lastMenuActivity = millis(); needsRedraw = true; btnAction = 0;
        }
        else if (menuState == MENU_STATE_OTA) {
            nirvana_ota_start();
            lastMenuActivity = millis(); needsRedraw = true; btnAction = 0;
        }
        else if (menuState == MENU_STATE_SETTINGS) {
            // Hold on settings = adjust current item
            if (subCursor == 0) { nvCfg.brightness = (nvCfg.brightness + 5) % 105; nirvana_cfg_apply_brightness(); }
            else if (subCursor == 1) { nvCfg.volume = (nvCfg.volume + 5) % 105; }
            else if (subCursor == 2) { nvCfg.turbo = !nvCfg.turbo; }
            else if (subCursor == 5) { nirvana_cfg_save(); menuState = MENU_STATE_HOME; subCursor = 0; }
            lastMenuActivity = millis(); needsRedraw = true; btnAction = 0;
        }
    }

    // ── Default menu handling (tap=move, hold=back on sub-screens, tap=move/hold=enter on home) ──
    bool redraw = nirvana_menu_handle(btnAction);
    redraw = redraw || nirvana_menu_timeout();

    // ── Recorder tick (writes PCM chunks while active) ──
    nirvana_recorder_tick();

    // ── Keep menu alive while recording (no timeout) ──
    if (nirvana_recorder_is_active()) lastMenuActivity = now;

    // ── BLE keyboard/mouse scanning tick ──
    nirvana_ble_tick();

    // ── WebSocket audio stream tick ──
    nirvana_stream_tick();
    // Receive TTS audio from server, feed orb + speaker
    int16_t streamBuf[512];
    int streamSamples = nirvana_stream_recv_audio(streamBuf, 512);
    if (streamSamples > 0) {
        float rms = nirvana_stream_rms(streamBuf, streamSamples);
        if (rms > 0.01f) {
            nirvana_orb_feed(rms);
        }
        // TODO: play streamBuf through speaker DAC
    }

    // ── Auto-redraw memos every 1s while recording (elapsed counter) ──
    static unsigned long lastMemosRedraw = 0;
    if (menuState == MENU_STATE_VOICE_MEMOS && nirvana_recorder_is_active()) {
        if (now - lastMemosRedraw > 1000) {
            lastMemosRedraw = now;
            redraw = true;
        }
    }

    // ── Render current menu state ──
    if (redraw || needsRedraw) {
        needsRedraw = false;
        lastRender = now;

        switch (menuState) {
        case MENU_STATE_HOME:
            nirvana_home_screen(menuCursor);
            break;
        case MENU_STATE_NIRVANA_AI:
            nirvana_page_nn(odCount, (const char*)odTopLabel, odTopScore,
                           faceCount, camReady, audioReady);
            break;
        case MENU_STATE_APPS:
            nirvana_page_workspace();
            break;
        case MENU_STATE_MARKETPLACE:
            nirvana_page_marketplace(subCursor);
            break;
        case MENU_STATE_FILE_EXPL:
            nirvana_page_explorer(subCursor, sdFiles, sdFileCount, sdTotal, sdFree);
            break;
        case MENU_STATE_VOICE_MEMOS:
            nirvana_page_memos(subCursor, sdFiles, sdFileCount,
                              nirvana_recorder_is_active(),
                              nirvana_recorder_elapsed());
            break;
        case MENU_STATE_SETTINGS:
            nirvana_page_settings(subCursor, nvCfg.brightness, nvCfg.volume,
                                nvCfg.turbo, agentSSID, MQTT_HOST);
            break;
        case MENU_STATE_OTA:
            nirvana_page_ota(otaStatus);
            break;
        }
    }

    // ── Orb + recorder visual feedback ──
    if (menuState == MENU_STATE_NIRVANA_AI) {
        if (nirvana_recorder_is_active()) {
            // Recording active — orb pulses with steady wave
            nirvana_orb_feed(0.4f + (sinf(now * 0.003f) * 0.15f));
        } else {
            float amp = 0.0f;
            if (odCount > 0 && odTopScore > 0) amp = odTopScore / 100.0f;
            if (faceCount > 0) amp = (amp > 0.3f + faceCount * 0.1f) ? amp : (0.3f + faceCount * 0.1f);
            nirvana_orb_feed(amp);
        }
        nirvana_orb_draw();
    }

    // ── Sub-screen cursor movement ──
    static int lastMenuState = MENU_STATE_HOME;
    if (menuState != lastMenuState) {
        lastMenuState = menuState;
        subCursor = 0;
    }

    delay(10);
}

