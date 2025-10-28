freeze("$(PORT_DIR)/modules")
include("$(MPY_DIR)/extmod/asyncio")
require("bundle-networking")
require("neopixel")
require("shutil")
require("aiohttp")

module("boot.py")

