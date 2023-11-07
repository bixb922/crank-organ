# crank-organ
MIDI based crank organ software and hardware

 Overview

This is a little context diagram:

![diagram](diagram.png)

A crank organ consists of windchests with pipes. A bellows pumps air into the windchests. One solenoid valve for each pipe controls the air flow, when open, the pipe sounds.

This hardware and software is the MIDI controller for this setup. It is controlled with a browser in a cell phone (or tablet or PC), and in turn controls the solenoid valves to open according to MIDI files stored in the microcontroller.

How is this solution used?

Once the hardware is build (see hardware plans in the doc-hardware folder), install the software, and put your MIDI files in the tunelib folder of the PC. You can add more information such as title to the music.

You control the order of the tunes with the cell phone. You select tunes to play by tapping on them on the tunelist page on the cell phone.

There are several ways to select tunes to be played:

The creative mode: Tap on a tune on the tunelist, and turn the crank (or touch and release the touchpad) and the tune plays. Then select the next tune, etc. You stay on the tunelist page.

The very creative mode: You can tap several tunes and queue them to play one after the other.

The diligent mode: Before a performance, you can tap several tunes and organize them into a setlist on the performance page. You save the setlist on flash to be ready for the next performance. When the performance begins, you power on the microcontroller, turn the crank (or touch and release the touchpad) and the setlist plays. No need to pull out the cell phone or to push buttons.

The diligent and flexible mode: You can modify the setlist on the fly with the performance page. You can delete or skip a tune, reorder tunes, or select a new tune and move to the top of the list, according to the audience and your wishes.

The very lazy mode: Don't use your cell phone. Don't define a setlist. Turn the microcontroller on. Turn the crank or touch the touchpad. All available tunes will be shuffled randomly and played. 

# Description

This is the complete software for automating a MIDI and solenoid valve based crank organ. A description on how to build the electronic hardware is included in the doc-hardware folder.

Please see the doc-software folder, click the file README.md for a detailed description of the software, with screen images.

See the doc-hardware folder, click the file README.md for schematics of the hardware and detailed instructions on how to build the hardware.

This is work in progress. Please post an issue for questions or observations.  I'll be happy to correct any problem and will try to help if there is an issue.

Time permitting, I'll complete this repository:
* Better description of hardware and building the hardware
* Better description of I2C based controller cards for more than 20 pipes
* Crank rotation sensor (tachometer)


# Folders
These are the folders in this GITHUB repository. On a cell phone, select "Browse code". On a PC, you should see the folders at https://github.com/bixb922/crank-organ

| Folder     | Contents                             |
|------------|--------------------------------------|
|Documentation                                      |
|doc-software|Description of the controller software. Open README.md|
|doc-hardware|Description of the controller hardware. Open README.md|
|Software folders                                   |
|src| Source code (MicroPython) |
|data| Pin assignment (pinout) configuration files |
|static| Web pages for the microcontroller (html)   |
|data| Pinout templates for 20, 26 and 31 note organs |
|install|Installation files                      |



# License
This license and disclaimer also covers the hardware design. The hardware design is part of the software published here.

Copyright (c) 2023 Hermann Paul von Borries

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


