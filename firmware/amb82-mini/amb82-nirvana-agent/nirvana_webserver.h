// NIRVANA WEB SERVER — Device-hosted HTTP control panel
// Access at http://<device-ip>:80/ from any browser on same network
// Serves JSON status + minimal web UI for device management
#ifndef NIRVANA_WEBSERVER_H
#define NIRVANA_WEBSERVER_H

#include <WiFi.h>
#include "nirvana_config.h"
#include "nirvana_sd.h"

extern bool camReady;    // from nirvana_camera.h
extern bool audioReady;  // from nirvana_audio.h

// ── Simple HTTP server using Ameba WiFiServer ──
WiFiServer webServer(80);
bool webServerRunning = false;

// ── JSON status response ──
void _web_send_status(WiFiClient& c) {
    char ip[20]; snprintf(ip,sizeof(ip),"%d.%d.%d.%d",
        WiFi.localIP()[0],WiFi.localIP()[1],WiFi.localIP()[2],WiFi.localIP()[3]);

    char json[512];
    snprintf(json, sizeof(json),
        "{\"device\":\"%s\",\"version\":\"%s\",\"uptime\":%lu,"
        "\"wifi_ssid\":\"%s\",\"wifi_rssi\":%d,\"ip\":\"%s\","
        "\"sd_ready\":%s,\"cam_ready\":%s,\"audio_ready\":%s,"
        "\"screen\":\"ili9341_bitbang\",\"ram_free\":\"n/a\"}",
        NIRVANA_DEVICE_ID, NIRVANA_VERSION, (unsigned long)(millis()/1000),
        WIFI_SSID, (int)WiFi.RSSI(), ip,
        sdReady?"true":"false", camReady?"true":"false", audioReady?"true":"false");

    c.print("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n");
    c.print("Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n");
    c.print(json);
}

// ── HTML control page (minimal, 2KB) ──
void _web_send_html(WiFiClient& c) {
    char ip[20]; snprintf(ip,sizeof(ip),"%d.%d.%d.%d",
        WiFi.localIP()[0],WiFi.localIP()[1],WiFi.localIP()[2],WiFi.localIP()[3]);

    c.print("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n");
    c.print("<!DOCTYPE html><html><head><meta charset='UTF-8'>");
    c.print("<meta name='viewport' content='width=240,initial-scale=1'>");
    c.print("<title>Nirvana OS</title><style>");
    c.print("body{font:12px monospace;background:#0a0a1a;color:#0f0;margin:8px}");
    c.print(".card{background:#111;border:1px solid #333;padding:8px;margin:6px 0;border-radius:4px}");
    c.print("button{background:#1a1a3a;color:#0ff;border:1px solid #0ff;padding:6px 12px;margin:2px;border-radius:3px;cursor:pointer}");
    c.print("h1{color:#f0f;font-size:16px} h2{color:#0ff;font-size:13px}");
    c.print(".val{color:#ff0} .err{color:#f00}</style></head><body>");
    c.print("<h1>Nirvana OS</h1><div class='card'>");
    c.print("<h2>Device</h2>");
    c.print(     "Type: <span class='val'>AMB82-Mini</span><br>");
    c.print(     "Version: <span class='val'>"); c.print(NIRVANA_VERSION); c.print("</span><br>");
    c.print(     "IP: <span class='val'>"); c.print(ip); c.print("</span><br>");
    c.print(     "WiFi: <span class='val'>"); c.print(WIFI_SSID); c.print("</span> ");
    c.print(     "RSSI: <span class='val'>"); c.print(WiFi.RSSI()); c.print("dBm</span></div>");
    c.print("<div class='card'><h2>Quick Control</h2>");
    c.print("<button onclick='cmd(\"home\")'>Home</button>");
    c.print("<button onclick='cmd(\"ai\")'>AI</button>");
    c.print("<button onclick='cmd(\"settings\")'>Settings</button>");
    c.print("<button onclick='cmd(\"explorer\")'>Files</button>");
    c.print("<button onclick='cmd(\"snapshot\")'>Snapshot</button>");
    c.print("<p id='status'></p></div>");
    c.print("<script>async function cmd(c){");
    c.print("document.getElementById('status').innerText='Sending: '+c;");
    c.print("try{await fetch('/api/cmd?c='+c);");
    c.print("document.getElementById('status').innerText='OK: '+c}");
    c.print("}catch(e){document.getElementById('status').innerText='Error'}}");
    c.print("setInterval(async()=>{try{let r=await fetch('/api/status');");
    c.print("if(r.ok){let j=await r.json();");
    c.print("document.getElementById('status').innerText='Up: '+j.uptime+'s | RSSI: '+j.wifi_rssi+'dBm'}}");
    c.print("catch(e){}},5000)</script></body></html>");
}

// ── Start web server ──
bool nirvana_webserver_start() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WEB] No WiFi — server skipped");
        return false;
    }
    webServer.begin();
    webServerRunning = true;

    char ip[20]; snprintf(ip,sizeof(ip),"%d.%d.%d.%d",
        WiFi.localIP()[0],WiFi.localIP()[1],WiFi.localIP()[2],WiFi.localIP()[3]);
    Serial.print("[WEB] http://"); Serial.print(ip);
    Serial.println("/ — control panel ready");
    return true;
}

// ── Tick: handle incoming HTTP requests ──
void nirvana_webserver_tick() {
    if (!webServerRunning) return;
    WiFiClient c = webServer.available();
    if (!c) return;

    // Read first line (GET /path HTTP/1.1)
    char line[128] = ""; int li = 0;
    unsigned long t = millis();
    while (c.connected() && li < 127 && millis()-t < 2000) {
        if (c.available()) { char ch = c.read(); line[li++] = ch;
            if (ch == '\n') break; }
    }
    line[li] = 0;

    // Route based on path
    if (strstr(line, "GET /api/status")) {
        _web_send_status(c);
    } else if (strstr(line, "GET /api/cmd")) {
        // Extract ?c=XXX parameter
        const char* p = strstr(line, "?c=");
        if (p) {
            p += 3; char cmd[32]=""; int i=0;
            while (*p && *p!=' ' && *p!='&' && i<31) cmd[i++]=*p++;
            cmd[i]=0;
            extern bool nirvana_control_exec(const char*);
            nirvana_control_exec(cmd);
        }
        c.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nOK");
    } else {
        _web_send_html(c);
    }

    // Drain any remaining data
    while (c.available()) c.read();
    c.stop();
}

#endif
