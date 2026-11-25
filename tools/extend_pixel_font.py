#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build and verify the extended font from the published v1.1.0 font and pinned artwork."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import struct
import tarfile
import unicodedata as ucd
from xml.etree import ElementTree
import zipfile
import zlib

import generate_superface_font as font

BASE_COUNT = 7496
BASE_WIDE = 6844
CAPACITY = font.GLYPH_LIMIT - font.GLYPH_FIRST
INPUTS = {
    "unifont": "2bd4e4679757126f48e1bf2c1be40b09aa92162bfedda4683ce5fbc70a2a5972",
    "unihan": "b8f000df69de7828d21326a2ffea462b04bc7560022989f7cc704f10521ef3e0",
    "taiwan": "e97e29ed2aa222bbfc12c18a6d96f0270440b1d73f64366d9ad22d7fe9012408",
    "unicode_license": "e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96",
}
BASE_HASHES = {
    font.MAP_NAME: "fa474ce2216d13d42cab9638c2541ab0730aa31283ece0e7e1e0c7b6955eab95",
    font.FLASH_NAME: "f453aeb01d875ffd88e73822cb848d4dff87c6c1ca024dbf515460f7bb45fd0f",
    font.MANIFEST_NAME: "373f840cd48570c79eff9f8706ccb44e220cd27f63c57818d0ba72bc444f2314",
}
CATEGORIES = {
    "ASCII": "0020-007E",
    "Box Drawing, Block Elements and Braille": "2500-259F 2800-28FF",
    "Terminal games and interface": (
        "2190-21FF 2300-23FF 2400-243F 25A0-25FF 2600-263C 2640-2642 "
        "2654-266F 2672-269F 26A0-26A1 26AA-26AF 26BD-26BE 26D4-26D4 "
        "2700-27BF 2B00-2B55 2B60-2B8F 2B95-2B95 1D100-1D110 1D11E-1D122 "
        "1D12A-1D12F 1D15D-1D164 1F0A0-1F0DF 1FB00-1FBFF"
    ),
    "Mathematical and scientific notation": (
        "2070-209F 2100-218F 2200-22FF 27C0-27EF 27F0-27FF 2900-2AFF "
        "1D538-1D56B 1D7D8-1D7E1"
    ),
    "Currency": "00A2-00A5 20A0-20CF",
    "Latin and IPA": "00A0-02FF 1D00-1DBF 1E00-1EFF 2C60-2C7F A720-A7FF AB30-AB6F",
    "Greek": "0370-03FF 1F00-1FFF",
    "Cyrillic": "0400-052F A640-A69F",
    "Kana and Bopomofo": "3040-30FF 3100-312F 31A0-31BF 31F0-31FF FF66-FF9D",
    "Punctuation and other typography": "2000-206F 2440-24FF 3000-303F FE10-FE1F FE30-FE6F FF00-FF65 FF9E-FFEF",
}
REPERTOIRE_CSV = "extended_repertoire.csv"
COVERAGE_NAME = "extended_coverage.md"
# Hand-tuned eight-column adaptations of the four Fusion Pixel suit silhouettes.
# Use the same silhouette for each solid and outlined pair.
SUITS = (
    (0x2660, 0x2664, (0x18, 0x3C, 0x7E, 0xFF, 0xFF, 0xE7, 0x42, 0x18, 0x18, 0x3C)),
    (0x2665, 0x2661, (0x66, 0xFF, 0xFF, 0xFF, 0xFF, 0x7E, 0x7E, 0x3C, 0x3C, 0x18)),
    (0x2666, 0x2662, (0x18, 0x18, 0x3C, 0x7E, 0xFF, 0xFF, 0x7E, 0x3C, 0x18, 0x18)),
    (0x2663, 0x2667, (0x18, 0x3C, 0x3C, 0x18, 0x7E, 0xFF, 0xE7, 0x66, 0x18, 0x3C)),
)


def pinned(path, digest):
    data = path.read_bytes()
    font.require(font.sha256(data) == digest, f"{path}: pinned SHA-256 mismatch")
    return data


