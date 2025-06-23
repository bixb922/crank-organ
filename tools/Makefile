# This makefile is used during software development.
# Use gmake -fcrank-organ/tools/Makefile
# Run from folder just above crank-organ

# Target compile: default, updates MC with changes, updates device/...
# Target freeze: to generate install files. No need to compile first.

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
PCFOLDER := "/Users/hermannvonborries/Google Drive/My Drive/midi/tunelib"
# MPREMOTE := python3 "/Users/hermannvonborries/Google Drive/My Drive/cosas/micropython/mpremote_chunk_15/mpremote.py"
MPREMOTE := mpremote

# Get device name testing WiFi MAC.
####x:=$(shell $(MPREMOTE) exec "import network;n='drehorgel' if network.WLAN(network.STA_IF).config('mac')==b'\xf4\x12\xfa\xe7\x29\x80' else 's3n8';print(n)">temp.txt)
x:=$(shell $(MPREMOTE) exec "import network;print(network.WLAN(network.STA_IF).config('hostname'))">temp.txt)
DEVICENAME := $(strip $(file < temp.txt))
#x=$(shell rm temp.txt)
CONFIGFOLDER := config-$(DEVICENAME)
# Get time stamp, for example for backup files
NOW := $(shell date "+%Y%m%d-%H%M%S")
# Set date on microcontroller
x:=$(shell $(MPREMOTE) rtc --set)

define COPYFILE
	$(MPREMOTE) cp $< :$(subst \,/,$(subst device/root,,$@))
	cp $< $@
endef

define COMPRESS_STATIC
	gzip -9 -c -k $< > temp.gz
	$(MPREMOTE) cp temp.gz :/software/static/$(notdir $@)
	cp temp.gz $@
endef

define COMPILE
	$(MPY_CROSS) -march=xtensawin $< -o temp.mpy
	$(MPREMOTE) cp temp.mpy :/software/mpy/$(basename $(<F)).mpy
	cp temp.mpy $@
endef

MPY_FILES := \
device/root/software/mpy/compiledate.mpy \
device/root/software/mpy/fileops.mpy \
device/root/software/mpy/battery.mpy \
device/root/software/mpy/config.mpy \
device/root/software/mpy/counter.mpy \
device/root/software/mpy/drehorgel.mpy \
device/root/software/mpy/driver_base.mpy \
device/root/software/mpy/driver_gpio.mpy \
device/root/software/mpy/driver_gpioservo.mpy \
device/root/software/mpy/driver_mcp23017.mpy \
device/root/software/mpy/driver_midiserial.mpy \
device/root/software/mpy/driver_null.mpy \
device/root/software/mpy/driver_ftoms.mpy \
device/root/software/mpy/driver_pca9685.mpy \
device/root/software/mpy/filemanager.mpy \
device/root/software/mpy/history.mpy \
device/root/software/mpy/led.mpy \
device/root/software/mpy/matrix.mpy \
device/root/software/mpy/midi.mpy \
device/root/software/mpy/midicontroller.mpy \
device/root/software/mpy/minilog.mpy \
device/root/software/mpy/microdot.mpy \
device/root/software/mpy/organtuner.mpy \
device/root/software/mpy/microphone.mpy \
device/root/software/mpy/pinout.mpy \
device/root/software/mpy/player.mpy \
device/root/software/mpy/poweroff.mpy \
device/root/software/mpy/scheduler.mpy \
device/root/software/mpy/setlist.mpy \
device/root/software/mpy/solenoid.mpy \
device/root/software/mpy/startup.mpy \
device/root/software/mpy/tachometer.mpy \
device/root/software/mpy/timezone.mpy \
device/root/software/mpy/touchpad.mpy \
device/root/software/mpy/tunemanager.mpy \
device/root/software/mpy/umidiparser.mpy \
device/root/software/mpy/webserver.mpy \
device/root/software/mpy/wifimanager.mpy \
device/root/software/mpy/frequency.mpy \
device/root/software/mpy/fft_arrays.mpy \
device/root/software/mpy/pcnt.mpy \
device/root/software/mpy/mcserver.mpy 

STATIC_FILES := \
device/root/software/static/common.js.gz \
device/root/software/static/config.html.gz \
device/root/software/static/diag.html.gz \
device/root/software/static/crank.jpg \
device/root/software/static/drums.html.gz \
device/root/software/static/favicon.ico \
device/root/software/static/favicon.png \
device/root/software/static/filemanager.html.gz \
device/root/software/static/index.html.gz \
device/root/software/static/history.html.gz \
device/root/software/static/note.html.gz \
device/root/software/static/notelist.html.gz \
device/root/software/static/pinout.html.gz \
device/root/software/static/play.html.gz \
device/root/software/static/tunelibedit.html.gz \
device/root/software/static/tunelist.html.gz \
device/root/software/static/show_midi.html.gz \
device/root/software/static/skeleton.css.gz \
device/root/software/static/translations.js.gz 

