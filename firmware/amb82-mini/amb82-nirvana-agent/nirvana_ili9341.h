// Nirvana ILI9341 Driver — BIT-BANGED SPI, Waveshare 2.4" LCD
// Zero SPI peripheral conflicts. Pure GPIO. Always works.
#ifndef NIRVANA_ILI9341_H
#define NIRVANA_ILI9341_H
#include "nirvana_config.h"

// Bit-banged SPI pin defines (must be BEFORE _bb_send)
#define MOSI 13
#define SCLK 15

// Bit-banged SPI send (MOSI=13, SCLK=15)
void _bb_send(uint8_t d) {
    for (int8_t i = 7; i >= 0; i--) {
        digitalWrite(SCLK, LOW);
        digitalWrite(MOSI, (d >> i) & 1);
        digitalWrite(SCLK, HIGH);
    }
}
inline void _cmd(uint8_t c) { digitalWrite(TFT_CS,0);digitalWrite(TFT_DC,0);_bb_send(c);digitalWrite(TFT_CS,1); }
inline void _dat(uint8_t d) { digitalWrite(TFT_CS,0);digitalWrite(TFT_DC,1);_bb_send(d);digitalWrite(TFT_CS,1); }
inline void _dat16(uint16_t d) { _dat(d>>8);_dat(d&0xFF); }
void _win(uint16_t x0,uint16_t y0,uint16_t x1,uint16_t y1) { _cmd(0x2A);_dat16(x0);_dat16(x1);_cmd(0x2B);_dat16(y0);_dat16(y1);_cmd(0x2C); }

