#!/bin/sh
# READ-ONLY Flash examination, automatic restoration of volatile terminal SOF.
set -eu
[ "$#" = 5 ] || exit 2
quartus_bin=$1; maintenance=$2; terminal=$3; chain=$4; logs=$5
mkdir -p "$logs"
# Fail closed unless this is the vendor-UI-generated EXAMINE ONLY profile.
python3 - "$chain" <<'PY'
from pathlib import Path
import sys,re
s=Path(sys.argv[1]).read_text()
assert 'OpMask(0)' in s and 'Child_OpMask(2 8 8)' in s
assert len(re.findall(r'Child_OpMask',s))==1
PY
export LD_PRELOAD=/usr/lib/libc.so.6
restore() { "$quartus_bin/quartus_pgm" --64bit -m jtag -c 1 -o "p;$terminal" > "$logs/restore-terminal.log" 2>&1; }
trap restore EXIT
trap 'exit 1' HUP INT TERM
"$quartus_bin/quartus_pgm" --64bit -m jtag -c 1 -o "p;$maintenance" > "$logs/load-maintenance.log" 2>&1
"$quartus_bin/quartus_pgm" --64bit -c 1 "$chain" > "$logs/examine.log" 2>&1
