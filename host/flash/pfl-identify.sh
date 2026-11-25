#!/bin/sh
# Configure ONLY volatile FPGA, auto-detect ONLY, restore terminal on exit.
# Contains no Flash erase/program operation. Do not add one here.
set -eu
[ "$#" = 4 ] || { echo 'Usage: pfl-identify.sh QUARTUS_BIN MAINTENANCE_SOF TERMINAL_SOF LOG_DIR' >&2; exit 2; }
quartus_bin=$1
maintenance=$2
terminal=$3
logs=$4
mkdir -p "$logs"
export LD_PRELOAD=/usr/lib/libc.so.6
restore() {
    "$quartus_bin/quartus_pgm" --64bit -m jtag -c 1 -o "p;$terminal" > "$logs/restore-terminal.log" 2>&1
}
trap restore EXIT
trap 'exit 1' HUP INT TERM
env -u LD_PRELOAD "$quartus_bin/jtagconfig" > "$logs/jtag-target.log"
# Require exactly one expected CycloneII target before configuring it.
python3 - "$logs/jtag-target.log" <<'PY'
import re,sys
s=open(sys.argv[1]).read()
assert len(re.findall(r'^\s*[0-9A-F]{8}\s+',s,re.M))==1 and '020B30DD' in s,s
PY
"$quartus_bin/quartus_pgm" --64bit -m jtag -c 1 -o "p;$maintenance" > "$logs/load-maintenance.log" 2>&1
"$quartus_bin/quartus_pgm" --64bit -c 1 -a > "$logs/auto-detect.log" 2>&1
env -u LD_PRELOAD "$quartus_bin/jtagconfig" --debug > "$logs/jtag-debug.log" 2>&1