static const uint8_t F5x7[95][5]={
{0x00,0x00,0x00,0x00,0x00},{0x00,0x00,0x5F,0x00,0x00},{0x00,0x07,0x00,0x07,0x00},{0x14,0x7F,0x14,0x7F,0x14},{0x24,0x2A,0x7F,0x2A,0x12},{0x23,0x13,0x08,0x64,0x62},{0x36,0x49,0x55,0x22,0x50},{0x00,0x05,0x03,0x00,0x00},{0x00,0x1C,0x22,0x41,0x00},{0x00,0x41,0x22,0x1C,0x00},{0x08,0x2A,0x1C,0x2A,0x08},{0x08,0x08,0x3E,0x08,0x08},{0x00,0x50,0x30,0x00,0x00},{0x08,0x08,0x08,0x08,0x08},{0x00,0x60,0x60,0x00,0x00},{0x20,0x10,0x08,0x04,0x02},{0x3E,0x51,0x49,0x45,0x3E},{0x00,0x42,0x7F,0x40,0x00},{0x42,0x61,0x51,0x49,0x46},{0x21,0x41,0x45,0x4B,0x31},{0x18,0x14,0x12,0x7F,0x10},{0x27,0x45,0x45,0x45,0x39},{0x3C,0x4A,0x49,0x49,0x30},{0x01,0x71,0x09,0x05,0x03},{0x36,0x49,0x49,0x49,0x36},{0x06,0x49,0x49,0x29,0x1E},{0x00,0x36,0x36,0x00,0x00},{0x00,0x56,0x36,0x00,0x00},{0x00,0x08,0x14,0x22,0x41},{0x14,0x14,0x14,0x14,0x14},{0x41,0x22,0x14,0x08,0x00},{0x02,0x01,0x51,0x09,0x06},{0x32,0x49,0x79,0x41,0x3E},{0x7E,0x11,0x11,0x11,0x7E},{0x7F,0x49,0x49,0x49,0x36},{0x3E,0x41,0x41,0x41,0x22},{0x7F,0x41,0x41,0x22,0x1C},{0x7F,0x49,0x49,0x49,0x41},{0x7F,0x09,0x09,0x01,0x01},{0x3E,0x41,0x41,0x51,0x32},{0x7F,0x08,0x08,0x08,0x7F},{0x00,0x41,0x7F,0x41,0x00},{0x20,0x40,0x41,0x3F,0x01},{0x7F,0x08,0x14,0x22,0x41},{0x7F,0x40,0x40,0x40,0x40},{0x7F,0x02,0x04,0x02,0x7F},{0x7F,0x04,0x08,0x10,0x7F},{0x3E,0x41,0x41,0x41,0x3E},{0x7F,0x09,0x09,0x09,0x06},{0x3E,0x41,0x51,0x21,0x5E},{0x7F,0x09,0x19,0x29,0x46},{0x46,0x49,0x49,0x49,0x31},{0x01,0x01,0x7F,0x01,0x01},{0x3F,0x40,0x40,0x40,0x3F},{0x1F,0x20,0x40,0x20,0x1F},{0x7F,0x20,0x18,0x20,0x7F},{0x63,0x14,0x08,0x14,0x63},{0x03,0x04,0x78,0x04,0x03},{0x61,0x51,0x49,0x45,0x43},{0x00,0x00,0x7F,0x41,0x41},{0x02,0x04,0x08,0x10,0x20},{0x41,0x41,0x7F,0x00,0x00},{0x04,0x02,0x01,0x02,0x04},{0x40,0x40,0x40,0x40,0x40},{0x00,0x01,0x02,0x04,0x00},{0x20,0x54,0x54,0x54,0x78},{0x7F,0x48,0x44,0x44,0x38},{0x38,0x44,0x44,0x44,0x20},{0x38,0x44,0x44,0x48,0x7F},{0x38,0x54,0x54,0x54,0x18},{0x08,0x7E,0x09,0x01,0x02},{0x08,0x54,0x54,0x54,0x3C},{0x7F,0x08,0x04,0x04,0x78},{0x00,0x44,0x7D,0x40,0x00},{0x20,0x40,0x44,0x3D,0x00},{0x00,0x7F,0x10,0x28,0x44},{0x00,0x41,0x7F,0x40,0x00},{0x7C,0x04,0x18,0x04,0x78},{0x7C,0x08,0x04,0x04,0x78},{0x38,0x44,0x44,0x44,0x38},{0x7C,0x14,0x14,0x14,0x08},{0x08,0x14,0x14,0x18,0x7C},{0x7C,0x08,0x04,0x04,0x08},{0x48,0x54,0x54,0x54,0x20},{0x04,0x3F,0x44,0x40,0x20},{0x3C,0x40,0x40,0x20,0x7C},{0x1C,0x20,0x40,0x20,0x1C},{0x3C,0x40,0x30,0x40,0x3C},{0x44,0x28,0x10,0x28,0x44},{0x0C,0x50,0x50,0x50,0x3C},{0x44,0x64,0x54,0x4C,0x44},{0x00,0x08,0x36,0x41,0x00},{0x00,0x00,0x7F,0x00,0x00},{0x00,0x41,0x36,0x08,0x00}};

void nirvana_display_fill(uint16_t c);
void nirvana_display_fill_rect(int16_t x,int16_t y,uint16_t w,uint16_t h,uint16_t c);
void nirvana_text(int16_t x,int16_t y,const char* t,uint16_t fg,uint8_t sz);
void nirvana_center(const char* t,int16_t y,uint16_t fg,uint8_t sz);
void nirvana_header(const char* t);

void nirvana_page_fleet(bool mq,unsigned long up);
void nirvana_page_nn(int odCount, const char* topLabel, int topScore, int faceCount, bool cam, bool audio);

void nirvana_page_nn(int odCount, const char* topLabel, int topScore, int faceCount, bool cam, bool audio);
void nirvana_home_screen(int cursor);
void nirvana_page_explorer(int cursor, char files[][32], int fileCount, uint32_t sdTotal, uint32_t sdFree);
void nirvana_page_memos(int cursor, char files[][32], int fileCount, bool recording, uint32_t elapsed);
void nirvana_page_settings(int cursor);
void nirvana_page_marketplace(int cursor);
void nirvana_page_workspace();
void nirvana_page_ota(const char* status);

