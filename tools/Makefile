# This makefile is used during software development.
# Use gmake -fcrank-organ/tools/Makefile
# Run from folder just above crank-organ

# Target compile: compiles .py and compresses html/js/css
# Target update: compiles/compresses and updates microcontroller

# Target cleanpc: removes device folder with compiled files
# on PC,
# forces all files to compile/regenerate again
#
# Targets for specific ESP32-S3 boards. Identification of boards
# based on MAC. MAC for s8n8 is b'|\xdf\xa1\xe8\xc2@' is s8n8 
# MAC for drehorgel (s3n16)  is b'\xf4\x12\xfa\xe7)\x80' == b'\xf4\x12\xfa\xe7\x29\x80'
# Target cleandevice: backups /data folder.
# erases all data except /tunelib and /lib from device. Erases device, so gmake esp32 will recompile all.

# Target backupdata: backups data folder of device to config-<hostname>. Hostname based on MAC, see definition of DEVICENAME.
#
# Target installdevice: install device. After that: connect with
# default configuration, set config and do gmake restoredata. Needs gmake freeze to get install files first. Needs backupdata first.
#
# Target deepcleandevice: formats device. No backup.
#

# MPY_CROSS = mpy-cross-multi --micropython 1.24
MPY_CROSS = mpy-cross
MPREMOTE := mpremote

# Get device name via WiFi MAC.
x:=$(shell $(MPREMOTE) exec "import network;print(network.WLAN(network.STA_IF).config('hostname'))">temp.txt)
DEVICENAME := $(strip $(file < temp.txt))
#x=$(shell rm temp.txt)
CONFIGFOLDER := config-$(DEVICENAME)
# Get time stamp, for example for backup files
NOW := $(shell date "+%Y%m%d-%H%M%S")
# Set date on microcontroller
x:=$(shell $(MPREMOTE) rtc --set)

MPY_FILES := \
compiledate.mpy \
fileops.mpy \
battery.mpy \
config.mpy \
counter.mpy \
drehorgel.mpy \
driver_base.mpy \
driver_gpio.mpy \
driver_gpioservo.mpy \
driver_mcp23017.mpy \
driver_midiserial.mpy \
driver_null.mpy \
driver_ftoms.mpy \
driver_pca9685.mpy \
filemanager.mpy \
history.mpy \
led.mpy \
matrix.mpy \
midi.mpy \
midicontroller.mpy \
minilog.mpy \
microdot.mpy \
organtuner.mpy \
microphone.mpy \
pinout.mpy \
player.mpy \
poweroff.mpy \
scheduler.mpy \
setlist.mpy \
solenoid.mpy \
startup.mpy \
tachometer.mpy \
timezone.mpy \
touchpad.mpy \
tunemanager.mpy \
umidiparser.mpy \
webserver.mpy \
wifimanager.mpy \
frequency.mpy \
fft_arrays.mpy \
pcnt.mpy \
mcserver.mpy 


STATIC_FILES := \
common.js.gz \
config.html.gz \
diag.html.gz \
drums.html.gz \
filemanager.html.gz \
index.html.gz \
history.html.gz \
note.html.gz \
notelist.html.gz \
pinout.html.gz \
play.html.gz \
tunelibedit.html.gz \
tunelist.html.gz \
show_midi.html.gz \
skeleton.css.gz \
translations.js.gz 


# Target "update": compile py to mpy, compress html/js to gz
# and copy to device and device/update folder. 
# device/update is used to test if file was copied to device.
# Does NOT update: *.jpg, *.ico, *.png, /data/*
update: compile device/update/main.py $(addprefix device/update/, $(MPY_FILES)) $(addprefix device/update/,  $(STATIC_FILES))

device/update/main.py: crank-organ/src/main.py
	$(MPREMOTE) cp $< :main.py
	cp $< device/update/$(notdir $<)

device/update/%.mpy: device/mpy/%.mpy
	$(MPREMOTE) cp $< :software/mpy/$(notdir $<)
	cp $< device/update/$(notdir $<)

device/update/%.gz : device/static/%.gz
	$(MPREMOTE) cp $< :software/static/$(notdir $<)
	cp $< device/update/$(notdir $<)


# Target "compile": compile py to mpy, compress html/js to gz
# Compilation results to device/mpy
# Compression results to device/static
compile : $(addprefix device/mpy/, $(MPY_FILES)) $(addprefix device/static/,  $(STATIC_FILES))

compiledate:
	echo $(NOW) $(DEVICENAME) $(CONFIGFOLDER) 
	python3 crank-organ/tools/write_compiledate.py
	$(MPY_CROSS) -march=xtensawin crank-organ/src/compiledate.py -o device/mpy/compiledate.mpy

device/mpy/mcserver.mpy: server/mcserver.py
	$(MPY_CROSS) -march=xtensawin $< -o $@
	
device/mpy/%.mpy: crank-organ/src/%.py
	$(MPY_CROSS) -march=xtensawin $< -o $@

device/static/%.js.gz: crank-organ/static/%.js
	gzip -9 -c -k $< > $@

device/static/%.html.gz: crank-organ/static/%.html
	gzip -9 -c -k $< > $@

device/static/%.css.gz: crank-organ/static/%.css
	gzip -9 -c -k $< > $@


