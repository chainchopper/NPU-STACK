# Marketplace app: Hello
import time

import display


def run():
    lcd = display.get()
    lcd.fill(0)
    lcd.center_text("HELLO", 80, display.GREEN)
    lcd.center_text("from store", 100, display.WHITE)
    lcd.show()
    time.sleep(2)
