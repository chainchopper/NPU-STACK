"""
GC9A01 — 240x240 round LCD driver (pure MicroPython).

Pins for the Seeed XIAO Round Display (ESP32-S3, HSPI):
    SCLK = GPIO7 (D8)   MOSI = GPIO9 (D10)   MISO = GPIO8 (D9)
    CS   = GPIO1 (D1)   DC   = GPIO3 (D3)    BL   = GPIO43 (D6)
    RST  = not wired (optional)

Wiring notes:
    - 240x240, RGB565 (16 bpp)
    - MADCTL is set to 0x48; if colours look swapped / mirrored, flip it.

Usage:
    import gc9a01
    from machine import SPI, Pin
    spi = SPI(2, baudrate=40_000_000, sck=Pin(7), mosi=Pin(9), miso=Pin(8))
    lcd = gc9a01.GC9A01(spi, cs=1, dc=3, bl=43)
    lcd.fill(0)               # black
    lcd.text("NIRVANA", 0, 0, 0xFFFF)
    lcd.show()
"""
import time

from machine import Pin
import framebuf


class GC9A01(framebuf.FrameBuffer):
    def __init__(self, spi, cs, dc, rst=None, bl=None,
                 width=240, height=240, madctl=0x48, baudrate=40_000_000):
        self.spi = spi
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.dc = Pin(dc, Pin.OUT, value=0)
        self.rst = Pin(rst, Pin.OUT, value=1) if rst is not None else None
        self.bl = Pin(bl, Pin.OUT, value=1) if bl is not None else None
        self.width = width
        self.height = height
        self.buffer = bytearray(width * height * 2)
        super().__init__(self.buffer, width, height, framebuf.RGB565)
        self._hard_reset()
        self._init(madctl)
        self._window(0, 0, width - 1, height - 1)

    # ── low-level SPI helpers ──────────────────────────────────────────
    def _cmd(self, c, *data):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc(1)
            self.spi.write(bytes(data))
        self.cs(1)

    def _window(self, x0, y0, x1, y1):
        self._cmd(0x2A, x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)  # column
        self._cmd(0x2B, y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)  # row
        self._cmd(0x2C)  # RAMWR

    def _hard_reset(self):
        if self.rst is None:
            return
        self.rst(0)
        time.sleep_ms(20)
        self.rst(1)
        time.sleep_ms(120)

    # ── GC9A01 init sequence (datasheet initial code) ──────────────────
    def _init(self, madctl):
        self._cmd(0xEF)
        self._cmd(0xEB, 0x14)

        self._cmd(0xFE)  # Inter Register Enable1
        self._cmd(0xEF)  # Inter Register Enable2
        self._cmd(0xEB, 0x14,
                  0x84, 0x40, 0x85, 0xFF, 0x86, 0xFF, 0x87, 0xFF,
                  0x88, 0x0A, 0x89, 0x21, 0x8A, 0x00, 0x8B, 0x80,
                  0x8C, 0x01, 0x8D, 0x01, 0x8E, 0xFF, 0x8F, 0xFF)

        self._cmd(0xB6, 0x00, 0x20)      # Display Function Control
        self._cmd(0x36, madctl)          # Memory Access Control
        self._cmd(0x3A, 0x05)            # COLMOD: 16bpp RGB565
        self._cmd(0x90, 0x08, 0x08, 0x08, 0x08)  # Frame rate
        self._cmd(0xBD, 0x06)            # VCOM
        self._cmd(0xBC, 0x00)            # VCOMDC
        self._cmd(0xFF, 0x60, 0x01, 0x04)  # Gamma
        self._cmd(0xC3, 0x13)            # Power Control 2
        self._cmd(0xC4, 0x13)            # Power Control 3
        self._cmd(0xC9, 0x22)            # Power Control 4
        self._cmd(0xBE, 0x11)            # Power Control 5
        self._cmd(0xE1, 0x10, 0x0E)      # Gamma Set
        self._cmd(0xDF, 0x21, 0x0C, 0x02)  # Power Control 6
        self._cmd(0xF0, 0x45, 0x09, 0x08, 0x08, 0x26, 0x2A)  # VCOM Set 1
        self._cmd(0xF1, 0x43, 0x70, 0x72, 0x36, 0x37, 0x6F)  # VCOM Set 2
        self._cmd(0xF2, 0x45, 0x09, 0x08, 0x08, 0x26, 0x2A)  # VCOM Set 3
        self._cmd(0xF3, 0x43, 0x70, 0x72, 0x36, 0x37, 0x6F)  # VCOM Set 4
        self._cmd(0xED, 0x1B, 0x0B)      # Gamma Set
        self._cmd(0xAE, 0x77)            # Gamma Set
        self._cmd(0xCD, 0x63)            # Gamma Set
        self._cmd(0x70, 0x07, 0x07, 0x04, 0x0E, 0x0F, 0x09, 0x07, 0x08, 0x03)
        self._cmd(0xE8, 0x34)            # Display Output Ctrl
        self._cmd(0x62, 0x18, 0x0D, 0x71, 0xED, 0x70, 0x70,
                  0x18, 0x0F, 0x71, 0xEF, 0x70, 0x70)
        self._cmd(0x63, 0x18, 0x11, 0x71, 0xF1, 0x70, 0x70,
                  0x18, 0x13, 0x71, 0xF3, 0x70, 0x70)
        self._cmd(0x64, 0x28, 0x29, 0xF1, 0x01, 0xF1, 0x00, 0x07)
        self._cmd(0x66, 0x3C, 0x00, 0xCD, 0x67, 0x45, 0x45, 0x10, 0x00, 0x00, 0x00)
        self._cmd(0x67, 0x00, 0x3C, 0x00, 0x00, 0x00, 0x01, 0x54, 0x10, 0x32, 0x98)
        self._cmd(0x74, 0x10, 0x85, 0x80, 0x00, 0x00, 0x4E, 0x00)
        self._cmd(0x98, 0x3E, 0x07)
        self._cmd(0x35, 0x00)            # Tearing Effect ON
        self._cmd(0x21)                  # Display Inversion ON
        self._cmd(0x11)                  # Sleep Out
        time.sleep_ms(120)
        self._cmd(0x29)                  # Display ON
        time.sleep_ms(20)

    # ── helpers ─────────────────────────────────────────────────────────
    def show(self):
        """Push the framebuffer to the display."""
        self._window(0, 0, self.width - 1, self.height - 1)
        self.cs(0)
        self.dc(1)
        self.spi.write(self.buffer)
        self.cs(1)

    def backlight(self, on):
        if self.bl is not None:
            self.bl(1 if on else 0)

    def center_text(self, text, y, color=0xFFFF):
        """Centre 8x8 framebuf text horizontally at row y."""
        x = (self.width - len(text) * 8) // 2
        self.text(text, x, y, color)
