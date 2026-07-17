"""Scan ALL USB devices using pyusb + explicit libusb DLL."""
import ctypes, os, sys

DLL_PATH = r"C:\Windows\System32\libusb-1.0.dll"
if not os.path.exists(DLL_PATH):
    DLL_PATH = r"C:\Users\iAMBLACK\AppData\Local\Temp\libusb_dll\libusb-1.0.dll"

libusb = ctypes.cdll.LoadLibrary(DLL_PATH)
print("libusb loaded OK")

import usb.backend.libusb1, usb.core, usb.util

backend = usb.backend.libusb1.get_backend(find_library=lambda x: DLL_PATH)
if not backend:
    print("No backend")
    sys.exit(1)

devs = list(usb.core.find(find_all=True, backend=backend))
print(f"Total USB devices: {len(devs)}\n")

NAMES = {
    0x2207: "ROCKCHIP/LUCKFOX",
    0x303A: "ESPRESSIF",
    0x239A: "ADAFRUIT",
    0x2886: "SEEED XIAO",
    0x04D8: "MICROCHIP",
    0x1A86: "WCH/CH343 (Grove Vision AI V2)",
    0x2E8A: "RASPBERRY PI RP2040/RP2350",
}

for d in sorted(devs, key=lambda x: (x.idVendor, x.idProduct)):
    vid = d.idVendor
    pid = d.idProduct
    try:
        mfg = usb.util.get_string(d, d.iManufacturer) if d.iManufacturer else ""
    except:
        mfg = ""
    try:
        prod = usb.util.get_string(d, d.iProduct) if d.iProduct else ""
    except:
        prod = ""
    flag = NAMES.get(vid, "")
    if flag:
        flag = " *** " + flag + " ***"
    port = str(d.port_numbers) if d.port_numbers else "?"
    print(f"  {vid:04x}:{pid:04x}  bus={d.bus:03d}  addr={d.address:03d}  {mfg[:30]:30s} {prod[:30]:30s}  port={port}{flag}")
