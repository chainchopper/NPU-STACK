// AMB82-Mini + Waveshare 2.4" ILI9341 — BIT-BANGED SPI
// Zero SPI library. Zero peripheral conflicts. Just GPIO.
// MOSI=13, SCLK=15, CS=12, DC=7, RST=8, BL=5

#define MOSI 13
#define SCLK 15
#define CS   12
#define DC   7
#define RST  8
#define BL   5
#define WIDTH  240
#define HEIGHT 320

// Bit-banged SPI send
void _send(uint8_t d) {
    for (int8_t i = 7; i >= 0; i--) {
        digitalWrite(SCLK, LOW);
        digitalWrite(MOSI, (d >> i) & 1);
        digitalWrite(SCLK, HIGH);
    }
}

inline void _cmd(uint8_t c) { digitalWrite(CS, LOW); digitalWrite(DC, LOW); _send(c); digitalWrite(CS, HIGH); }
inline void _dat(uint8_t d) { digitalWrite(CS, LOW); digitalWrite(DC, HIGH); _send(d); digitalWrite(CS, HIGH); }
void _dat16(uint16_t d) { _dat(d >> 8); _dat(d & 0xFF); }
void _win(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) { _cmd(0x2A); _dat16(x0); _dat16(x1); _cmd(0x2B); _dat16(y0); _dat16(y1); _cmd(0x2C); }

void fill(uint16_t c) {
    _win(0, 0, WIDTH-1, HEIGHT-1);
    uint8_t hi = c >> 8, lo = c & 0xFF;
    digitalWrite(CS, LOW); digitalWrite(DC, HIGH);
    for (uint32_t i = 0; i < (uint32_t)WIDTH * HEIGHT; i++) { _send(hi); _send(lo); }
    digitalWrite(CS, HIGH);
}

void setup() {
    Serial.begin(115200); delay(2000);
    Serial.println("=== ILI9341 — BIT-BANGED SPI ===");

    // All pins as simple GPIO outputs — no SPI peripheral at all
    pinMode(MOSI, OUTPUT); pinMode(SCLK, OUTPUT);
    pinMode(CS, OUTPUT);   pinMode(DC, OUTPUT);
    pinMode(RST, OUTPUT);  pinMode(BL, OUTPUT);
    digitalWrite(CS, HIGH); digitalWrite(BL, HIGH);
    digitalWrite(SCLK, HIGH);
    Serial.println("GPIO set OK");

    // Reset
    digitalWrite(RST, LOW);  delay(10);
    digitalWrite(RST, HIGH); delay(150);
    Serial.println("Reset done");

    // ILI9341 init
    _cmd(0x01); delay(150); Serial.println("SW reset");
    _cmd(0x11); delay(150); Serial.println("Sleep out");
    _cmd(0x36); _dat(0x48); Serial.println("MADCTL");
    _cmd(0x3A); _dat(0x55); Serial.println("RGB565");
    _cmd(0x29); delay(50);  Serial.println("Display ON");

    fill(0xF800); Serial.println("=== RED ===");
    delay(3000);
    fill(0x07E0); Serial.println("=== GREEN ===");
    delay(3000);
    fill(0x001F); Serial.println("=== BLUE ===");
}

void loop() {}
