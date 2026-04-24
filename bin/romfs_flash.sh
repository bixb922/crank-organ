echo Flash romfs only. Use full_flash.sh to flash both MicroPython and romfs with the complete crank organ software
esptool --chip esp32s3 write-flash --flash-mode dio --flash-size 4MB --flash-freq 80m 0x1C0000 romfs.bin
