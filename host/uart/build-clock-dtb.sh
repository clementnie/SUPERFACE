#!/bin/sh
# Build a separate clock trial from the validated pinmux DTB.
set -eu
stock=false
if [ "$#" -eq 3 ] && [ "$1" = --stock ]; then
    stock=true
    shift
fi
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 [--stock] UART2_PINMUX_CANDIDATE.dtb NEW_CLOCK_CANDIDATE.dtb" >&2
    exit 2
fi
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
base=$1
output=$2
ccu=/soc/clock@3001000
uart=/soc/serial@5000800
[ ! -e "$output" ] && [ ! -L "$output" ]
case " $(fdtget -t s "$base" / compatible) " in *' xunlong,orangepi-zero2w '*) ;; *) exit 1;; esac
[ "$(fdtget -t s "$base" "$uart" status)" = okay ]
[ "$(fdtget -t s "$base" "$uart" compatible)" = snps,dw-apb-uart ]
[ "$(fdtget -t s "$base" "$ccu" compatible)" = allwinner,sun50i-h616-ccu ]
handle=$(fdtget -t x "$base" "$ccu" phandle)
[ "$(fdtget -t x "$base" "$uart" clocks)" = "$handle 44" ]
if fdtget -p "$base" "$ccu" | grep -q '^assigned-clock'; then
    echo 'Review existing CCU clock assignments before building a clock trial' >&2
    exit 1
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
trap 'exit 1' HUP INT TERM
candidate=$tmp/clock.dtb
# Linux 6.9.4 provider IDs: PLL_PERIPH0=4, APB2=27.
if $stock; then
    cp -- "$base" "$candidate"
    # On the audited 24 MHz baseline, first set APB2 to OSC24M/16.
    # Before final retuning, any reparent transient is bounded by 576 MHz/16.
    fdtput -t x "$candidate" "$ccu" assigned-clocks "$handle" 1b "$handle" 4 "$handle" 1b
    fdtput -t u "$candidate" "$ccu" assigned-clock-rates 1500000 576000000 48000000
    [ "$(fdtget -t u "$candidate" "$ccu" assigned-clock-rates)" = '1500000 576000000 48000000' ]
    [ "$(fdtget -t s "$candidate" "$uart" compatible)" = snps,dw-apb-uart ]
else
    # This variant requires the staged UART and atomic APB2 kernel patches.
    dtc -@ -I dts -O dtb -o "$tmp/driver.dtbo" "$here/uart2-h616-driver.dts"
    fdtoverlay -i "$base" -o "$candidate" "$tmp/driver.dtbo"
    fdtput -t x "$candidate" "$ccu" assigned-clocks "$handle" 4 "$handle" 1b
    fdtput -t u "$candidate" "$ccu" assigned-clock-rates 576000000 48000000
    [ "$(fdtget -t u "$candidate" "$ccu" assigned-clock-rates)" = '576000000 48000000' ]
    [ "$(fdtget -t s "$candidate" "$uart" compatible)" = allwinner,sun50i-h616-uart ]
fi
cp -- "$candidate" "$output"
sha256sum "$base" "$output"
