// AMB82-Mini + Waveshare 2.4" ILI9341 — SPI.begin(TFT_CS) FIX
// Ameba SDK has SPI.begin(int ss_pin) — registers only OUR SS pin, not pin 4

#include <SPI.h>

#define TFT_CS  12
#define TFT_DC  7
#define TFT_RST 8
#define TFT_BL  5
#define WIDTH  240
#define HEIGHT 320

inline void _cmd(uint8_t c){digitalWrite(TFT_CS,0);digitalWrite(TFT_DC,0);SPI.transfer(c);digitalWrite(TFT_CS,1);}
inline void _dat(uint8_t d){digitalWrite(TFT_CS,0);digitalWrite(TFT_DC,1);SPI.transfer(d);digitalWrite(TFT_CS,1);}
inline void _dat16(uint16_t d){digitalWrite(TFT_CS,0);digitalWrite(TFT_DC,1);SPI.transfer16(d);digitalWrite(TFT_CS,1);}
void _win(uint16_t x0,uint16_t y0,uint16_t x1,uint16_t y1){_cmd(0x2A);_dat16(x0);_dat16(x1);_cmd(0x2B);_dat16(y0);_dat16(y1);_cmd(0x2C);}
void fill(uint16_t c){_win(0,0,WIDTH-1,HEIGHT-1);digitalWrite(TFT_CS,0);digitalWrite(TFT_DC,1);for(uint32_t i=0;i<(uint32_t)WIDTH*HEIGHT;i++)SPI.transfer16(c);digitalWrite(TFT_CS,1);}

void setup(){
    Serial.begin(115200);delay(2000);
    Serial.println("=== ILI9341 — SPI.begin(TFT_CS) ===");

    // All GPIO first
    pinMode(TFT_CS,OUTPUT);pinMode(TFT_DC,OUTPUT);pinMode(TFT_RST,OUTPUT);pinMode(TFT_BL,OUTPUT);
    digitalWrite(TFT_CS,1);digitalWrite(TFT_BL,1);
    Serial.println("GPIO set OK");

    // SPI.begin(int ss_pin) — only claims OUR SS pin, NOT pin 4
    SPI.begin(TFT_CS);
    Serial.println("SPI.begin(TFT_CS) OK");

    // Reset
    digitalWrite(TFT_RST,0);delay(10);digitalWrite(TFT_RST,1);delay(150);
    Serial.println("Reset done");

    // Init
    _cmd(0x01);delay(150);Serial.println("SW reset");
    _cmd(0x11);delay(150);Serial.println("Sleep out");
    _cmd(0x36);_dat(0x48);Serial.println("MADCTL");
    _cmd(0x3A);_dat(0x55);Serial.println("RGB565");
    _cmd(0x29);delay(50);Serial.println("Display ON");

    fill(0xF800); Serial.println("=== RED ===");
}

void loop(){}
