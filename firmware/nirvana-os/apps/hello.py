# Example Nirvana OS app — copy this file to the SD card as:
#   /sd/apps/hello.py
# The home menu auto-discovers it and adds "Hello" to the list.
NAME = "Hello"


def run():
    import time

    import display

    lcd = display.get()
    lcd.fill(0)
    lcd.center_text("HELLO", 80, display.GREEN)
    lcd.center_text("from SD app", 100, display.WHITE)
    lcd.show()
    time.sleep(2)
