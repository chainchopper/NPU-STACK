# Marketplace app: Demo
import time

import display


def run():
    lcd = display.get()
    lcd.fill(0)
    lcd.center_text("DEMO APP", 80, display.GREEN)
    lcd.center_text("manifest format", 100, display.WHITE)
    lcd.show()
    time.sleep(2)
