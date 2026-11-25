#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then echo "Usage: $0 INSTALLED_BASE.dtb NEW_CANDIDATE.dtb" >&2; exit 2; fi
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
base=$1
output=$2
uart=/soc/serial@5000800
pio=/soc/pinctrl@300b000
pins=$pio/uart2-pi-superface-pins
[ ! -e "$output" ] && [ ! -L "$output" ]
case " $(fdtget -t s "$base" / compatible) " in *' xunlong,orangepi-zero2w '*) ;; *) exit 1;; esac
[ "$(fdtget -t s "$base" "$uart" compatible)" = snps,dw-apb-uart ]
[ "$(fdtget -t s "$base" "$uart" status)" = disabled ]
[ "$(fdtget -t x "$base" "$uart" reg)" = '5000800 400' ]
[ "$(fdtget -t s "$base" "$pio" compatible)" = allwinner,sun50i-h616-pinctrl ]
# Refuse an unknown clock wiring instead of repurposing a different controller.
ccu=$(fdtget -t x "$base" /soc/clock@3001000 phandle)
[ "$(fdtget -t x "$base" "$uart" clocks)" = "$ccu 44" ] # CLK_BUS_UART2 = 68

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
trap 'exit 1' HUP INT TERM
dtc -@ -I dts -O dtb -o "$scratch/uart2.dtbo" "$here/uart2-pi.dts"
fdtoverlay -i "$base" -o "$scratch/candidate.dtb" "$scratch/uart2.dtbo"
candidate=$scratch/candidate.dtb
[ "$(fdtget -t s "$candidate" "$pins" pins)" = 'PI5 PI6' ]
[ "$(fdtget -t s "$candidate" "$pins" function)" = uart2 ]
[ "$(fdtget -t s "$candidate" "$uart" status)" = okay ]
[ "$(fdtget -t x "$candidate" "$uart" pinctrl-0)" = "$(fdtget -t x "$candidate" "$pins" phandle)" ]
[ "$(fdtget -t x "$candidate" "$uart" clocks)" = "$ccu 44" ]
[ "$(fdtget -t s "$candidate" /chosen stdout-path)" = "$(fdtget -t s "$base" /chosen stdout-path)" ]
cp -- "$candidate" "$output"
sha256sum "$base" "$output"