bool nirvana_display_init() {
    // All GPIO — no SPI peripheral
    pinMode(MOSI,OUTPUT);pinMode(SCLK,OUTPUT);pinMode(TFT_CS,OUTPUT);
    pinMode(TFT_DC,OUTPUT);pinMode(TFT_RST,OUTPUT);pinMode(TFT_BL,OUTPUT);
    digitalWrite(TFT_CS,1);digitalWrite(TFT_BL,1);digitalWrite(SCLK,1);
    digitalWrite(TFT_RST,0);delay(10);digitalWrite(TFT_RST,1);delay(150);
    _cmd(0x01);delay(130);_cmd(0x11);delay(130);
    _cmd(0xCF);_dat(0x00);_dat(0xC1);_dat(0x30);_cmd(0xED);_dat(0x64);_dat(0x03);_dat(0x12);_dat(0x81);
    _cmd(0xE8);_dat(0x85);_dat(0x00);_dat(0x78);_cmd(0xCB);_dat(0x39);_dat(0x2C);_dat(0x00);_dat(0x34);_dat(0x02);
    _cmd(0xF7);_dat(0x20);_cmd(0xEA);_dat(0x00);_dat(0x00);_cmd(0xC0);_dat(0x23);_cmd(0xC1);_dat(0x10);
    _cmd(0xC5);_dat(0x3E);_dat(0x28);_cmd(0xC7);_dat(0x86);_cmd(0x36);_dat(0x48);_cmd(0x3A);_dat(0x55);
    _cmd(0xB1);_dat(0x00);_dat(0x18);_cmd(0xB6);_dat(0x08);_dat(0x82);_dat(0x27);
    _cmd(0xF2);_dat(0x00);_cmd(0x26);_dat(0x01);
    _cmd(0xE0);_dat(0x0F);_dat(0x31);_dat(0x2B);_dat(0x0C);_dat(0x0E);_dat(0x08);_dat(0x4E);_dat(0xF1);_dat(0x37);_dat(0x07);_dat(0x10);_dat(0x03);_dat(0x0E);_dat(0x09);_dat(0x00);
    _cmd(0xE1);_dat(0x00);_dat(0x0E);_dat(0x14);_dat(0x03);_dat(0x11);_dat(0x07);_dat(0x31);_dat(0xC1);_dat(0x48);_dat(0x08);_dat(0x0F);_dat(0x0C);_dat(0x31);_dat(0x36);_dat(0x0F);
    _cmd(0x29);delay(20);
    Serial.println("[DISP] ILI9341 OK (bit-banged)");
    nirvana_display_fill(NIRVANA_BLACK);
    return true;
}