def intervals(spec):
    for span in spec.split():
        lo, hi = (int(n, 16) for n in span.split("-"))
        yield from range(lo, hi + 1)


def category_map():
    result = {}
    for category, spec in CATEGORIES.items():
        for cp in intervals(spec):
            result.setdefault(cp, category)
    return result


def width(cp):
    scalar = chr(cp)
    if ucd.category(scalar)[0] not in "LNPS":
        return 0
    return 2 if ucd.east_asian_width(scalar) in ("W", "F") else 1


def bdf_records(bitmap):
    records = {}
    for raw in bitmap.decode("ascii").split("\nSTARTCHAR ")[1:]:
        lines = raw.splitlines()
        cp = int(font.bdf_field(lines, "ENCODING"))
        font.require(cp not in records, f"duplicate Fusion Pixel encoding U+{cp:04X}")
        records[cp] = lines
    return records


def fusion_pixels(record):
    w, h, x, y = map(int, font.bdf_field(record, "BBX").split())
    advance, dy = map(int, font.bdf_field(record, "DWIDTH").split())
    top = font.ASCENT - y - h
    font.require(advance in (6, 12) and dy == 0 and 0 <= w <= advance and 0 <= h <= 12,
                 "invalid Fusion Pixel glyph dimensions")
    encoded = record[record.index("BITMAP") + 1:record.index("ENDCHAR")]
    font.require(len(encoded) == h, "invalid Fusion Pixel bitmap height")
    pixels = set()
    for row, data in enumerate(encoded, top):
        size = 8 * ((w + 7) // 8)
        padding = size - w
        mask = int(data or "0", 16)
        font.require(len(data) * 4 == size and mask % (1 << padding) == 0,
                     "invalid Fusion Pixel bitmap row")
        pixels.update((x + col, row) for col in range(w) if mask & (1 << (size - 1 - col)))
    font.require(all(0 <= col < advance and 0 <= row < 12 for col, row in pixels),
                 "Fusion Pixel ink extends outside its cell")
    return pixels, advance


def fit_axis(value, start, span, size):
    """Resample the ink extent onto a smaller integer grid, keeping endpoints."""
    return ((value - start) * (size - 1) + (span - 1) // 2) // (span - 1)


def fusion_slot(record, cells):
    pixels, advance = fusion_pixels(record)
    if not pixels:
        return None
    if cells == 2:
        shift = (12 - advance) // 2
        return encode({(x + shift, y) for x, y in pixels}, 12)
    if advance == 6:
        return encode({(x + 1, y + 2) for x, y in pixels}, 8)
    left = min(x for x, _ in pixels)
    right = max(x for x, _ in pixels)
    span = right - left + 1
    if span <= 8:
        shift = min(left, max(0, right - 7, 2))
        return encode({(x - shift, y + 2) for x, y in pixels}, 8)
    # Merge neighboring ink columns on the integer grid, with no gray pixels.
    return encode({(fit_axis(x, left, span, 8), y + 2) for x, y in pixels}, 8)


def encode(pixels, bits):
    rows = [0] * 16
    for x, y in pixels:
        rows[y] |= 1 << (bits - 1 - x)
    return tuple(rows)


def suit_slots():
    slots = {}
    for solid, outline, artwork in SUITS:
        rows = (0, 0, 0, *artwork, 0, 0, 0)
        slots[solid] = tuple(rows)
        slots[outline] = (0, *(row & ~(row << 1 & row >> 1 & above & below)
                               for above, row, below in zip(rows, rows[1:], rows[2:])), 0)
    return slots


def unifont_art(path):
    pinned(path, INPUTS["unifont"])
    prefix = "unifont-16.0.04/"
    with tarfile.open(path) as archive:
        def read(member):
            with archive.extractfile(prefix + member) as handle:
                return handle.read()
        notices = {
            name: read(name) for name in ("COPYING", "OFL-1.1.txt", "README")
        }
        # Preserve the copyright string embedded by the upstream bitmap build.
        makefile = read("font/Makefile").replace(b"\\\n", b"")
        copyright_notice = re.search(rb'^COPYRIGHT = "([^"]+)"$', makefile, re.MULTILINE)
        font.require(copyright_notice is not None, "missing Unifont bitmap copyright notice")
        notices["COPYRIGHT.txt"] = copyright_notice[1] + b"\n"
        records = {}
        for line in read("font/precompiled/unifont_all-16.0.04.hex").splitlines():
            scalar, bitmap = line.split(b":")
            cp = int(scalar, 16)
            font.require(cp not in records, f"duplicate Unifont encoding U+{cp:04X}")
            records[cp] = bytes.fromhex(bitmap.decode("ascii"))
    return records, {"LICENSES/unifont/" + k: v for k, v in notices.items()}


def unifont_slot(raw, cells):
    if not raw or not any(raw):
        return None
    font.require(len(raw) in (16, 32), "invalid Unifont glyph size")
    if len(raw) == 16 and cells == 1:
        return tuple(raw)
    # Adapt the native bitmap as binary ink; retain its edges and a clear baseline.
    stride = len(raw) // 16
    bits = 8 if cells == 1 else 12
    pixels = set()
    for y in range(16):
        row = int.from_bytes(raw[y * stride:(y + 1) * stride], "big")
        for x in range(stride * 8):
            if row & (1 << (stride * 8 - 1 - x)):
                px = fit_axis(x, 0, stride * 8, bits)
                py = y if cells == 1 else fit_axis(y, 0, 16, 12)
                pixels.add((px, py))
    return encode(pixels, bits)


def taiwan_points(path):
    pinned(path, INPUTS["taiwan"])
    with zipfile.ZipFile(path) as archive:
        sheet = ElementTree.fromstring(archive.read("content.xml"))
    points = []
    for row in sheet.findall(".//{*}table-row"):
        fields = ["".join(cell.itertext()) for cell in row]
        if len(fields) > 3 and re.fullmatch(r"A\d{5}", fields[1]):
            cp = int(fields[2], 16)
            # Row A02149 lists U+6C69 but prints U+6C68. Use the character column.
            if fields[1] == "A02149" and (cp, fields[3]) == (0x6C69, chr(0x6C68)):
                cp = 0x6C68
            font.require(fields[3] == chr(cp), "Taiwan character/code mismatch")
            points.append(cp)
    font.require(len(points) == len(set(points)) == 4808, "unexpected Taiwan repertoire")
    return points


def unihan_points(path):
    pinned(path, INPUTS["unihan"])
    standard, big5 = {}, {}
    with zipfile.ZipFile(path) as archive:
        for line in archive.read("Unihan_OtherMappings.txt").decode().splitlines():
            if not line.startswith("U+"):
                continue
            scalar, field, value = line.split("\t")
            if field == "kTGH" and value.startswith("2013:"):
                standard[int(value[5:])] = int(scalar[2:], 16)
            elif field == "kBigFive" and re.fullmatch(r"[0-9A-F]{4}", value):
                big5[int(value, 16)] = int(scalar[2:], 16)
    font.require(set(standard) == set(range(1, 8106)), "incomplete 2013 Chinese standard")
    return standard, big5


def baseline(path):
    raw, image, manifest = (pinned(path / name, BASE_HASHES[name])
                            for name in (font.MAP_NAME, font.FLASH_NAME, font.MANIFEST_NAME))
    entries = {int(row["unicode"][2:], 16): int(row["glyph_id"], 16)
               for row in csv.DictReader(raw.decode().splitlines())}
    font.require(len(entries) == 95 + BASE_COUNT, "invalid v1.1.0 mapping")
    payload = font.read_flash(image, BASE_COUNT, font.mapping_id(raw))
    return entries, payload, json.loads(manifest)


def validate(entries, old_entries, payload, old_payload, narrow_limit, mapping, image, mif):
    font.require(len(entries) == 95 + CAPACITY and len(set(entries.values())) == len(entries),
                 "duplicate or missing glyph mapping")
    font.require(all(entries.get(cp) == glyph for cp, glyph in old_entries.items()) and
                 payload.startswith(old_payload), "v1.1.0 mapping or artwork changed")
    ids = sorted(glyph for glyph in entries.values() if glyph >= font.GLYPH_FIRST)
    font.require(ids == list(range(font.GLYPH_FIRST, font.GLYPH_LIMIT)), "invalid SRAM ID range")
    font.require(len(payload) == 2 * font.SRAM_WORDS and len(image) <= font.FLASH_PARTITION_BYTES,
                 "font exceeds SRAM or Flash capacity")
    for cp, glyph in entries.items():
        if cp in old_entries:
            continue
        expected = 1 if glyph < narrow_limit else 2
        offset = (glyph - font.GLYPH_FIRST) * 32
        rows = struct.unpack_from("<16H", payload, offset)
        font.require(width(cp) == expected and any(rows) and
                     max(rows) < (256 if expected == 1 else 4096) and
                     (expected == 1 or not any(rows[12:])), f"invalid glyph U+{cp:04X}")
    font.require(font.read_flash(image, CAPACITY, font.mapping_id(mapping)) == payload,
                 "Flash round trip failed")
    font.require(b"".join(struct.pack("<H", word) for word in font.decode_mif(mif)) == payload,
                 "SRAM MIF round trip failed")
    for lo, hi in ((0x2654, 0x2667), (0x2680, 0x2685)):
        masks = set()
        for cp in range(lo, hi + 1):
            glyph = entries[cp]
            offset = (glyph - font.GLYPH_FIRST) * 32
            font.require(glyph < narrow_limit, f"game symbol U+{cp:04X} must occupy one cell")
            masks.add(bytes(payload[offset:offset + 32]))
        font.require(len(masks) == hi - lo + 1, "game silhouettes must be distinct")


def emit(path, data, verify):
    if verify:
        font.require(path.read_bytes() == data, f"{path}: generated output differs")
    elif not path.exists() or path.read_bytes() != data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def write_rtl(count, narrow_limit, identity, verify):
    project = font.ROOT / "lab8_restored"
    package = project / "Font_CRC.vhd"
    rtl = package.read_text()
    for name, count_value in (("glyphs", count), ("narrow_end", narrow_limit - font.GLYPH_FIRST)):
        rtl, matches = re.subn(rf"(constant {name} : natural := )\d+;", rf"\g<1>{count_value};", rtl)
        font.require(matches == 1, f"cannot find {name} in Font_CRC.vhd")
    for name, digest in (("mapping", identity.hex()), ("wire_mapping", identity[::-1].hex())):
        rtl, matches = re.subn(rf'(constant {name} : .*? := x")[0-9a-fA-F]{{32}}', rf"\g<1>{digest}", rtl)
        font.require(matches == 1, f"cannot find {name} in Font_CRC.vhd")
    emit(package, rtl.encode(), verify)
    for name in ("Terminal_Display", "Xga_Display"):
        schematic = project / (name + ".bdf")
        raw = schematic.read_text()
        previous = re.search(r"K15_([0-9A-F]{4})", raw)
        font.require(previous is not None, f"{name}: no declared font count bus")
        old_count = int(previous[1], 16)
        raw = raw.replace(previous[0], f"K15_{count:04X}").replace(
            f'(parameter "LPM_CVALUE" "{old_count}"', f'(parameter "LPM_CVALUE" "{count}"')
        emit(schematic, raw.encode(), verify)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="verified v1.1.0 assets/fonts directory")
    parser.add_argument("--fusion", type=Path, required=True)
    for name in INPUTS:
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    font.require(ucd.unidata_version == "16.0.0", "use Python with Unicode 16.0.0")
    font.verify_ascii()
    old_entries, old_payload, manifest = baseline(args.baseline)
    entries = dict(old_entries)
    hans_bitmap, notices = font.load_source(args.fusion)
    with zipfile.ZipFile(args.fusion) as archive:
        hant_bitmap = archive.read("fusion-pixel-12px-monospaced-zh_hant.bdf")
    hans = bdf_records(hans_bitmap)
    hant = bdf_records(hant_bitmap)
    fallback, fallback_notices = unifont_art(args.unifont)
    notices.update(fallback_notices)
    notices["LICENSES/unicode/LICENSE.txt"] = pinned(args.unicode_license, INPUTS["unicode_license"])

    categories = category_map()
    # U+3007 is a Han numeral and belongs with the Han repertoire.
    categories.pop(0x3007)
    for cp in range(0x3031, 0x3036):
        categories.pop(cp)  # Vertical kana iteration marks span stacked rows.
    categories.pop(0xFFA0)  # Invisible halfwidth Hangul filler.
    coverage_old = Counter(categories.get(cp, "Han") for cp in old_entries)
    additions = {}
    unavailable = []
    suits = suit_slots()
    for cp in sorted(categories.keys() - entries.keys()):
        cells = width(cp)
        if not cells:
            continue
        source = "Fusion Pixel zh_Hans"
        if cp in suits:
            rows = suits[cp]
            source = "Fusion Pixel zh_Hans (adapted suit)"
        else:
            rows = fusion_slot(hans[cp], cells) if cp in hans else None
        if rows is None:
            rows = unifont_slot(fallback.get(cp), cells)
            source = "GNU Unifont"
        if rows is not None:
            additions[cp] = (cells, rows, categories[cp], source, "Terminal and language selection")
        else:
            unavailable.append(f"U+{cp:04X}")

    taiwan = taiwan_points(args.taiwan)
    standard, big5 = unihan_points(args.unihan)
    tiers = (
        ("GB 2312 remaining Han", (cp for cp in font.gb2312_levels()[1] if cp not in entries), hans, "zh_Hans"),
        ("GB 8105 level 1", (standard[n] for n in range(1, 3501)), hans, "zh_Hans"),
        ("Taiwan MOE common characters", iter(taiwan), hant, "zh_Hant"),
        ("GB 8105 level 2", (standard[n] for n in range(3501, 6501)), hans, "zh_Hans"),
        ("Big5 frequent tier", (big5[n] for n in sorted(big5) if 0xA440 <= n <= 0xC67E), hant, "zh_Hant"),
        ("GB 8105 level 3", (standard[n] for n in range(6501, 8106)), hans, "zh_Hans"),
        ("Big5 secondary tier", (big5[n] for n in sorted(big5) if 0xC940 <= n <= 0xF9D5), hant, "zh_Hant"),
    )
    for tier, points, records, flavor in tiers:
        for cp in points:
            if len(additions) == CAPACITY - BASE_COUNT:
                break
            if cp in entries or cp in additions or cp not in records:
                continue
            rows = fusion_slot(records[cp], 2)
            if rows is not None:
                additions[cp] = (2, rows, "Han", "Fusion Pixel " + flavor, tier)

    payload = bytearray(old_payload)
    provenance = ["unicode,glyph_id,width,category,artwork,repertoire\n"]
    # Dict insertion order retains the explicitly ranked Han tiers.
    ordered = sorted(additions.items(), key=lambda item: item[1][0])
    for glyph, (cp, (cells, rows, category, artwork, tier)) in enumerate(ordered, font.GLYPH_FIRST + BASE_COUNT):
        entries[cp] = glyph
        payload.extend(struct.pack("<16H", *rows))
        provenance.append(f'U+{cp:06X},0x{glyph:04X},{cells},"{category}","{artwork}","{tier}"\n')

    added_narrow = sum(art[0] == 1 for art in additions.values())
    narrow_limit = font.GLYPH_FIRST + BASE_COUNT + added_narrow
    narrow_count = narrow_limit - (font.GLYPH_FIRST + BASE_WIDE)
    wide_count = CAPACITY - narrow_count
    mapping = ("unicode,glyph_id\n" +
               "".join(f"U+{cp:06X},0x{entries[cp]:04X}\n" for cp in sorted(entries))).encode()
    identity = font.mapping_id(mapping)
    image = font.build_flash(payload, CAPACITY, identity)
    mif = font.build_mif(payload)
    validate(entries, old_entries, payload, old_payload, narrow_limit, mapping, image, mif)

    coverage_new = Counter(art[2] for art in additions.values())
    art_sources = Counter(art[3] for art in additions.values())
    han_tiers = Counter(art[4] for art in additions.values() if art[2] == "Han")
    coverage = ["# Extended pixel font coverage\n\n",
                "| Category | v1.1.0 | Added | Total |\n| --- | ---: | ---: | ---: |\n"]
    for category in (*CATEGORIES, "Han"):
        old, added = coverage_old[category], coverage_new[category]
        coverage.append(f"| {category} | {old:,} | {added:,} | {old + added:,} |\n")
    coverage.append(f"| **Total** | **{len(old_entries):,}** | **{len(additions):,}** | **{len(entries):,}** |\n")
    coverage.append("\nHan additions in selection order\n\n")
    coverage.extend(f"- {tier} ({count:,})\n" for tier, count in han_tiers.items())
    coverage.append("\nCounts are individual mapped Unicode scalars. Shaping, combining sequences and bidirectional layout are outside this repertoire.\n")

    old_missing = (args.baseline / font.MISSING_NAME).read_bytes()
    font.require(font.sha256(old_missing) == manifest["files"][font.MISSING_NAME]["sha256"],
                 "v1.1.0 missing report checksum mismatch")
    missing_header, *missing_records = old_missing.decode().splitlines()
    missing_records = [line for line in missing_records if int(line.split(",")[0][2:], 16) not in entries]
    missing_report = ("\n".join([missing_header, *missing_records]) + "\n").encode()
    manifest["repertoire"]["missing"].update(han_total=len(missing_records), level_2=len(missing_records))
    manifest["repertoire"]["extended_pixel_font"] = {
        "coverage": {name: {"existing": coverage_old[name], "added": coverage_new[name]}
                     for name in (*CATEGORIES, "Han")},
        "han_selection": dict(han_tiers),
        "artwork_sources": dict(art_sources),
        "added_glyphs": len(additions),
        "provenance": REPERTOIRE_CSV,
        "eligible_non_han_without_artwork": unavailable,
        "baseline_commit": "e2df6867008e763adefd36874a7e48b0cd87623e",
        "baseline_payload_sha256": font.sha256(old_payload),
        "pinned_inputs_sha256": INPUTS,
        "unicode_version": ucd.unidata_version,
    }
    manifest["mapping"].update(sha256=font.sha256(mapping), mapping_id_hex=identity.hex(),
                               sram_count=CAPACITY, last_sram_id=font.GLYPH_LIMIT - 1,
                               total_scalar_count=len(entries), narrow_id_limit=narrow_limit,
                               wide_count=wide_count, narrow_count=narrow_count)
    manifest["sram"].update(end_word_exclusive=len(payload) // 2, allocated_bytes=len(payload),
                            free_bytes=0, useful_bytes=18 * wide_count + 16 * narrow_count,
                            padding_bytes=14 * wide_count + 16 * narrow_count)
    manifest["flash"].update(end_byte_exclusive=len(image), image_bytes=len(image),
                             payload_bytes=len(payload),
                             header_crc32_hex=f"{zlib.crc32(image[:60]):08x}",
                             payload_crc32_hex=f"{zlib.crc32(payload):08x}",
                             free_partition_bytes=font.FLASH_PARTITION_BYTES - len(image),
                             free_device_bytes_by_capacity={str(x): x - len(image) for x in font.FLASH_CAPACITIES})
    outputs = {font.MAP_NAME: mapping, font.MIF_NAME: mif, font.FLASH_NAME: image,
               font.MISSING_NAME: missing_report, REPERTOIRE_CSV: "".join(provenance).encode(),
               COVERAGE_NAME: "".join(coverage).encode(), **notices}
    for name, data in outputs.items():
        manifest["files"][name] = {"bytes": len(data), "sha256": font.sha256(data)}
        emit(font.ASSETS / name, data, args.verify)
    emit(font.ASSETS / font.MANIFEST_NAME, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
         args.verify)
    write_rtl(CAPACITY, narrow_limit, identity, args.verify)
    print(f"{len(entries)} mapped scalars; {narrow_count} narrow and {wide_count} wide SRAM glyphs; "
          f"{len(payload)} SRAM bytes; mapping {identity.hex()}")


if __name__ == "__main__":
    main()
