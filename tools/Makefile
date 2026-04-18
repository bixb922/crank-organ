# >>> add Microdot and umidiparser as submodules.
# >>> update Microdot to latest version. Use native authentication.

# This makefile is used during software development.
# Run from folder just above crank-organ:
# Use gmake -C crank-organ/tools

# Target compile: compiles .py and compresses html/js/css
# Target update: compiles/compresses and updates microcontroller

# Target cleanpc: removes device folder with compiled files
# on PC,
# forces all files to compile/regenerate again
#
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
actuatorstats.mpy \
battery.mpy \
blemcs.mpy \
config.mpy \
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
filecache.mpy \
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
skeleton.css.gz \
translations.js.gz 


# Target "update": compile py to mpy, compress html/js to gz
# and copy to device and device/update folder. 
# device/update is used to test if file was copied to device.
# Does NOT update: *.jpg, *.ico, *.png, /data/*
update: compile $(addprefix device/update/, $(MPY_FILES)) $(addprefix device/update/,  $(STATIC_FILES))

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
compile: $(addprefix device/mpy/, $(MPY_FILES)) $(addprefix device/static/,  $(STATIC_FILES)) compiledate

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


 
cleandevice: backupdata
	-$(MPREMOTE) mpremote rm -r software
	-$(MPREMOTE) rm -r signals
	-$(MPREMOTE) rm /main.py
	-$(MPREMOTE) rm /boot.py
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

initpc:
	mkdir device
	mkdir device/mpy
	mkdir device/static


romfs: compile
	-mkdir crank-organ/bin
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
	python3 -m freezefs crank-organ/data temp.py --target=/data --on-import=extract --compress
	$(MPY_CROSS) temp.py -o romfs_temp/install_data.mpy
	mpremote romfs --no-mpy -o crank-organ/bin/romfs.bin build romfs_temp 
	echo "Run flash_mp.sh in crank-organ/bin folder"
	echo "or deploy with: mpremote romfs deploy romfs_temp"	
	echo "or deploy with: esptool.py --chip esp32s3 write_flash --flash_mode dio --flash_size 4MB --flash_freq 80m 0x1C0000 crank-organ/bin/romfs.bin"

copy_mp_bin:
	#  cache results of MicroPython image compilation here
	-cp $(HOME)/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/bootloader/bootloader.bin ../bin/
	-cp $(HOME)/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/partition_table/partition-table.bin ../bin/
	-cp $(HOME)/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/micropython.bin ../bin/
