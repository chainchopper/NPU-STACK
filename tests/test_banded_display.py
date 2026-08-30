"""Host-side validation of the banded GC9A01 renderer.

The emulator's own PIL FrameBuffer does not exercise the banded path, so this
test drives gc9a01.GC9A01 directly with a recording SPI stub, reconstructs the
full 240x240 frame from the band pushes, and asserts that drawing + full
show() + dirty-region commit() all land pixels correctly. It also asserts the
driver never allocates a full-size framebuffer (the no-PSRAM constraint).
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "firmware", "nirvana-os"))

from backend.emulator import shim  # noqa: E402  (installs machine/Pin stubs)


class _RecSPI:
    """Reassembles GC9A01 SPI traffic into a full 240x240 frame."""

    def __init__(self):
        self.dc = 0
        self._pending = None      # 1-byte command awaiting its data burst
        self.col = (0, 239)
        self.row = (0, 239)
        self.frame = bytearray(240 * 240 * 2)
        self.pushes = 0

    def _pin(self, num, value):
        if num == 4:              # DC pin (xiao-sense pinmap)
            self.dc = value

    def write(self, data):
        data = bytes(data)
        if self.dc == 0:
            # Command byte.
            cmd = data[0]
            self._pending = cmd
            return len(data)
        # dc == 1 -> data burst for the pending command.
        cmd = self._pending
        self._pending = None
        if cmd == 0x2A:  # column address set
            self.col = ((data[0] << 8) | data[1], (data[2] << 8) | data[3])
        elif cmd == 0x2B:  # row address set
            self.row = ((data[0] << 8) | data[1], (data[2] << 8) | data[3])
        elif cmd == 0x2C:  # RAMWR pixel payload
            x0 = self.col[0]
            y0 = self.row[0]
            idx = (y0 * 240 + x0) * 2
            self.frame[idx:idx + len(data)] = data
            self.pushes += 1
        return len(data)


def _px(frame, x, y):
    i = (y * 240 + x) * 2
    return (frame[i] << 8) | frame[i + 1]


class BandedDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shim.install()

    @classmethod
    def tearDownClass(cls):
        shim.uninstall()

    def _make(self):
        import gc9a01 as g
        from machine import Pin
        spi = _RecSPI()

        # Patch gc9a01.Pin with a subclass whose DC line reports back to the SPI.
        class SpyPin(Pin):
            def value(self, v=None):
                r = super().value(v)
                if v is not None and self.num == 4:  # dc pin
                    spi.dc = 1 if v else 0
                return r
        g.Pin = SpyPin
        lcd = g.GC9A01(spi, cs=2, dc=4, bl=43)
        g.Pin = Pin
        return lcd, spi

    def test_no_full_framebuffer_allocated(self):
        lcd, _ = self._make()
        # Band buffer only — never the full 115,200 bytes.
        self.assertLessEqual(len(lcd.buffer), 240 * 40 * 2)
        self.assertEqual(lcd.band_h, 40)

    def test_fill_then_show_covers_full_frame(self):
        lcd, spi = self._make()
        lcd.fill(0xFFFF)
        lcd.show()
        # 6 bands of 40 rows each -> 6 pixel pushes.
        self.assertEqual(spi.pushes, 6)
        for (x, y) in [(0, 0), (120, 120), (239, 239), (10, 200)]:
            self.assertEqual(_px(spi.frame, x, y), 0xFFFF, (x, y))

    def test_pixel_across_band_boundary(self):
        lcd, spi = self._make()
        lcd.fill(0)
        # Row 39 = last row of band 0, row 40 = first row of band 1.
        lcd.pixel(5, 39, 0x07E0)
        lcd.pixel(5, 40, 0xF800)
        lcd.show()
        self.assertEqual(_px(spi.frame, 5, 39), 0x07E0)
        self.assertEqual(_px(spi.frame, 5, 40), 0xF800)
        # Untouched pixel stays background.
        self.assertEqual(_px(spi.frame, 6, 39), 0)

    def test_commit_only_pushes_overlapping_bands(self):
        lcd, spi = self._make()
        lcd.fill(0)
        lcd.fill_circle(120, 98, 20, 0xFFFF)  # eye, rows ~78..118 -> bands 40..119
        before = spi.pushes
        lcd.commit(78, 118)
        # rows 78..118 span band 40 (40-79) and band 80 (80-119) -> 2 pushes.
        self.assertEqual(spi.pushes - before, 2)
        self.assertEqual(_px(spi.frame, 120, 98), 0xFFFF)

    def test_text_renders_in_correct_band(self):
        lcd, spi = self._make()
        lcd.fill(0)
        lcd.center_text("HI", 100, 0xFFFF)  # rows 100..107 -> band 80..119
        lcd.show()
        # At least one glyph pixel lit in that row range.
        lit = any(
            _px(spi.frame, x, y) == 0xFFFF
            for y in range(100, 108) for x in range(0, 240)
        )
        self.assertTrue(lit)


if __name__ == "__main__":
    unittest.main()
