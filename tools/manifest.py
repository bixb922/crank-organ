freeze("$(PORT_DIR)/modules")
include("$(MPY_DIR)/extmod/asyncio")
# require("bundle-networking")
# Bundle networking is composed of:
# require("mip")
require("ntptime")
require("ssl")
# require("requests")
# require("webrepl")
# require("urequests")

require("neopixel")
require("aiohttp")
require("tarfile")
require("tarfile-write")

module("boot.py")
module("main.py")


