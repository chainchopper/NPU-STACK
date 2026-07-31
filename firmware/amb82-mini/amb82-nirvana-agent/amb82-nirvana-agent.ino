// AMB82-Mini + Waveshare 2.4" ILI9341 — FIXED SPI INIT
// SPI.begin() must be called FIRST, before pinMode on any SPI-related pin.
// CS (AMB_D12) is claimed by the SPI library — don't call pinMode on it.

#include <SPI.h>

#define TFT_CS  12   // SPI SS: handled by SPI library, not pinMode!
#define TFT_DC  7    // AMB_D7  = PF_14
#define TFT_RST 8    // AMB_D8  = PF_15
#define TFT_BL  5    // AMB_D5  = PF_12 (safe)
#define WIDTH  240
#define HEIGHT 320

inline void cmd(uint8_t c)   { digitalWrite(TFT_CS,LOW); digitalWrite(TFT_DC,LOW);  SPI.transfer(c); digitalWrite(TFT_CS,HIGH); }
inline void data(uint8_t d)  { digitalWrite(TFT_CS,LOW); digitalWrite(TFT_DC,HIGH); SPI.transfer(d); digitalWrite(TFT_CS,HIGH); }
inline void data16(uint16_t d) { data(d>>8); data(d&0xFF); }
void setWin(uint16_t x0,uint16_t y0,uint16_t x1,uint16_t y1){ cmd(0x2A);data16(x0);data16(x1);cmd(0x2B);data16(y0);data16(y1);cmd(0x2C); }

void fill(uint16_t c) {
    setWin(0,0,WIDTH-1,HEIGHT-1);
    digitalWrite(TFT_CS,LOW); digitalWrite(TFT_DC,HIGH);
    for(uint32_t i=0;i<(uint32_t)WIDTH*HEIGHT;i++){ SPI.transfer(c>>8); SPI.transfer(c&0xFF); }
    digitalWrite(TFT_CS,HIGH);
}

void setup() {
    Serial.begin(115200); delay(2000);
    Serial.println("=== ILI9341 FIXED ===");

    // -- STEP 1: SPI.init() FIRST (before any pinMode on pins it needs) --
    SPI.begin();
    Serial.println("SPI.begin() OK");
    delay(10);

    // -- STEP 2: Manually set only non-SPI pins --
    pinMode(TFT_DC, OUTPUT);
    pinMode(TFT_RST, OUTPUT);
    pinMode(TFT_BL, OUTPUT);
    digitalWrite(TFT_BL, HIGH);   // Backlight ON
    // NOTE: TFT_CS is managed by SPI library — do NOT call pinMode on it
    pinMode(TFT_CS, OUTPUT);      // OK to call AFTER SPI.begin()
    digitalWrite(TFT_CS, HIGH);
    Serial.println("GPIO set OK");

    // -- STEP 3: Hard reset (match AmebaIL9341 example: pull LOW first) --
    digitalWrite(TFT_RST, LOW);   delay(10);
    digitalWrite(TFT_RST, HIGH);  delay(150);
    Serial.println("Reset done");

    // -- STEP 4: ILI9341 init --
    cmd(0x01); delay(150);  Serial.println("SW reset");
    cmd(0x11); delay(150);  Serial.println("Sleep out");
    cmd(0x36); data(0x48);  Serial.println("MADCTL");
    cmd(0x3A); data(0x55);  Serial.println("RGB565");
    cmd(0x29); delay(50);   Serial.println("Display ON");

    // -- STEP 5: Fill RED (proof SPI works) --
    Serial.println("Fill RED...");
    fill(0xF800);
    Serial.println("=== DONE — screen should be RED ===");
}

void loop() { fill(0xF800); delay(5000); fill(0x07E0); delay(5000); fill(0x001F); delay(5000); }
