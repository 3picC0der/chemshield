# Build and upload from the Pi (Debian packages arduino-mk arduino-core-avr gcc-avr avr-libc avrdude):
#   make            compile
#   make upload     load it onto the Uno (stop the station first)
BOARD_TAG = uno
ARDUINO_LIBS = EEPROM
MONITOR_PORT = /dev/ttyACM0
# Debian's own avrdude and its config (the bundled path has no config file)
AVRDUDE = /usr/bin/avrdude
AVRDUDE_CONF = /etc/avrdude.conf
include /usr/share/arduino/Arduino.mk
# Debian avr-size has no --format=avr: give it the hex
avr_size = $(SIZE) $(2)
