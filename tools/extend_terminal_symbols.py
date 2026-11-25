#!/usr/bin/env python3
"""Append 8×16 terminal symbols to the reproducible Phase 7 font image."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import struct
import unicodedata
import zlib

import generate_superface_font as font

FIRST = 0x9ABC
RANGES = ((0x2190, 0x21FF), (0x2500, 0x257F), (0x2580, 0x259F), (0x2800, 0x28FF))
EXTRA = (
    0x00A0, 0x00B0, 0x00B1, 0x00B5, 0x00B7, 0x00D7, 0x00F7,
    0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026,
    0x20AC, 0x2212, 0x221A, 0x221E, 0x2248, 0x2260, 0x2264, 0x2265,
    0x25A0, 0x25A1, 0x25AA, 0x25AB, 0x25B2, 0x25B6, 0x25BC,
    0x25C0, 0x25C6, 0x25C7, 0x25CB, 0x25CF, 0x25E6,
)
HAND_DRAWN = {
    0x20AC: (0x1E, 0x20, 0x40, 0xFC, 0x40, 0xF8, 0x40, 0x20, 0x1E),
    0x2212: (0, 0, 0, 0, 0x7E, 0, 0, 0, 0),
    0x221A: (0x0F, 0x08, 0x08, 0x10, 0x10, 0x50, 0x50, 0x20, 0x20),
    0x221E: (0, 0, 0x66, 0x99, 0x89, 0x99, 0x66, 0, 0),
    0x2248: (0, 0, 0x32, 0x4C, 0, 0x32, 0x4C, 0, 0),
    0x2260: (0x02, 0x04, 0x08, 0x7E, 0x10, 0x7E, 0x20, 0x40, 0),
    0x2264: (0x04, 0x18, 0x60, 0x18, 0x04, 0, 0x7C, 0, 0),
    0x2265: (0x40, 0x30, 0x0C, 0x30, 0x40, 0, 0x7C, 0, 0),
}


def rows_from_pixels(pixels):
    return [sum(0x80 >> x for x in range(8) if (x, y) in pixels) for y in range(16)]


def rect(x0, y0, x1, y1):
    return {(x, y) for x in range(x0, x1) for y in range(y0, y1)}


def box(cp):
    tokens = unicodedata.name(chr(cp)).removeprefix("BOX DRAWINGS ")
    if "DIAGONAL" in tokens:
        forward = {(round(y * 7 / 15), y) for y in range(16)}
        backward = {(7 - x, y) for x, y in forward}
        return (forward | backward if "CROSS" in tokens else
                backward if "UPPER RIGHT" in tokens else forward)
    styles = {"LIGHT": 1, "SINGLE": 1, "HEAVY": 3, "DOUBLE": 2}
    global_style = styles.get(tokens.split()[0], 1)
    directions = {"HORIZONTAL": ("LEFT", "RIGHT"), "VERTICAL": ("UP", "DOWN")}
    pixels = set()
    for clause in tokens.split(" AND "):
        words = clause.split()
        style = next((styles[w] for w in words if w in styles), global_style)
        for word in words:
            for direction in directions.get(word, (word,)):
                if direction in ("LEFT", "RIGHT"):
                    y_rows = {1: (7,), 2: (6, 9), 3: (6, 7, 8)}[style]
                    extent = range(0, 5) if direction == "LEFT" else range(3, 8)
                    pixels.update((x, y) for x in extent for y in y_rows)
                if direction in ("UP", "DOWN"):
                    x_cols = {1: (3,), 2: (2, 5), 3: (2, 3, 4)}[style]
                    extent = range(0, 9) if direction == "UP" else range(7, 16)
                    pixels.update((x, y) for y in extent for x in x_cols)
    if "DASH" in tokens:
        segments = 2 if "DOUBLE DASH" in tokens else 3 if "TRIPLE" in tokens else 4
        horizontal = "HORIZONTAL" in tokens
        dimension = 8 if horizontal else 16
        gaps = {i * dimension // segments for i in range(1, segments)}
        pixels = {(x, y) for x, y in pixels if (x if horizontal else y) not in gaps}
    assert pixels, hex(cp)
    return pixels


def block(cp):
    if cp == 0x2580:
        return rect(0, 0, 8, 8)
    if cp <= 0x2588:
        return rect(0, 16 - 2 * (cp - 0x2580), 8, 16)
    if cp <= 0x258F:
        return rect(0, 0, 0x2590 - cp, 16)
    if cp == 0x2590:
        return rect(4, 0, 8, 16)
    if cp <= 0x2593:
        return {(x, y) for x, y in rect(0, 0, 8, 16)
                if ((0, 2), (3, 1))[y % 2][x % 2] < cp - 0x2590}
    if cp == 0x2594:
        return rect(0, 0, 8, 2)
    if cp == 0x2595:
        return rect(7, 0, 8, 16)
    quadrants = ((0, 0), (4, 0), (0, 8), (4, 8))
    mask = (4, 8, 1, 13, 9, 7, 11, 2, 6, 14)[cp - 0x2596]
    return set().union(*(rect(x, y, x + 4, y + 8) for bit, (x, y) in enumerate(quadrants)
                         if mask & (1 << bit)))


def braille(cp):
    positions = ((1, 1), (1, 5), (1, 9), (5, 1), (5, 5), (5, 9), (1, 13), (5, 13))
    return set().union(*(rect(x, y, x + 2, y + 2) for bit, (x, y) in enumerate(positions)
                         if (cp - 0x2800) & (1 << bit)))


def bitmap(record):
    width, height, x, y = map(int, font.bdf_field(record, "BBX").split())
    advance = int(font.bdf_field(record, "DWIDTH").split()[0])
    data = record[record.index("BITMAP") + 1:record.index("ENDCHAR")]
    assert len(data) == height and advance in (6, 12)
    # Preserve 6-pixel designs. Compress full-width originals to eight pixels.
    pixels = set()
    for row, encoded in enumerate(data, 11 - y - height):
        word = int(encoded or "0", 16)
        for dx in range(width):
            if word & (1 << (4 * len(encoded) - 1 - dx)):
                dest_x = (x + dx) * 8 // 12 if advance == 12 else 1 + x + dx
                if 0 <= dest_x < 8 and 0 <= row < 16:
                    pixels.add((dest_x, row))
    return rows_from_pixels(pixels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    font.verify_ascii()
    source, notices = font.load_source(args.archive)
    assets = font.ASSETS
    manifest_path = assets / font.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes())
    wide_count = manifest["mapping"]["chinese_count"]
    assert wide_count == FIRST - font.GLYPH_FIRST
    old_entries = csv.DictReader((assets / font.MAP_NAME).read_text().splitlines())
    entries = {int(row["unicode"][2:], 16): int(row["glyph_id"], 16) for row in old_entries
               if int(row["glyph_id"], 16) < FIRST}
    supported = sorted(set(EXTRA) | (set(range(0xA1, 0x100)) - {0xAD}) |
                       {cp for lo, hi in RANGES for cp in range(lo, hi + 1)})
    assert not (entries.keys() & set(supported))
    bdf = {}
    for raw in source.decode("ascii").split("\nSTARTCHAR ")[1:]:
        lines = raw.splitlines()
        cp = int(font.bdf_field(lines, "ENCODING"))
        if cp in supported:
            bdf[cp] = lines

    old_image = (assets / font.FLASH_NAME).read_bytes()
    prefix = old_image[64:64 + 32 * wide_count]
    payload = bytearray(prefix)
    for glyph, cp in enumerate(supported, FIRST):
        entries[cp] = glyph
        if 0x2500 <= cp <= 0x257F:
            rows = rows_from_pixels(box(cp))
        elif 0x2580 <= cp <= 0x259F:
            rows = rows_from_pixels(block(cp))
        elif 0x2800 <= cp <= 0x28FF:
            rows = rows_from_pixels(braille(cp))
        elif cp in HAND_DRAWN:
            rows = [0] * 3 + list(HAND_DRAWN[cp]) + [0] * 4
        else:
            rows = bitmap(bdf[cp])
        assert len(rows) == 16
        assert any(rows) or cp in (0xA0, 0x2800), hex(cp)
        payload.extend(struct.pack("<16H", *rows))

    mapping = ("unicode,glyph_id\n" +
               "".join(f"U+{cp:06X},0x{entries[cp]:04X}\n" for cp in sorted(entries))).encode()
    identity = font.mapping_id(mapping)
    count = wide_count + len(supported)
    image = font.build_flash(payload, count, identity)
    outputs = {font.MAP_NAME: mapping, font.MIF_NAME: font.build_mif(payload),
               font.FLASH_NAME: image, **notices}
    for name, data in outputs.items():
        (assets / name).write_bytes(data)
        manifest["files"][name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest["mapping"].setdefault("punctuation_mapping_hex", manifest["mapping"]["mapping_id_hex"])
    manifest["mapping"].update(sha256=hashlib.sha256(mapping).hexdigest(),
                               mapping_id_hex=identity.hex(), sram_count=count,
                               last_sram_id=FIRST + len(supported) - 1)
    manifest["mapping"]["missing_ids"] = {"single": 0x7F, "double": 0x80}
    manifest["repertoire"]["terminal_symbols"] = {
        "width": 1, "count": len(supported), "first_id": FIRST,
        "code_points": [f"U+{cp:04X}" for cp in supported],
        "wide_payload_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
    }
    manifest["repertoire"]["missing"]["fallback"] = "Dedicated width-one and width-two placeholders with the extended protocol"
    manifest["sram"].update(end_word_exclusive=len(payload) // 2, allocated_bytes=len(payload),
                            free_bytes=2 * font.SRAM_WORDS - len(payload),
                            useful_bytes=18 * wide_count + 16 * len(supported),
                            padding_bytes=14 * wide_count + 16 * len(supported))
    manifest["sram"]["terminal_symbols"] = {"width": 8, "height": 16, "leftmost_pixel_bit": 7}
    manifest["flash"].update(end_byte_exclusive=len(image), image_bytes=len(image),
                             payload_bytes=len(payload),
                             header_crc32_hex=f"{zlib.crc32(image[:60]):08x}",
                             payload_crc32_hex=f"{zlib.crc32(payload):08x}",
                             free_partition_bytes=font.FLASH_PARTITION_BYTES - len(image),
                             free_device_bytes_by_capacity={str(x): x - len(image) for x in font.FLASH_CAPACITIES})
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    vhdl = font.ROOT / "lab8_restored/Font_CRC.vhd"
    rtl = vhdl.read_text()
    rtl = re.sub(r"(constant glyphs : natural := )\d+;", rf"\g<1>{count};", rtl)
    if "constant wide_glyphs" not in rtl:
        rtl = rtl.replace("    constant payload_bytes", f"    constant wide_glyphs : natural := {wide_count};\n    constant payload_bytes")
    rtl = re.sub(r'(constant mapping : .*? := x")[0-9a-fA-F]+', rf"\g<1>{identity.hex()}", rtl)
    rtl = re.sub(r'(constant wire_mapping : .*? := x")[0-9a-fA-F]+', rf"\g<1>{identity[::-1].hex()}", rtl)
    vhdl.write_text(rtl)
    sheet = font.ROOT / "lab8_restored/Terminal_Display.bdf"
    old = re.search(r"K15_([0-9A-F]{4})", sheet.read_text())
    assert old
    old_count = int(old[1], 16)
    sheet.write_text(sheet.read_text().replace(old[0], f"K15_{count:04X}").replace(f'"{old_count}"', f'"{count}"'))
    print(f"{wide_count} wide + {len(supported)} single SRAM glyphs, {len(image)} flash bytes, {identity.hex()}")


if __name__ == "__main__":
    main()
