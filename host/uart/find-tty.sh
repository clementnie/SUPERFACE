#!/bin/sh
set -eu
for d in /sys/class/tty/ttyS*; do
    device=$(readlink -f "$d")
    # The controller may be above serial-base wrapper devices.
    while [ "${device#/sys/devices/}" != "$device" ]; do
        if [ -L "$device/of_node" ] && [ -L "$device/driver" ]; then
            node=$(readlink -f "$device/of_node")
            case "$node" in */serial@5000800)
                tty=/dev/${d##*/}
                if [ -c "$tty" ]; then printf '%s\n' "$tty"; exit 0; fi
            esac
        fi
        device=${device%/*}
    done
done
echo 'No bound tty for UART2 serial@5000800' >&2
exit 1
