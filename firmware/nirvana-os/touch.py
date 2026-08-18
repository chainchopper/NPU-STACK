"""
NIRVANA OS — CHSC6X capacitive touch driver (Seeed XIAO Round Display).

Controller: CHSC6540 (CHSC6X family) @ I2C 0x2E.
I2C bus:    SDA = GPIO4 (D4), SCL = GPIO5 (D5), 400 kHz.
INT pin:    GPIO44 (D7), active LOW when touched.

Read format (5 bytes):
    [0] = touch count (0x01 = touched)
    [1] = reserved
    [2] = X (0..255)
    [3] = reserved
    [4] = Y (0..255)
"""
import time

import machine

CHSC6X_ADDR = 0x2E


class Touch:
    def __init__(self, i2c, int_pin=44):
        self.i2c = i2c
        self.int_pin = machine.Pin(int_pin, machine.Pin.IN, machine.Pin.PULL_UP)

    def read(self):
        """Return (x, y) if currently touched, else None."""
        if self.int_pin.value() != 0:      # INT high = no touch (active low)
            return None
        try:
            data = self.i2c.readfrom(CHSC6X_ADDR, 5)
        except OSError:
            return None
        if len(data) != 5 or data[0] != 0x01:
            return None
        return data[2], data[4]

    def read_until(self, timeout_ms=5000):
        """Block until a touch; return (x, y) or None on timeout."""
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
            p = self.read()
            if p is not None:
                return p
            time.sleep_ms(20)
        return None
