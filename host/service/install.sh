#!/bin/sh
# Run privately as root AFTER reviewing the staged files and checksum manifest.
# Changes service/device permissions only; never changes bootloader/DT/kernel.
set -eu
[ "$(id -u)" = 0 ]
base=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$base"
sha256sum -c SERVICE-SHA256SUMS
[ -x /usr/bin/login ]
# Verify the terminfo source before making persistent changes.
terminfo=$(mktemp -d)
trap 'rm -rf -- "$terminfo"' EXIT
tic -x -o "$terminfo" service/superface.terminfo
[ -f "$terminfo/s/superface" ]
[ -d /sys/devices/platform/soc/5000800.serial ]
# An identical running installation is already complete: no needless restart.
if systemctl is-active --quiet superface.service &&
   cmp -s "$terminfo/s/superface" /usr/share/terminfo/s/superface &&
   cmp -s build/superface /opt/superface/bin/superface &&
   cmp -s build/superface-uart /opt/superface/bin/superface-uart &&
   cmp -s service/check-uart /opt/superface/bin/check-uart &&
   cmp -s service/superface-layout /usr/local/bin/superface-layout &&
   cmp -s uart/find-tty.sh /opt/superface/bin/find-tty &&
   cmp -s service/superface.service /etc/systemd/system/superface.service &&
   cmp -s service/70-superface-uart.rules /etc/udev/rules.d/70-superface-uart.rules &&
   cmp -s login/superface.conf /etc/sysusers.d/superface.conf; then
    systemctl enable superface.service
    echo 'Identical installation already running; no restart needed.'
    systemctl --no-pager status superface.service
    exit 0
fi
if fuser /dev/ttyS2 >/dev/null 2>&1; then
    echo 'UART2 is in use; stop the development renderer first.' >&2
    exit 1
fi
backup=$(mktemp -d /var/backups/superface-service.XXXXXXXX)
for path in /usr/local/bin/superface-layout /opt/superface/bin/superface /opt/superface/bin/superface-uart /opt/superface/bin/find-tty /opt/superface/bin/check-uart /etc/systemd/system/superface.service /etc/udev/rules.d/70-superface-uart.rules /etc/sysusers.d/superface.conf /usr/share/terminfo/s/superface; do
    if [ -e "$path" ]; then cp --parents -p "$path" "$backup"; fi
done
systemctl is-enabled superface.service > "$backup/previous-enable-state" 2>&1 || :
# Minimal Manjaro installations can omit sysusers.d until it is first used.
# Create missing target directories before installing any persistent file.
for directory in /opt/superface/bin /usr/local/bin /etc/sysusers.d /etc/udev/rules.d /etc/systemd/system /usr/share/terminfo/s; do
    if [ ! -d "$directory" ]; then
        install -d -o root -g root -m 0755 "$directory"
    fi
done
install -o root -g root -m 0644 login/superface.conf /etc/sysusers.d/superface.conf
systemd-sysusers /etc/sysusers.d/superface.conf
install -o root -g root -m 0755 build/superface build/superface-uart /opt/superface/bin/
install -o root -g root -m 0755 uart/find-tty.sh /opt/superface/bin/find-tty
install -o root -g root -m 0755 service/check-uart /opt/superface/bin/check-uart
install -o root -g root -m 0755 service/superface-layout /usr/local/bin/superface-layout
install -o root -g root -m 0644 service/70-superface-uart.rules /etc/udev/rules.d/
install -o root -g root -m 0644 service/superface.service /etc/systemd/system/
install -o root -g root -m 0644 "$terminfo/s/superface" /usr/share/terminfo/s/superface
udevadm control --reload-rules
udevadm trigger --action=change /sys/class/tty/ttyS2
udevadm settle
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/superface.service
systemctl enable --now superface.service
printf 'Service rollback backup: %s\n' "$backup"
systemctl --no-pager status superface.service
