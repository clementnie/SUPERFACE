#!/usr/bin/env python3
"""Generate a full-device data-only PFL conversion plan. Performs no hardware I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib
from xml.sax.saxutils import escape

CAPACITY = 4 * 1024 * 1024


def ihex(address, kind, data):
    record = struct.pack(">BHB", len(data), address, kind) + data
    return ":" + record.hex().upper() + f"{-sum(record) & 255:02X}\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--preserve", type=Path, required=True,
                        help="verified current full-device contents to retain outside the font")
    parser.add_argument("--preserve-sha256", required=True, help="recorded SHA-256 of the current contents")
    parser.add_argument("--recovery-only", action="store_true",
                        help="convert the verified preservation image without applying the new font")
    args = parser.parse_args()
    font = args.font.read_bytes()
    manifest = json.loads(args.manifest.read_text())
    old = args.preserve.read_bytes()
    assert len(old) == CAPACITY and hashlib.sha256(old).hexdigest() == args.preserve_sha256
    assert hashlib.sha256(font).hexdigest() == manifest["files"][args.font.name]["sha256"]
    assert len(font) == manifest["flash"]["image_bytes"] <= manifest["flash"]["partition_end_byte_exclusive"]
    assert font[20:36].hex() == manifest["mapping"]["mapping_id_hex"]
    assert zlib.crc32(font[64:]) == int.from_bytes(font[36:40], "little")
    assert zlib.crc32(font[:60]) == int.from_bytes(font[60:64], "little")
    data = old if args.recovery_only else font + old[len(font):]
    out = args.output.resolve()
    out.mkdir(mode=0o700)
    (out / "candidate.bin").write_bytes(data)
    with (out / "candidate.hex").open("w") as handle:
        for high in range(CAPACITY // 65536):
            handle.write(ihex(0, 4, high.to_bytes(2, "big")))
            for low in range(0, 65536, 32):
                start = high * 65536 + low
                handle.write(ihex(low, 0, data[start:start + 32]))
        handle.write(ihex(0, 1, b""))
    (out / "candidate.cof").write_text(f"""<?xml version="1.0" encoding="US-ASCII" standalone="yes"?>
<cof>
 <eprom_name>CFI_32MB</eprom_name>
 <output_filename>{escape(str(out / 'candidate.pof'))}</output_filename>
 <n_pages>0</n_pages><width>1</width><mode>0</mode>
 <hex_block><hex_filename>{escape(str(out / 'candidate.hex'))}</hex_filename><hex_addressing>absolute</hex_addressing><hex_little_endian>0</hex_little_endian></hex_block>
 <version>9</version><options><map_file>1</map_file></options>
</cof>
""")
    print(f"Font SHA-256 {hashlib.sha256(font).hexdigest()}")
    print(f"Full-device candidate SHA-256 {hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main()
