#!/bin/sh
# Run on the board. Root access adds clock, driver, and pin ownership details.
set -eu
dt=/sys/firmware/devicetree/base
[ "$(uname -m)" = aarch64 ]
tr '\0' '\n' < "$dt/compatible" | grep -qx xunlong,orangepi-zero2w
uname -sr
tr '\0' '\n' < "$dt/model"
tr ' ' '\n' </proc/cmdline |
    grep -E '^(console=|root=PARTUUID=|initrd=|cma=|earlycon(=|$)|ro$|rw$|rootwait$)'
findmnt /boot
lsblk -o NAME,FSTYPE,PARTUUID,MOUNTPOINTS
awk '
    toupper($1) ~ /^(DEFAULT|LABEL|LINUX|KERNEL|INITRD|FDT|FDTDIR|TIMEOUT|PROMPT|ONTIMEOUT)$/ {print}
    toupper($1) == "APPEND" {
        for (i=2; i<=NF; i++)
            if ($i ~ /^(console=|root=PARTUUID=|initrd=|cma=|earlycon(=|$)|ro$|rw$|rootwait$)/)
                print $i
    }' /boot/extlinux/extlinux.conf
sha256sum /boot/extlinux/extlinux.conf /boot/Image /boot/initramfs-linux.img \
    /boot/dtbs/allwinner/sun50i-h618-orangepi-zero2w.dtb
if [ -r /sys/firmware/fdt ]; then sha256sum /sys/firmware/fdt; fi
test -d "/usr/lib/modules/$(uname -r)"
for serial in "$dt"/soc/serial@*; do
    printf '%s ' "${serial##*/}"
    if [ -r "$serial/status" ]; then tr '\0' '\n' < "$serial/status"; else echo okay; fi
done
for tty in /sys/class/tty/ttyS*; do
    device=$(readlink -f "$tty")
    printf '%s %s\n' "$tty" "$device"
    while [ "${device#/sys/devices/}" != "$device" ]; do
        if [ -L "$device/of_node" ]; then
            readlink -f "$device/of_node"
            if [ -L "$device/driver" ]; then readlink -f "$device/driver"; fi
            break
        fi
        device=${device%/*}
    done
done
systemctl is-active serial-getty@ttyS0.service || :
for prop in "$dt/chosen/stdout-path" "$dt/chosen/u-boot,version"; do
    if [ -r "$prop" ]; then tr '\0' '\n' < "$prop"; fi
done
if [ -r /proc/config.gz ]; then
    zcat /proc/config.gz | grep -E '^CONFIG_(SERIAL_8250|PINCTRL_SUN50I_H616|SUN50I_H616_CCU|DMA_SUN6I)' || :
fi
if [ -r /sys/kernel/debug/clk/clk_summary ]; then
    cat /sys/kernel/debug/clk/clk_summary
else
    echo 'Clock tree unavailable (requires readable debugfs)'
fi
for pins in /sys/kernel/debug/pinctrl/*/pinmux-pins; do
    if [ -r "$pins" ]; then grep -E '\((PI5|PI6|PH0|PH1)\)' "$pins" || :; fi
done
if [ -r /proc/tty/driver/serial ]; then cat /proc/tty/driver/serial; fi