void nirvana_display_fill(uint16_t c) {
    uint8_t hi=c>>8,lo=c&0xFF;
    _win(0,0,TFT_WIDTH-1,TFT_HEIGHT-1);digitalWrite(TFT_CS,0);digitalWrite(TFT_DC,1);
    for(uint32_t i=0;i<(uint32_t)TFT_WIDTH*TFT_HEIGHT;i++){_bb_send(hi);_bb_send(lo);}
    digitalWrite(TFT_CS,1);
}
void nirvana_display_fill_rect(int16_t x,int16_t y,uint16_t w,uint16_t h,uint16_t c) {
    if(x<0||y<0||x+w>TFT_WIDTH||y+h>TFT_HEIGHT)return;
    uint8_t hi=c>>8,lo=c&0xFF;
    _win(x,y,x+w-1,y+h-1);digitalWrite(TFT_CS,0);digitalWrite(TFT_DC,1);
    for(uint32_t i=0;i<(uint32_t)w*h;i++){_bb_send(hi);_bb_send(lo);}
    digitalWrite(TFT_CS,1);
}
void nirvana_text(int16_t x,int16_t y,const char* t,uint16_t fg,uint8_t sz) {
    while(*t){char c=*t++;if(c<' '||c>'~')c=' ';const uint8_t*g=F5x7[c-' '];
    for(int8_t co=0;co<5;co++){uint8_t ln=g[co];for(int8_t ro=0;ro<7;ro++)if(ln&(1<<ro)){
        if(sz==1)nirvana_display_fill_rect(x+co,y+ro,1,1,fg);else nirvana_display_fill_rect(x+co*sz,y+ro*sz,sz,sz,fg);
    }}x+=6*sz;}
}
void nirvana_center(const char* t,int16_t y,uint16_t fg,uint8_t sz){int16_t x=(TFT_WIDTH-strlen(t)*6*sz)/2;if(x<0)x=0;nirvana_text(x,y,t,fg,sz);}
void nirvana_header(const char* t){nirvana_display_fill_rect(0,0,TFT_WIDTH,18,NIRVANA_PURPLE);nirvana_text(3,2,t,NIRVANA_WHITE,1);}
void nirvana_splash(const char* ip,const char* ver){
    nirvana_display_fill(NIRVANA_BLACK);nirvana_center("NIRVANA FLEET",50,0x8010,2);
    nirvana_center("AMB82-Mini + ILI9341",80,0x07E0,1);nirvana_center(ver,105,0x07FF,1);
    if(ip[0])nirvana_center(ip,140,0xFFFF,1);
    nirvana_center("Nirvana True Intelligence",200,0x8410,1);nirvana_center("NPU-STACK Fleet",220,0x8410,1);
}
void nirvana_page_status(const char* ip,const char* ssid,int rssi,bool mq,unsigned long up){
    nirvana_display_fill(NIRVANA_BLACK);nirvana_header("NIRVANA FLEET");char b[32];
    nirvana_text(4,22,"Device:",0x8410,1);nirvana_text(62,22,NIRVANA_DEVICE_ID,0x07E0,1);
    nirvana_text(4,36,"Ver:",0x8410,1);nirvana_text(62,36,NIRVANA_VERSION,0x07FF,1);
    nirvana_text(4,50,"IP:",0x8410,1);nirvana_text(62,50,ip,0xFFFF,1);
    snprintf(b,sizeof(b),"%d dBm",rssi);nirvana_text(4,64,"WiFi:",0x8410,1);nirvana_text(62,64,b,rssi>-60?0x07E0:0xF800,1);
    nirvana_text(4,78,"MQTT:",0x8410,1);nirvana_text(62,78,mq?"ONLINE":"OFFLINE",mq?0x07E0:0xF800,1);
    snprintf(b,sizeof(b),"%lu s",up);nirvana_text(4,96,"Up:",0x8410,1);nirvana_text(62,96,b,0xFFFF,1);
    nirvana_text(4,118,"Waveshare 2.4 ILI9341",0x8410,1);nirvana_text(4,132,"RTL8735B M33+NN 500MHz",0x8410,1);
    nirvana_center("NIRVANA FLEET",TFT_HEIGHT-40,0x8010,2);
}
void nirvana_page_network(const char* ip,const char* ssid,int rssi){
    nirvana_display_fill(NIRVANA_BLACK);nirvana_header("NETWORK");char b[32];
    nirvana_text(4,24,"SSID:",0x8410,1);nirvana_text(56,24,ssid,0x07FF,1);
    nirvana_text(4,38,"IP:",0x8410,1);nirvana_text(56,38,ip,0xFFFF,1);
    snprintf(b,sizeof(b),"%d dBm",rssi);nirvana_text(4,52,"RSSI:",0x8410,1);nirvana_text(56,52,b,0x07E0,1);
    nirvana_text(4,80,"5GHz WiFi + BLE 5.1",0x8410,1);nirvana_text(4,100,"OV5647 Camera CSI",0x8410,1);
    nirvana_text(4,114,"I2S Audio (Mic+Spkr)",0x8410,1);nirvana_text(4,128,"NN Engine (RTL8735B)",0x8410,1);
}
void nirvana_page_fleet(bool mq,unsigned long up){
    nirvana_display_fill(NIRVANA_BLACK);nirvana_header("FLEET COMMS");char b[32];
    nirvana_text(4,24,"Protocol: MQTT+UDP",0x07E0,1);nirvana_text(4,42,"Topic: npu-fleet/amb82",0x8410,1);
    nirvana_text(4,56,"Broker:",0x8410,1);nirvana_text(56,56,MQTT_HOST,0x07FF,1);
    nirvana_text(4,74,"Status:",0x8410,1);nirvana_text(56,74,mq?"ONLINE":"OFFLINE",mq?0x07E0:0xF800,1);
    snprintf(b,sizeof(b),"%lu sec",up);nirvana_text(4,92,"Uptime:",0x8410,1);nirvana_text(56,92,b,0xFFFF,1);
    nirvana_text(4,130,"Nirvana Voice Ready",0x07E0,1);nirvana_text(4,144,"xiao zhi MQTT bridge",0x8410,1);
}
void nirvana_page_nn(int odCount, const char* topLabel, int topScore, int fc, bool cam, bool aud){
    nirvana_display_fill(NIRVANA_BLACK);nirvana_header("NIRVANA AI");char b[32];
    // Compact status — orb handles the visual
    nirvana_text(4,22,"Cam:",0x8410,1);nirvana_text(40,22,cam?"OK":"OFF",cam?0x07E0:0xF800,1);
    nirvana_text(80,22,"Aud:",0x8410,1);nirvana_text(114,22,aud?"OK":"OFF",aud?0x07E0:0xF800,1);
    // Detection summary
    if(odCount>0 && topLabel[0]){
        snprintf(b,sizeof(b),"%s (%d%%)",topLabel,topScore);
        nirvana_text(4,38,b,0x07E0,1);
        snprintf(b,sizeof(b),"%d objects | %d faces",odCount,fc);
    } else {
        snprintf(b,sizeof(b),"Scanning... | %d faces",fc);
    }
    nirvana_text(4,52,b,0x07FF,1);
}

