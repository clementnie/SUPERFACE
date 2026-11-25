#!/bin/sh
# Run as root only on the audited target, after securing private recovery access.
set -eu
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 BASE_DTB_SHA256 EXTLINUX_SHA256 VALIDATED_CANDIDATE.dtb" >&2
    exit 2
fi
[ "$(id -u)" = 0 ]
[ "$(uname -m)" = aarch64 ]
tr '\0' '\n' < /sys/firmware/devicetree/base/compatible | grep -qx xunlong,orangepi-zero2w
findmnt -n -o FSTYPE --mountpoint /boot | grep -qx vfat
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
config=/boot/extlinux/extlinux.conf
base=/boot/dtbs/allwinner/sun50i-h618-orangepi-zero2w.dtb
candidate=/boot/dtbs/allwinner/sun50i-h618-orangepi-zero2w-superface-uart2.dtb
tmpconf=/boot/extlinux/.superface-extlinux.new
[ ! -e "$tmpconf" ] && [ ! -e "$candidate" ]
printf '%s  %s\n' "$1" "$base" "$2" "$config" | sha256sum -c -
test -d "/usr/lib/modules/$(uname -r)"
command -v dtc fdtget fdtoverlay python3 >/dev/null
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
trap 'exit 1' HUP INT TERM
sh "$here/build-dtb.sh" "$base" "$work/uart2.dtb"
cmp "$work/uart2.dtb" "$3"

# Accept one strict original extlinux entry. Preserve it verbatim as the default.
python3 "$here/render-extlinux.py" "$config" "$work/extlinux.conf"
umask 077
backup=$(mktemp -d /var/backups/superface-uart2.XXXXXXXX)
sha256sum "$config" "$base" /boot/Image /boot/initramfs-linux.img > "$backup/boot-before.sha256"
cp -- "$config" "$backup/extlinux.conf"
cp -- "$base" "$backup/baseline.dtb"
cmp "$config" "$backup/extlinux.conf"
cmp "$base" "$backup/baseline.dtb"
sha256sum -c "$backup/boot-before.sha256"
install -m644 "$work/uart2.dtb" "$candidate"
install -m644 "$work/extlinux.conf" "$tmpconf"
sync
mv -T -- "$tmpconf" "$config"
sync
sha256sum "$config" "$candidate"
printf 'Baseline backup: %s\nOriginal entry remains default. No reboot performed.\n' "$backup"
