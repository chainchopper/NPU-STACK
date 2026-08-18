# NIRVANA OS — MicroPython boot
# Runs before main.py. Keep this minimal: clock + hostname.

import machine
import network

try:
    machine.freq(240_000_000)
except Exception:
    pass

try:
    network.hostname("nirvana-os")
except Exception:
    pass