// ══════════════════════════════════════════════════
//  NIRVANA OS HOME SCREEN — 2×3 Card Grid
// ══════════════════════════════════════════════════
void nirvana_home_screen(int cursor) {
    nirvana_display_fill(NIRVANA_BLACK);
    nirvana_display_fill_rect(0,0,TFT_WIDTH,20,NIRVANA_PURPLE);
    nirvana_text(3,2,"NIRVANA OS",NIRVANA_WHITE,1);
    nirvana_text(150,2,NIRVANA_VERSION,NIRVANA_CYAN,1);

    const char* labels[] = {"Nirvana AI","Workspace","Marketplace",
                            "Explorer","Recorder","Settings","OTA"};
    uint16_t colors[] = {0x4014,0x1C60,0x1922, 0x2C20,0x4008,0x4210,0x2800};
    int xPos[] = {4,124,4,  124,4,124,64};
    int yPos[] = {28,28,106,  106,184,184,262};

    for (int i=0; i<7; i++) {
        uint16_t bg = (i == cursor) ? NIRVANA_WHITE : colors[i];
        uint16_t fg = (i == cursor) ? NIRVANA_BLACK : NIRVANA_WHITE;
        nirvana_display_fill_rect(xPos[i],yPos[i],114,(i<6?70:40),bg);
        int16_t tx = xPos[i] + (114 - strlen(labels[i])*6)/2;
        nirvana_text(tx, yPos[i]+28, labels[i], fg, 1);
    }
    // Status bar at bottom
    nirvana_display_fill_rect(0,260,TFT_WIDTH,60,NIRVANA_BLACK);
    nirvana_text(4,264,"[BTN] Short:Next  Long:Select",NIRVANA_GRAY,1);
    nirvana_center("NIRVANA FLEET",TFT_HEIGHT-20,NIRVANA_PURPLE,1);
}

