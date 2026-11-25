#!/bin/sh
# NON-DESTRUCTIVE original-content verification through vendor PFL.
# P operation below applies ONLY to the volatile FPGA maintenance/restoration SOFs.
# Flash POF gets V (verify) ONLY. Never substitute P/PV/R before authorization.
set -eu
[ "$#" = 6 ] || exit 2
quartus_bin=$1; maintenance=$2; terminal=$3; recovery=$4; wrong=$5; logs=$6
mkdir -p "$logs"
export LD_PRELOAD=/usr/lib/libc.so.6
restore() { "$quartus_bin/quartus_pgm" --64bit -m jtag -c 1 -o "p;$terminal" > "$logs/restore-terminal.log" 2>&1; }
trap restore EXIT
trap 'exit 1' HUP INT TERM
"$quartus_bin/quartus_pgm" --64bit -m jtag -c 1 -o "p;$maintenance" > "$logs/load-maintenance.log" 2>&1
"$quartus_bin/quartus_pgm" --64bit -m jtag -c 1 "$recovery" > "$logs/verify-original.log" 2>&1
# Negative control: unchanged Flash MUST reject the different font candidate.
if "$quartus_bin/quartus_pgm" --64bit -m jtag -c 1 "$wrong" > "$logs/verify-wrong-image.log" 2>&1; then
    echo 'FAIL verification negative control: different image reported success' > "$logs/result.txt"
    exit 1
fi
echo 'PASS original verified and different image rejected' > "$logs/result.txt"
