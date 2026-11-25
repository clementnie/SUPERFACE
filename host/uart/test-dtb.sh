#!/bin/sh
set -eu
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
trap 'exit 1' HUP INT TERM
cat > "$tmp/base.dts" <<'DTS'
/dts-v1/;
/ {
    compatible = "xunlong,orangepi-zero2w", "allwinner,sun50i-h616";
    #address-cells = <1>;
    #size-cells = <1>;
    chosen { stdout-path = "serial0:115200n8"; };
    aliases { serial0 = &uart0; };
    soc {
        #address-cells = <1>;
        #size-cells = <1>;
        ranges;
        ccu: clock@3001000 { compatible = "allwinner,sun50i-h616-ccu"; reg = <0x3001000 0x1000>; #clock-cells = <1>; };
        pinctrl@300b000 { compatible = "allwinner,sun50i-h616-pinctrl"; reg = <0x300b000 0x1000>; };
        uart0: serial@5000000 { reg = <0x05000000 0x400>; status = "okay"; };
        serial@5000800 {
            compatible = "snps,dw-apb-uart";
            reg = <0x05000800 0x400>;
            clocks = <&ccu 68>;
            status = "disabled";
        };
    };
};
DTS
dtc -I dts -O dtb -o "$tmp/base.dtb" "$tmp/base.dts"
sh "$here/build-dtb.sh" "$tmp/base.dtb" "$tmp/candidate.dtb"
[ "$(fdtget -t s "$tmp/base.dtb" /soc/serial@5000800 status)" = disabled ]
[ "$(fdtget -t s "$tmp/candidate.dtb" /soc/serial@5000000 status)" = okay ]
dtc -@ -I dts -O dtb -o "$tmp/driver.dtbo" "$here/uart2-h616-driver.dts"
fdtoverlay -i "$tmp/candidate.dtb" -o "$tmp/driver.dtb" "$tmp/driver.dtbo"
[ "$(fdtget -t s "$tmp/driver.dtb" /soc/serial@5000800 compatible)" = allwinner,sun50i-h616-uart ]
sh "$here/build-clock-dtb.sh" "$tmp/candidate.dtb" "$tmp/clock.dtb"
[ "$(fdtget -t x "$tmp/clock.dtb" /soc/clock@3001000 assigned-clocks)" = '1 4 1 1b' ]
[ "$(fdtget -t u "$tmp/clock.dtb" /soc/clock@3001000 assigned-clock-rates)" = '576000000 48000000' ]
sh "$here/build-clock-dtb.sh" --stock "$tmp/candidate.dtb" "$tmp/stock-clock.dtb"
[ "$(fdtget -t x "$tmp/stock-clock.dtb" /soc/clock@3001000 assigned-clocks)" = '1 1b 1 4 1 1b' ]
[ "$(fdtget -t s "$tmp/stock-clock.dtb" /soc/serial@5000800 compatible)" = snps,dw-apb-uart ]
if fdtget -t x "$tmp/clock.dtb" /soc/clock@3001000 assigned-clock-parents 2>/dev/null; then
    echo 'Unexpected explicit parent switch before dividers' >&2
    exit 1
fi
fdtput -t x "$tmp/base.dtb" /soc/serial@5000800 clocks 1 45
if sh "$here/build-dtb.sh" "$tmp/base.dtb" "$tmp/unexpected.dtb"; then
    echo 'Unexpected UART2 clock wiring was accepted' >&2
    exit 1
fi
echo 'UART2 DT overlay, baseline preservation, driver binding overlay and mismatched-base rejection passed'
cat > "$tmp/extlinux.conf" <<'CONF'
TIMEOUT 1
DEFAULT Manjaro ARM
LABEL Manjaro ARM
    KERNEL /Image
    FDT /dtbs/allwinner/sun50i-h618-orangepi-zero2w.dtb
    APPEND initrd=/initramfs-linux.img console=ttyS0,115200 root=PARTUUID=55aec0d2-02 cma=256M
CONF
python3 "$here/render-extlinux.py" "$tmp/extlinux.conf" "$tmp/staged.conf"
grep -Fx 'DEFAULT Manjaro ARM' "$tmp/staged.conf"
grep -Fx 'PROMPT 1' "$tmp/staged.conf"
grep -Fx 'LABEL superface-uart2' "$tmp/staged.conf"
python3 "$here/render-extlinux.py" "$tmp/extlinux.conf" "$tmp/three-entry.conf" --clock
grep -Fx 'LABEL superface-uart2-clock' "$tmp/three-entry.conf"
[ "$(grep -c '^LABEL ' "$tmp/three-entry.conf")" = 3 ]
[ "$(grep -c 'KERNEL /Image' "$tmp/staged.conf")" = 2 ]
[ "$(grep -c 'console=ttyS0,115200' "$tmp/staged.conf")" = 2 ]
cat >> "$tmp/extlinux.conf" <<'CONF'
ONTIMEOUT another
CONF
if python3 "$here/render-extlinux.py" "$tmp/extlinux.conf" "$tmp/refused.conf"; then
    echo 'Unexpected extlinux boot default was accepted' >&2
    exit 1
fi
echo 'Extlinux default and fallback-entry preservation passed'