// ══════════════════════════════════════════════════
//  FILE EXPLORER — SD Card Browser with sizes
// ══════════════════════════════════════════════════
void nirvana_page_explorer(int cursor, char files[][32], int fileCount,
                           uint32_t sdTotal, uint32_t sdFree) {
    nirvana_display_fill(NIRVANA_BLACK);nirvana_header("FILE EXPLORER");char b[32];
    snprintf(b,sizeof(b),"SD: %lu/%lu MB free",sdFree,sdTotal);
    nirvana_text(4,20,b,NIRVANA_CYAN,1);

    if (fileCount == 0) {
        nirvana_center("No files on SD card",100,NIRVANA_GRAY,1);
        nirvana_center("Insert TF card & reboot",120,NIRVANA_GRAY,1);
    }
    for (int i=0; i<fileCount && i<10; i++) {
        int y = 38 + i*16;
        uint16_t bg = (i == cursor) ? NIRVANA_PURPLE : NIRVANA_BLACK;
        if (i == cursor) nirvana_display_fill_rect(4,y-2,TFT_WIDTH-8,15,bg);
        uint16_t fg = (i == cursor) ? NIRVANA_WHITE : NIRVANA_CYAN;
        nirvana_text(6, y, files[i], fg, 1);
    }
    nirvana_text(4,TFT_HEIGHT-28,"Short:Next File",NIRVANA_GRAY,1);
    nirvana_text(4,TFT_HEIGHT-14,"Long:View/Play  Hold:Back",NIRVANA_GRAY,1);
}

// ══════════════════════════════════════════════════
//  VOICE MEMOS / RECORDER — SD-backed with live state
// ══════════════════════════════════════════════════
void nirvana_page_memos(int cursor, char files[][32], int fileCount,
                        bool recording, uint32_t elapsed) {
    nirvana_display_fill(NIRVANA_BLACK);nirvana_header("MEMOS & RECORDER");
    // Record button — color based on recording state
    uint16_t recBg = recording ? NIRVANA_RED : (cursor==-1 ? NIRVANA_WHITE : 0x4008);
    uint16_t recFg = (recBg == NIRVANA_WHITE) ? NIRVANA_BLACK : NIRVANA_WHITE;
    nirvana_display_fill_rect(60,26,120,40,recBg);
    if (recording) {
        char t[16]; snprintf(t,sizeof(t),"REC %lus",elapsed);
        nirvana_center(t,38,recFg,2);
    } else {
        nirvana_center("RECORD",38,recFg,2);
    }
    nirvana_text(4,74,"Saved on SD:",NIRVANA_GRAY,1);
    if (fileCount == 0) {
        nirvana_text(4,94,"(no recordings yet)",NIRVANA_GRAY,1);
    }
    for (int i=0; i<fileCount && i<6; i++) {
        int y = 94 + i*18;
        uint16_t bg = (i == cursor) ? NIRVANA_PURPLE : NIRVANA_BLACK;
        if (i == cursor) nirvana_display_fill_rect(4,y-2,TFT_WIDTH-8,16,bg);
        nirvana_text(6, y, files[i], i==cursor?NIRVANA_WHITE:NIRVANA_CYAN,1);
    }
    nirvana_text(4,TFT_HEIGHT-28,"Short:Next  Long:Back",NIRVANA_GRAY,1);
    nirvana_text(4,TFT_HEIGHT-14,"REC=Hold 2s to toggle",NIRVANA_GRAY,1);
}

