// AMB82-Mini + Waveshare 2.4" ILI9341 — MINIMAL TEST
// Pin 4 (AMB_D4 = PF_11) is shared with SPI1/I2S — never use for GPIO!
// Backlight moved to Pin 5 (AMB_D5 = PF_12, PWM, no peripheral conflict)

#include <SPI.h>

// LCD pins — use AMB_Dn numbers (not PAxx)
#define TFT_CS  12   // AMB_D12 = PE_4 (safe)
#define TFT_DC  7    // AMB_D7  = PF_14 (safe)
#define TFT_RST 8    // AMB_D8  = PF_15 (safe)
#define TFT_BL  5    // AMB_D5  = PF_12 (safe — NOT pin 4!)

#define WIDTH  240
#define HEIGHT 320

void cmd(uint8_t c) {
    digitalWrite(TFT_CS, LOW);
    digitalWrite(TFT_DC, LOW);
    SPI.transfer(c);
    digitalWrite(TFT_CS, HIGH);
}

void data(uint8_t d) {
    digitalWrite(TFT_CS, LOW);
    digitalWrite(TFT_DC, HIGH);
    SPI.transfer(d);
    digitalWrite(TFT_CS, HIGH);
}

void data16(uint16_t d) {
    data(d >> 8);
    data(d & 0xFF);
}

void setWindow(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
    cmd(0x2A); data16(x0); data16(x1);
    cmd(0x2B); data16(y0); data16(y1);
    cmd(0x2C);
}

void fillScreen(uint16_t color) {
    setWindow(0, 0, WIDTH-1, HEIGHT-1);
    digitalWrite(TFT_CS, LOW);
    digitalWrite(TFT_DC, HIGH);
    for (uint32_t i = 0; i < (uint32_t)WIDTH * HEIGHT; i++) {
        SPI.transfer(color >> 8);
        SPI.transfer(color & 0xFF);
    }
    digitalWrite(TFT_CS, HIGH);
}

void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println("=== ILI9341 TEST (BL on pin 5, not 4) ===");

    // GPIO — BL on pin 5, NOT pin 4!
    pinMode(TFT_CS, OUTPUT);
    pinMode(TFT_DC, OUTPUT);
    pinMode(TFT_RST, OUTPUT);
    pinMode(TFT_BL, OUTPUT);
    digitalWrite(TFT_CS, HIGH);
    digitalWrite(TFT_BL, HIGH);

    SPI.begin();

    digitalWrite(TFT_RST, HIGH); delay(10);
    digitalWrite(TFT_RST, LOW);  delay(10);
    digitalWrite(TFT_RST, HIGH); delay(150);
    Serial.println("Reset done");

    cmd(0x01); delay(150);  Serial.println("SW reset");
    cmd(0x11); delay(150);  Serial.println("Sleep out");
    cmd(0x36); data(0x48);  Serial.println("MADCTL");
    cmd(0x3A); data(0x55);  Serial.println("RGB565");
    cmd(0x29); delay(50);   Serial.println("Display ON");

    Serial.println("Filling RED...");
    fillScreen(0xF800);
    Serial.println("DONE");
}

void loop() {
    fillScreen(0xF800); delay(5000);
    fillScreen(0x07E0); delay(5000);
    fillScreen(0x001F); delay(5000);
}