prepare_git: compiledate
	python3 crank-organ/tools/update-toc.py
	-rm device/mpy/mcserver.mpy
	-rm device/mpy/mcserver.py
	python3 -m freezefs crank-organ/data crank-organ/install/install_data.py --target=/data --on-import=extract --overwrite=always --compress
	-rm -r freezetemp/
	-mkdir freezetemp/
	-mkdir freezetemp/software/
	-mkdir freezetemp/software/mpy/
	-mkdir freezetemp/software/static/
	cp crank-organ/src/* freezetemp/software/mpy/
	cp crank-organ/static/* freezetemp/software/static/
	cp crank-organ/src/main.py freezetemp/
	rm freezetemp/software/mpy/main.py
	python3 -m freezefs freezetemp crank-organ/install/install_software.py --target=/ --on-import=extract --overwrite=always --compress
	-rm -r freezetemp


 
deepcleandevice: backupdata
	$(MPREMOTE)e exec "import os;os.umount('/');os.VfsLfs2.mkfs(bdev);os.mount(bdev,'/'))

cleandevice: backupdata
	-$(MPREMOTE) exec "import shutil;shutil.rmtree('software')"
	-$(MPREMOTE) exec "import shutil;shutil.rmtree('signals')"
	-$(MPREMOTE) rm /main.py
	-$(MPREMOTE) mkdir software
	-$(MPREMOTE) mkdir software/mpy
	-$(MPREMOTE) mkdir software/static
	-$(MPREMOTE) mkdir lib
	echo "/tunelib /lib and /data were kept"
	

	
cleanpc:
	-rm -r -f device
	-mkdir device
	-mkdir device/mpy
	-mkdir device/static
	-mkdir device/update

initdevice:
	-$(MPREMOTE) mkdir software
	-$(MPREMOTE) mkdir software/static
	-$(MPREMOTE) mkdir software/mpy
	$(MPREMOTE) mip install shutil

initpc:
	mkdir device
	mkdir device/mpy
	mkdir device/static

installdevice: 
	$(MPREMOTE) mip install shutil
	$(MPREMOTE) run crank-organ/install/install_software.py  
	$(MPREMOTE) run crank-organ/install/install_data.py 


backupdata:
	-mkdir $(CONFIGFOLDER)
	-mkdir $(CONFIGFOLDER)/$(NOW)
	-$(MPREMOTE) cp :data/config.json $(CONFIGFOLDER)/$(NOW)/
	-$(MPREMOTE) cp :data/organtuner.json $(CONFIGFOLDER)/$(NOW)/
	-$(MPREMOTE) cp :data/35_note_custom.json $(CONFIGFOLDER)/$(NOW)/
	-$(MPREMOTE) cp :data/48_note_custom.json $(CONFIGFOLDER)/$(NOW)/
	-$(MPREMOTE) cp :data/pinout.txt $(CONFIGFOLDER)/$(NOW)/
	-$(MPREMOTE) cp :data/history.json $(CONFIGFOLDER)/$(NOW)/
	-$(MPREMOTE) cp :data/battery_calibration.json $(CONFIGFOLDER)/$(NOW)/
	-$(MPREMOTE) cp :data/tunelib.json $(CONFIGFOLDER)/$(NOW)/
	-$(MPREMOTE) cp :data/lyrics.json $(CONFIGFOLDER)/$(NOW)/

romfs: compile
	-mkdir micropython_bin
	# To generate micropython 1.26.preview image:
	# git rebase -i f77fd62... and edit file 
	# to remove commit d737112 "esp32/esp32_common.cmake: Use the tinyusb source files from ESP-IDF"
	# Replace _boot.py
	# add partitions-4MiB-BIG-romfs.csv file
	# add these lines to boards/ESP32_GENERIC_S3/sdkconfig.board
	# 		CONFIG_PARTITION_TABLE_CUSTOM=y
	#		CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-4MiB-BIG-romfs.csv"
	#  #define MICROPY_VFS_ROM (1)  in mpconfigboard.h
	# (I also defined in mpconfigport.h, but should not...)
	# rm -f -r build-ESP32_GENER.... folders
	# make clean	
	# make submodules
	# make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT
	# Once .bin was flashed, run this.
	rm -r romfs_temp
	mkdir romfs_temp
	mkdir romfs_temp/static
	# use compiled/compressed files for py and static
	cp device/mpy/* romfs_temp/
	cp device/static/* romfs_temp/static/
	# use uncompiled/uncompressed files for main.py and data
	cp crank-organ/src/main.py romfs_temp/
	python3 -m freezefs crank-organ/data temp.py --target=/data --on-import=extract --compress
	$(MPY_CROSS) temp.py -o romfs_temp/install_data.mpy
	mpremote romfs --no-mpy -o micropython_bin/romfs.bin build romfs_temp 

	# To generate image with romfs included:
	# press boot for long time with a short reset
	# esptool.py read_flash 0 0x200000 ESP32S3.bin
	# To test:
	# esptool.py write_flash 0 ESP32S3.bin
	# 
	# To make image:
	# python -m esptool --chip esp32s3 -b 460800 --before default_reset --after hard_reset write_flash --flash_mode dio --flash_size 4MB --flash_freq 80m 0x0 build-ESP32_GENERIC_S3-SPIRAM_OCT/bootloader/bootloader.bin 0x8000 build-ESP32_GENERIC_S3-SPIRAM_OCT/partition_table/partition-table.bin 0x10000 build-ESP32_GENERIC_S3-SPIRAM_OCT/micropython.bin
	-cp -n /Users/hermannvonborries/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/bootloader/bootloader.bin micropython_bin/
	-cp -n /Users/hermannvonborries/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/partition_table/partition-table.bin micropython_bin/
	-cp -n /Users/hermannvonborries/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/micropython.bin micropython_bin
	python3 -m esptool --chip esp32s3 merge_bin -o micropython_bin/organillo.bin --flash_mode dio --flash_size 4MB --flash_freq 80m 0x0 micropython_bin/bootloader.bin 0x8000 micropython_bin/partition-table.bin 0x10000 micropython_bin/micropython.bin 0x1C0000 micropython_bin/romfs.bin