// ══════════════════════════════════════════════════
//  OTA FIRMWARE UPDATE
// ══════════════════════════════════════════════════
void nirvana_page_ota(const char* status) {
    nirvana_display_fill(NIRVANA_BLACK);nirvana_header("OTA UPDATE");
    nirvana_text(4,30,"Firmware Update",NIRVANA_WHITE,2);
    nirvana_text(4,60,"Current:",NIRVANA_GRAY,1);
    nirvana_text(70,60,NIRVANA_VERSION,NIRVANA_CYAN,1);
    nirvana_text(4,78,"Status:",NIRVANA_GRAY,1);
    nirvana_text(70,78,status,NIRVANA_GREEN,1);
    nirvana_text(4,100,"Source:",NIRVANA_GRAY,1);
    nirvana_text(4,114,"http://" MQTT_HOST ":9000",0x07FF,1);
    nirvana_text(4,130,"/firmware/npu-amb82-latest.bin",0x07FF,1);
    nirvana_text(4,160,"Hold button to start OTA",NIRVANA_GRAY,1);
    nirvana_text(4,176,"Device will reboot after flash",NIRVANA_RED,1);
    nirvana_text(4,TFT_HEIGHT-14,"Long:Start OTA  Short:Back",NIRVANA_GRAY,1);
}

// ══════════════════════════════════════════════════
//  SETTINGS — Backlight, WiFi, CPU Profile
// ══════════════════════════════════════════════════
void nirvana_page_settings(int cursor){
    nirvana_display_fill(NIRVANA_BLACK);nirvana_header("SETTINGS");
    const char* items[] = {"Backlight: 75%","WiFi:" WIFI_SSID,
                           "CPU: Turbo 500MHz","Audio: AEC+AGC+NS",
                           "Camera: CSI MIPI","MQTT: " MQTT_HOST};
    for(int i=0;i<6;i++){
        int y=24+i*22;
        if(i==cursor)nirvana_display_fill_rect(4,y-2,TFT_WIDTH-8,20,NIRVANA_PURPLE);
        nirvana_text(6,y,items[i],i==cursor?NIRVANA_WHITE:NIRVANA_CYAN,1);
    }
    nirvana_text(4,TFT_HEIGHT-14,"Short:Next  Long:Back",NIRVANA_GRAY,1);
}

// ══════════════════════════════════════════════════
//  MARKETPLACE — GitHub OTA App Store
// ══════════════════════════════════════════════════
void nirvana_page_marketplace(int cursor){
    nirvana_display_fill(NIRVANA_BLACK);nirvana_header("NIRVANA STORE");
    const char* apps[] = {"NES Emulator v1.1","Doom Shareware",
                          "MQTT Dashboard","Web Radio Stream"};
    for(int i=0;i<4;i++){
        int y=28+i*28;
        if(i==cursor)nirvana_display_fill_rect(4,y-2,TFT_WIDTH-8,26,NIRVANA_PURPLE);
        nirvana_text(6,y,apps[i],i==cursor?NIRVANA_WHITE:0x07E0,1);
        nirvana_text(TFT_WIDTH-30,y,"GET",0x07E0,1);
    }
    nirvana_text(4,160,"Source: github.com/chainchopper",NIRVANA_GRAY,1);
    nirvana_text(4,176,"Format: MicroPython / WASM",NIRVANA_GRAY,1);
    nirvana_text(4,TFT_HEIGHT-14,"Short:Next  Long:Download",NIRVANA_GRAY,1);
}

// ══════════════════════════════════════════════════
//  WORKSPACE — Installed Apps Launcher
// ══════════════════════════════════════════════════
void nirvana_page_workspace(){
    nirvana_display_fill(NIRVANA_BLACK);nirvana_header("WORKSPACE");
    nirvana_center("No apps installed",120,NIRVANA_GRAY,1);
    nirvana_center("Visit Marketplace to download",140,NIRVANA_GRAY,1);
    nirvana_center("MicroPython & WASM sandbox",160,NIRVANA_GRAY,1);
    nirvana_text(4,TFT_HEIGHT-14,"Press button to return",NIRVANA_GRAY,1);
}

#endif
