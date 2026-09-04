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
            # Command byte; RAMWR opens a write cursor at the window origin.
            self._pending = data[0]
            if self._pending != 0x2C:
                self._writing = False
            return len(data)
        # dc == 1 -> data burst for the pending command (or a RAMWR stream).
        cmd = self._pending
        self._pending = None
        if cmd == 0x2A:  # column address set
            self.col = ((data[0] << 8) | data[1], (data[2] << 8) | data[3])
            self._writing = False
        elif cmd == 0x2B:  # row address set
            self.row = ((data[0] << 8) | data[1], (data[2] << 8) | data[3])
            self._writing = False
        elif cmd == 0x2C or getattr(self, "_writing", False):
            # RAMWR payload: the panel cursor auto-increments and WRAPS at the
            # window's right edge, dropping to the next row inside the window.
            if cmd == 0x2C:
                self._wx = self.col[0]
                self._wy = self.row[0]
                self.pushes += 1
            off = 0
            while off < len(data):
                run = (self.col[1] - self._wx + 1) * 2
                run = min(run, len(data) - off)
                idx = (self._wy * 240 + self._wx) * 2
                self.frame[idx:idx + run] = data[off:off + run]
                off += run
                if self._wx + run // 2 > self.col[1]:
                    self._wx = self.col[0]
                    self._wy += 1
                else:
                    self._wx += run // 2
            self._writing = True
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

    def _make(self, banded=True):
        import gc9a01 as g
        from machine import Pin
        spi = _RecSPI()
        # Force the banded path so these tests exercise the fallback renderer
        # even on hosts where the full framebuffer would allocate. Direct-mode
        # behaviour is covered separately in test_direct_mode_*.
        g.FORCE_BANDED = banded

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
        g.FORCE_BANDED = False
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

    def test_blit_replays_across_bands(self):
        lcd, spi = self._make()
        lcd.fill(0)
        # 4x4 white sprite straddling the band0/band1 boundary (rows 38..41).
        data = b"\xff\xff" * 16
        lcd.blit(10, 38, 4, 4, data)
        lcd.show()
        for y in range(38, 42):
            for x in range(10, 14):
                self.assertEqual(_px(spi.frame, x, y), 0xFFFF, (x, y))
        self.assertEqual(_px(spi.frame, 9, 38), 0)   # untouched neighbour
        self.assertEqual(_px(spi.frame, 14, 41), 0)

    def test_blit_retain_false_streams_directly(self):
        lcd, spi = self._make()
        data = b"\xff\xff" * 16
        # Non-retained blit streams straight to the panel (no scene, no band
        # buffer), so the rect lands immediately...
        lcd.blit(10, 38, 4, 4, data, retain=False)
        self.assertEqual(spi.pushes, 1)
        self.assertEqual(_px(spi.frame, 10, 38), 0xFFFF)
        self.assertEqual(_px(spi.frame, 13, 41), 0xFFFF)
        # ...and a later show() overwrites it (nothing retained).
        lcd.fill(0)
        lcd.show()
        self.assertEqual(_px(spi.frame, 10, 38), 0)
        self.assertEqual(_px(spi.frame, 13, 41), 0)

    # ── direct (full framebuffer) mode — the PSRAM-live fast path ────────
    def test_direct_mode_full_framebuffer_single_push(self):
        lcd, spi = self._make(banded=False)
        self.assertTrue(lcd._direct)
        self.assertEqual(len(lcd.buffer), 240 * 240 * 2)
        lcd.fill(0xFFFF)
        lcd.show()
        # Direct mode pushes the whole frame in ONE SPI burst (no band replay).
        self.assertEqual(spi.pushes, 1)
        for (x, y) in [(0, 0), (120, 120), (239, 239), (10, 200)]:
            self.assertEqual(_px(spi.frame, x, y), 0xFFFF, (x, y))

    def test_direct_mode_region_push(self):
        lcd, spi = self._make(banded=False)
        lcd.fill(0)
        lcd.fill_rect(0, 80, 240, 41, 0x07E0)  # green band rows 80..120
        spi.pushes = 0
        lcd.show_region(80, 120)
        self.assertEqual(spi.pushes, 1)  # one region burst, not per-band
        for y in range(80, 121):
            for x in (0, 120, 239):
                self.assertEqual(_px(spi.frame, x, y), 0x07E0, (x, y))
        self.assertEqual(_px(spi.frame, 120, 79), 0)
        self.assertEqual(_px(spi.frame, 120, 121), 0)


class SpriteAssetTests(unittest.TestCase):
    """assets.sprite() .spr parsing + cache budget (runs against host /sd)."""

    @classmethod
    def setUpClass(cls):
        shim.install()

    @classmethod
    def tearDownClass(cls):
        shim.uninstall()

    def _write_spr(self, root, name, w, h, payload=None):
        import builtins
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        header = bytes((w >> 8, w & 0xFF, h >> 8, h & 0xFF))
        data = header + (payload if payload is not None else b"\x00\x11" * (w * h))
        with builtins.open(path, "wb") as f:
            f.write(data)

    def test_sprite_roundtrip(self):
        import tempfile
        import assets
        with tempfile.TemporaryDirectory() as td:
            assets.ASSET_DIR = td
            self._write_spr(td, "icons/app.spr", 28, 28)
            spr = assets.sprite("icons/app.spr")
            self.assertIsNotNone(spr)
            w, h, data = spr
            self.assertEqual((w, h), (28, 28))
            self.assertEqual(len(data), 28 * 28 * 2)
            # second read is cached (same object)
            self.assertIs(assets.sprite("icons/app.spr")[2], data)
            assets.clear()

    def test_sprite_rejects_corrupt(self):
        import tempfile
        import assets
        with tempfile.TemporaryDirectory() as td:
            assets.ASSET_DIR = td
            self._write_spr(td, "bad.spr", 28, 28, payload=b"\x00" * 10)
            self.assertIsNone(assets.sprite("bad.spr"))
            self.assertIsNone(assets.sprite("missing.spr"))
            assets.clear()

    def test_cache_budget_evicts_oldest(self):
        import tempfile
        import assets
        with tempfile.TemporaryDirectory() as td:
            assets.ASSET_DIR = td
            big = 30 * 1024  # two of these exceed the 48KB budget
            self._write_spr(td, "a.spr", 1, 1, payload=b"\x00" * big)
            self._write_spr(td, "b.spr", 1, 1, payload=b"\x00" * big)
            assets.load("a.spr")
            assets.load("b.spr")
            self.assertNotIn("a.spr", assets.cached())
            self.assertIn("b.spr", assets.cached())
            self.assertLessEqual(assets.total_bytes(), assets.CACHE_BUDGET)
            assets.clear()


if __name__ == "__main__":
    unittest.main()
