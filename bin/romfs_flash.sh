echo Flash romfs only. Use flash_mp.sh to flash MicroPython + romfs
python3 -m esptool --chip esp32s3 write_flash --flash_mode dio --flash_size 4MB --flash_freq 80m 0x1C0000 romfs.bin