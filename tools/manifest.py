freeze("$(PORT_DIR)/modules")
include("$(MPY_DIR)/extmod/asyncio")
require("bundle-networking")
require("neopixel")
require("aiohttp")

module("boot.py")
module("main.py")


