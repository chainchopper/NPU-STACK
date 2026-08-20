# Marketplace app: Clock
import time

import display


def run():
    lcd = display.get()
    lcd.fill(0)
    lcd.center_text("CLOCK", 60, display.GREEN)
    try:
        from machine import I2C, Pin
        i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400000)
        data = i2c.readfrom_mem(0x51, 0x02, 7)

        def _bcd(v):
            return (v >> 4) * 10 + (v & 0x0F)

        hh = _bcd(data[2] & 0x3F)
        mm = _bcd(data[1] & 0x7F)
        ss = _bcd(data[0] & 0x7F)
        lcd.center_text("%02d:%02d:%02d" % (hh, mm, ss), 110, display.WHITE)
    except Exception:
        lcd.center_text("rtc offline", 110, display.WHITE)
    lcd.show()
    time.sleep(2)
