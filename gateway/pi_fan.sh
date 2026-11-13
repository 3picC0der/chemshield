#!/usr/bin/env bash
# Pi 5 fan (the active cooler on the FAN header). The kernel runs the fan from the CPU
# temperature: by default it starts at 50 C and is at full speed at 75 C, so on a cool Pi it
# stays off. This moves those temperatures; the kernel still drives the fan.
#
#   sudo bash gateway/pi_fan.sh status     temperature, fan speed and the current settings
#   sudo bash gateway/pi_fan.sh on         full speed from now on (until reboot or "auto")
#   sudo bash gateway/pi_fan.sh cool       starts at 35 C, full speed at 60 C (quiet but cooler)
#   sudo bash gateway/pi_fan.sh auto       back to the Pi's defaults (50 / 60 / 67.5 / 75 C)
#   sudo bash gateway/pi_fan.sh persist on|cool|auto   the same, kept across reboots
#                                          (writes dtparam=fan_temp lines in config.txt)
set -euo pipefail
ZONE=/sys/class/thermal/thermal_zone0
CONFIG=/boot/firmware/config.txt

trips_for() {                            # the four "active" trip points, in millidegrees C
  case "$1" in
    on)   echo "20000 22000 24000 26000" ;;
    cool) echo "35000 45000 52000 60000" ;;
    auto) echo "50000 60000 67500 75000" ;;
    *) echo "unknown mode: $1 (on, cool or auto)" >&2; exit 2 ;;
  esac
}

status() {
  local hw rpm
  hw=$(ls -d /sys/devices/platform/cooling_fan/hwmon/hwmon* 2>/dev/null | head -1)
  rpm=$([ -n "$hw" ] && cat "$hw/fan1_input" || echo "?")
  echo "CPU $(( $(cat $ZONE/temp) / 1000 )) C, fan ${rpm} rpm, level $(cat /sys/class/thermal/cooling_device0/cur_state) of 4"
  echo -n "fan steps at:"
  for i in 1 2 3 4; do echo -n " $(( $(cat $ZONE/trip_point_${i}_temp) / 100 ))" | sed 's/\(.\)$/.\1/'; done
  echo " C"
}

apply_now() {
  local i=1 t
  for t in $(trips_for "$1"); do
    echo "$t" > "$ZONE/trip_point_${i}_temp"
    i=$((i + 1))
  done
}

persist() {
  local i=0 t
  trips_for "$1" >/dev/null
  cp "$CONFIG" "$CONFIG.bak-fan"
  sed -i '/^dtparam=fan_temp[0-3]=/d; /^# ChemShield fan$/d' "$CONFIG"
  if [ "$1" != auto ]; then
    echo "# ChemShield fan" >> "$CONFIG"
    for t in $(trips_for "$1"); do
      echo "dtparam=fan_temp${i}=${t}" >> "$CONFIG"
      i=$((i + 1))
    done
  fi
  echo "config.txt updated (backup: $CONFIG.bak-fan); it applies after the next reboot."
}

[ "$(id -u)" = 0 ] || { echo "run it with sudo" >&2; exit 1; }
case "${1:-status}" in
  status) status ;;
  on|cool|auto) apply_now "$1"; sleep 3; status ;;
  persist) persist "${2:?persist needs on, cool or auto}"; apply_now "$2"; sleep 3; status ;;
  *) echo "usage: sudo bash gateway/pi_fan.sh status|on|cool|auto|persist <mode>" >&2; exit 2 ;;
esac