DATA_FILES := \
device/data/20_note_Carl_Frei.json \
device/data/35_note_custom.json \
device/data/48_note_custom.json \
device/data/26_note_Alderman_Wright.json \
device/data/31_note_Raffin.json \
device/data/drumdef.json \
device/data/pinout.txt 

all_inputs :  compiledate device/root/main.py $(MPY_FILES) $(STATIC_FILES) $(DATA_FILES)

compiledate:
	echo $(NOW) $(DEVICENAME) $(CONFIGFOLDER) 
	python3 crank-organ/tools/write_compiledate.py
	# echo compiledate=""`date +\%Y-\%m-\%d\ \%H:\%M:\%S`"" > crank-organ/src/compiledate.py

device/root/main.py: crank-organ/src/main.py
	$(MPREMOTE) cp $< :main.py
	cp $< $@

device/root/software/mpy/mcserver.mpy: server/mcserver.py
	$(COMPILE)
	
device/root/software/mpy/%.mpy: crank-organ/src/%.py
	$(COMPILE)

device/data/%.json: crank-organ/data/%.json
	cp $< $@

device/data/%.txt: crank-organ/data/%.txt
	cp $< $@

device/root/software/static/%.gz: crank-organ/static/%
	$(COMPRESS_STATIC)

device/root/software/static/%.jpg: crank-organ/static/%.jpg
	$(COPYFILE)
	
device/root/software/static/%.png: crank-organ/static/%.png
	$(COPYFILE)

device/root/software/static/%.ico: crank-organ/static/%.ico
	$(COPYFILE)

prepare_git: 
	python3 crank-organ/tools/update-toc.py
	-rm device/root/software/mpy/mcserver.mpy
	-rm device/root/software/mpy/mcserver.py
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
	-$(MPREMOTE) exec "import os;print('remove signal*.tsv files', len([os.remove(f) for f in os.listdir() if f.startswith('signal') and f.endswith('.tsv')]))"
	-$(MPREMOTE) rm /main.py
	$(MPREMOTE) mkdir software
	$(MPREMOTE) mkdir software/mpy
	$(MPREMOTE) mkdir software/static
	-$(MPREMOTE) mkdir lib
	-$(MPREMOTE) mkdir data
	-$(MPREMOTE) mkdir tunelib
	echo "/tunelib /lib and /data were kept"
	

	
cleanpc:
	-rm -r device/root
	-rm -r device/data
	-mkdir device
	mkdir device/root
	mkdir device/root/software
	mkdir device/root/software/mpy
	mkdir device/root/software/static
	mkdir device/data

initdevice:
	$(MPREMOTE) mkdir software
	$(MPREMOTE) mkdir software/static
	$(MPREMOTE) mkdir software/mpy
	$(MPREMOTE) mkdir data
	$(MPREMOTE) mkdir lib
	$(MPREMOTE) mkdir tunelib
	$(MPREMOTE) mip install aiohttp
	$(MPREMOTE) mip install shutil

initpc:
	mkdir device/root/software
	mkdir device/root/software/mpy
	mkdir device/root/software/static
	mkdir device/root/data
	mkdir device/tunelib

installdevice: 
	$(MPREMOTE) mip install shutil
	#curl https://raw.githubusercontent.com/micropython/micropython-lib/refs/heads/master/python-stdlib/datetime/datetime.py --output datetime.py
	#curl https://raw.githubusercontent.com/micropython/micropython-lib/refs/heads/master/python-stdlib/datetime/localtz.patch --output localtz.patch
	#patch -p2 < localtz.patch
	#$(MPREMOTE) cp datetime.py :/lib/
	#rm -r datetime.py.orig
	#rm -r localtz.patch
	$(MPREMOTE) run crank-organ/install/install_software.py  
	$(MPREMOTE) run crank-organ/install/install_data.py 

updatedevice:
	$(MPREMOTE) mip install shutil
	$(MPREMOTE) cp device/root/software/mpy/* :/software/mpy/
	$(MPREMOTE) cp device/root/software/static/* :/software/static/
	$(MPREMOTE) cp device/root/main.py :/
	echo don't update /data nor /tunelib

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
