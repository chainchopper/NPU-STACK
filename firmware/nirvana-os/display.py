"""
NIRVANA OS — display module for the Seeed XIAO Round Display (GC9A01 240x240).

Pins (XIAO ESP32-S3, HSPI):
    SCK = GPIO7 (D8)  MOSI = GPIO9 (D10)  MISO = GPIO8 (D9)
    CS  = GPIO1 (D1)  DC   = GPIO3 (D3)   BL   = GPIO43 (D6)
"""
from machine import Pin, SPI

import gc9a01

SPI_BUS = 2      # HSPI (SPI3 peripheral on ESP32-S3)
SCK = 7
MOSI = 9
MISO = 8
CS = 1
DC = 3
BL = 43

_lcd = None
_spi = None

GREEN = 0x07E0
WHITE = 0xFFFF
BLUE = 0x001F
YELLOW = 0xFFE0


def get_spi():
    """Return the shared HSPI bus (display + SD card share SCK/MOSI/MISO)."""
    global _spi
    if _spi is None:
        _spi = SPI(SPI_BUS, baudrate=40_000_000, polarity=0, phase=0,
                   sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))
    return _spi


def init():
    global _lcd
    if _lcd is not None:
        return _lcd
    _lcd = gc9a01.GC9A01(get_spi(), cs=CS, dc=DC, bl=BL)
    _lcd.backlight(True)
    return _lcd


def get():
    return _lcd


def splash(version):
    lcd = init()
    lcd.fill(0)
    lcd.center_text("NIRVANA", 70, GREEN)
    lcd.center_text("OS v" + version, 86, WHITE)
    lcd.center_text("NPU-STACK fleet", 118, BLUE)
    lcd.show()


def status(msg, color=WHITE):
    """Update the bottom status line."""
    lcd = get()
    if lcd is None:
        return
    lcd.fill_rect(0, 220, lcd.width, 20, 0)
    lcd.center_text(msg[:14], 220, color)
    lcd.show()
