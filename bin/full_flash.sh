esptool --chip esp32s3 write-flash --flash-mode dio --flash-size 4MB --flash-freq 80m 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 micropython.bin 0x1B0000 romfs.bin
