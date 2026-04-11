python3 -m esptool --chip esp32s3 write_flash --flash_mode dio --flash_size 4MB --flash_freq 80m 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 micropython.bin 0x1C0000 romfs.bin
