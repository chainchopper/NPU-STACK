"""
NIRVANA OS — touch-driven menu for the round display.

Touch reports X/Y in 0..255 (panel 240x240). Navigation:
    tap top third    (y <  80) -> previous item
    tap bottom third (y > 160) -> next item
    tap middle                 -> select / activate
"""
import time


class Menu:
    def __init__(self, touch, display_mod, items):
        self.touch = touch
        self.d = display_mod
        self.lcd = display_mod.get()
        self.items = items          # [(label, callback_or_None), ...]
        self.index = 0

    def draw(self):
        lcd = self.lcd
        lcd.fill(0)
        lcd.center_text("NIRVANA", 18, self.d.GREEN)
        n = len(self.items) or 1
        for offset in (-2, -1, 0, 1, 2):
            i = (self.index + offset) % n
            label = self.items[i][0]
            color = self.d.WHITE if offset == 0 else 0x4208
            lcd.center_text(label[:14], 55 + (offset + 2) * 18, color)
        lcd.center_text("^ select v", 205, 0x4208)
        lcd.show()

    def run(self):
        self.draw()
        while True:
            p = self.touch.read()
            if p is None:
                time.sleep_ms(40)
                continue
            _x, y = p
            if y < 80:
                self.index = (self.index - 1) % len(self.items)
                self.draw()
            elif y > 160:
                self.index = (self.index + 1) % len(self.items)
                self.draw()
            else:
                label, cb = self.items[self.index]
                self.lcd.fill(0)
                self.lcd.center_text("> " + label[:12], 110, self.d.YELLOW)
                self.lcd.show()
                time.sleep_ms(300)
                if cb is not None:
                    try:
                        cb()
                    except Exception as e:
                        print("[NIRVANA] action error:", e)
                self.draw()
            time.sleep_ms(250)  # debounce
