# >>> add Microdot and umidiparser as submodules.
# >>> update Microdot to latest version. Use native authentication.
# >>> check if multipart/form-data is useful.

# This makefile is used during software development.
# Use gmake -fcrank-organ/tools/Makefile
# Run from folder just above crank-organ

# Target compile: compiles .py and compresses html/js/css
# Target update: compiles/compresses and updates microcontroller

# Target cleanpc: removes device folder with compiled files
# on PC,
# forces all files to compile/regenerate again
#
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
# Get time stamp for compiledate.py
NOW := $(shell date "+%Y%m%d-%H%M%S")
# Set date on microcontroller (disabled to run makefile without microcontroller)
# x:=$(shell $(MPREMOTE) rtc --set)


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
	echo device update main.py
	$(MPREMOTE) cp $< :main.py
	cp $< device/update/$(notdir $<)

device/update/%.mpy: device/mpy/%.mpy
	echo device update mpy: $<
	$(MPREMOTE) cp $< :software/mpy/$(notdir $<)
	cp $< device/update/$(notdir $<)

device/update/%.gz : device/static/%.gz
	echo device update gz: $<
	$(MPREMOTE) cp $< :software/static/$(notdir $<)
	cp $< device/update/$(notdir $<)


# Target "compile": compile py to mpy, compress html/js to gz
# Compilation results to device/mpy
# Compression results to device/static
compile: $(addprefix device/mpy/, $(MPY_FILES)) $(addprefix device/static/,  $(STATIC_FILES))

compiledate:
	python3 crank-organ/tools/write_compiledate.py
	$(MPY_CROSS) -march=xtensawin crank-organ/src/compiledate.py -o device/mpy/compiledate.mpy

device/mpy/mcserver.mpy: server/mcserver.py
	echo mpy-cross $<
	$(MPY_CROSS) -march=xtensawin $< -o $@
	
device/mpy/%.mpy: crank-organ/src/%.py
	echo mpy-cross $<
	$(MPY_CROSS) -march=xtensawin $< -o $@

device/static/%.js.gz: crank-organ/static/%.js
	echo gzip $<
	gzip -9 -c -k $< > $@

device/static/%.html.gz: crank-organ/static/%.html
	echo gzip $<
	gzip -9 -c -k $< > $@

device/static/%.css.gz: crank-organ/static/%.css
	echo gzip $<
	gzip -9 -c -k $< > $@


prepare_git: romfs
	python3 crank-organ/tools/check_translations.py
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
	cp crank-organ/tools/boot.py freezetemp/
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

initpc:
	mkdir device
	mkdir device/mpy
	mkdir device/static

installdevice: 
	$(MPREMOTE) run crank-organ/install/install_software.py  
	$(MPREMOTE) run crank-organ/install/install_data.py 


romfs: compile
	# V1.26 previews:
	# git rebase -i f77fd62... and edit file 
	# to remove commit d737112 "esp32/esp32_common.cmake: Use the tinyusb source files from ESP-IDF"
	#
	# Run tools/fix_mp_romfs.py
	# Then: generate MicroPython:
	# make -C mpy-cross
	# cd ports/esp32
	# make clean
	# make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT submodules
	# make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT
	# 
	# Then:
	# gmake romfs
	# 
	# Then:
	# cd micropython_bin
	# sh flash_mp.sh
	#
	-mkdir micropython_bin
	-rm -r -f romfs_temp
	mkdir romfs_temp
	mkdir romfs_temp/static
	# use compiled/compressed files for py and static
	cp device/mpy/* romfs_temp/
	-rm romfs_temp/mcserver.mpy
	cp device/static/* romfs_temp/static/
	cp crank-organ/static/*.ico romfs_temp/static/
	cp crank-organ/static/*.png romfs_temp/static/
	cp crank-organ/static/*.jpg romfs_temp/static/
	# use uncompiled/uncompressed files for main.py
	cp crank-organ/src/main.py romfs_temp/
	python3 -m freezefs crank-organ/data temp.py --target=/data --on-import=extract --compress
	$(MPY_CROSS) temp.py -o romfs_temp/install_data.mpy
	mpremote romfs --no-mpy -o micropython_bin/romfs.bin build romfs_temp 
	echo "Run flash_mp.sh in micropython_bin folder"

copy_mp_bin:
	#  cache results of MicroPython image compilation here
	-cp $(HOME)/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/bootloader/bootloader.bin ../../micropython_bin/
	-cp $(HOME)/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/partition_table/partition-table.bin ../../micropython_bin/
	-cp $(HOME)/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/micropython.bin ../../micropython_bin/
