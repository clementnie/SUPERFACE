"""Render a selectable UART2 trial while keeping the original entry the default."""

from pathlib import Path
import re
import sys

options = sys.argv[3:]
if len(sys.argv) < 3 or options not in ([], ["--clock"]):
    raise SystemExit("Usage: render-extlinux.py ORIGINAL OUTPUT [--clock]")
source, dest = map(Path, sys.argv[1:3])
original = source.read_bytes()
if re.search(rb"(?im)^\s*(include|localboot|ipappend|fdtoverlays|devicetree|devicetree-overlay)\s+", original):
    raise SystemExit("Unsupported extlinux directives require manual review")
text = original.decode("ascii")
directives = re.findall(rb"(?im)^\s*(label|linux|kernel|initrd|fdt|fdtdir|append|default|timeout|prompt|ontimeout)\s+([^\r\n]+)", original)
found = {}
for raw_key, raw_value in directives:
    key = raw_key.lower()
    if key in found:
        raise SystemExit("Expected a single existing extlinux entry")
    found[key] = raw_value.strip()
label = found.get(b"label", b"")
if (not re.fullmatch(rb"[\w .-]+", label)
        or found.get(b"default", label) != label
        or found.get(b"ontimeout", label) != label
        or b"fdtdir" in found
        or sum(key in found for key in (b"linux", b"kernel")) != 1
        or found.get(b"linux", found.get(b"kernel")) != b"/Image"
        or found.get(b"initrd", b"/initramfs-linux.img") != b"/initramfs-linux.img"
        or found.get(b"fdt") != b"/dtbs/allwinner/sun50i-h618-orangepi-zero2w.dtb"
        or b"console=ttyS0,115200" not in found.get(b"append", b"").split()
        or not re.search(rb"(?:^| )root=PARTUUID=[0-9a-fA-F-]+(?: |$)", found[b"append"])):
    raise SystemExit("Review the installed extlinux entry before staging")
text = re.sub(r"(?im)^\s*(default|timeout|prompt|ontimeout)\s+[^\r\n]+", "", text)
candidate = b"\nLABEL superface-uart2\n  MENU LABEL SUPERFACE UART2 pinmux trial\n"
candidate += b"  " + (b"LINUX" if b"linux" in found else b"KERNEL") + b" /Image\n"
if b"initrd" in found:
    candidate += b"  INITRD " + found[b"initrd"] + b"\n"
candidate += b"  FDT /dtbs/allwinner/sun50i-h618-orangepi-zero2w-superface-uart2.dtb\n"
candidate += b"  APPEND " + found[b"append"] + b"\n"
if options:
    trial = candidate.replace(b"LABEL superface-uart2\n", b"LABEL superface-uart2-clock\n", 1) \
        .replace(b"SUPERFACE UART2 pinmux trial", b"SUPERFACE UART2 3 Mbaud trial", 1) \
        .replace(b"zero2w-superface-uart2.dtb", b"zero2w-superface-uart2-clock.dtb", 1)
    candidate += trial
dest.write_bytes(b"DEFAULT " + label + b"\nPROMPT 1\nTIMEOUT 100\n" +
                 text.strip().encode("ascii") + b"\n" + candidate)
