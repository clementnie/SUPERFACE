#!/usr/bin/env python3
"""Generate or verify SUPERFACE's font assets from the pinned native bitmap release."""

import argparse
import hashlib
import json
import re
import struct
import sys
import tempfile
import unicodedata
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "fonts"
ASCII_MIF = ROOT / "lab8_restored" / "ascii_8x16.mif"
ASCII_SHA256 = "dac189ba1fe8eb46c94341b90f4e7a2f6b3e9e8d61c073b05d75b6b103b1d554"

RELEASE = "2026.11.10"
COMMIT = "a38a5de9cc099ce28da3cab9f9411aa83cc7a3e9"
UPSTREAM = "https://github.com/TakWolf/fusion-pixel-font"
ZIP_NAME = f"fusion-pixel-font-12px-monospaced-bdf-v{RELEASE}.zip"
ZIP_URL = f"{UPSTREAM}/releases/download/{RELEASE}/{ZIP_NAME}"
ZIP_SHA256 = "bbf8efa39f165dee5e52ed1c2ccc21f7d7d32dd6e536190cba55065220b2c0a5"
BDF_MEMBER = "fusion-pixel-12px-monospaced-zh_hans.bdf"
BDF_SHA256 = "fce624869a7ddc228b45173d8a9f9a3a7a7f3e86ad8008d23d5611218d608f08"
LICENSE_MEMBERS = {
    "OFL.txt": "LICENSES/fusion-pixel/OFL.txt",
    "LICENSES/ark-pixel/OFL.txt": "LICENSES/ark-pixel/OFL.txt",
    "LICENSES/cubic-11/OFL.txt": "LICENSES/cubic-11/OFL.txt",
    "LICENSES/galmuri/LICENSE.txt": "LICENSES/galmuri/LICENSE.txt",
}

FORMAT_VERSION = 1
MAGIC = b"SFFONT1\0"
GLYPH_FIRST = 0x8000
GLYPH_LIMIT = 0xC000
SIZE = 12
ASCENT = 10
STRIDE_WORDS = 16
SRAM_WORDS = 0x40000
FLASH_HEADER_BYTES = 64
FLASH_PARTITION_BYTES = 0x90000
FLASH_CAPACITIES = (0x100000, 0x400000)
SAMPLES = "一二三十民主自由云南人民你好世界"

REPERTOIRE_NAME = "required_zh_hans.txt"
MAP_NAME = "glyph_map.csv"
MIF_NAME = "chinese_sram.mif"
FLASH_NAME = "superface_font.bin"
MANIFEST_NAME = "font_manifest.json"
SHEET_NAME = "font_contact_sheet.svg"
MISSING_NAME = "missing_zh_hans.csv"

Bitmap = tuple[tuple[bool, ...], ...]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def gb2312_levels() -> tuple[list[int], list[int]]:
    # EUC forms for Han rows 16–55 and 56–87. D7FA–D7FE are unassigned.
    level_one = sorted(
        ord(bytes((lead, trail)).decode("gb2312"))
        for lead in range(0xB0, 0xD8)
        for trail in range(0xA1, 0xFA if lead == 0xD7 else 0xFF)
    )
    level_two = sorted(
        ord(bytes((lead, trail)).decode("gb2312"))
        for lead in range(0xD8, 0xF8)
        for trail in range(0xA1, 0xFF)
    )
    require((len(level_one), len(level_two), len(set(level_one + level_two))) == (3755, 3008, 6763),
            "GB/T 2312 codec does not yield the expected unique Han scalars")
    return level_one, level_two


def read_repertoire(raw: bytes) -> list[int]:
    lines = raw.decode("ascii").split("\n")
    require(lines[-1] == "", "repertoire must end with LF")
    points = []
    seen = set()
    for line_number, line in enumerate(lines[:-1], 1):
        require(re.fullmatch(r"U\+[0-9A-F]{6}", line) is not None,
                f"repertoire line {line_number}: expected U+ followed by six uppercase hex digits")
        point = int(line[2:], 16)
        require(point <= 0x10FFFF and unicodedata.name(chr(point), "").startswith("CJK UNIFIED IDEOGRAPH-"),
                f"repertoire line {line_number}: {line} is outside the unified Han repertoire")
        require(point not in seen, f"repertoire line {line_number}: duplicate {line}")
        seen.add(point)
        points.append(point)
    require(1 <= len(points) <= GLYPH_LIMIT - GLYPH_FIRST, "repertoire must contain 1–16,384 glyphs")
    return sorted(points)


def load_source(path: Path) -> tuple[bytes, dict[str, bytes]]:
    with path.open("rb") as source:
        require(hashlib.file_digest(source, "sha256").hexdigest() == ZIP_SHA256,
                f"{path}: SHA-256 does not match pinned release {ZIP_NAME}")
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            bitmap = archive.read(BDF_MEMBER)
            notices = {target: archive.read(name) for name, target in LICENSE_MEMBERS.items()}
    require(sha256(bitmap) == BDF_SHA256, "unexpected upstream zh_hans bitmap member")
    return bitmap, notices


def bdf_field(record: list[str], key: str) -> str:
    values = [line[len(key) + 1:] for line in record if line.startswith(key + " ")]
    require(len(values) == 1, f"expected exactly one BDF {key} field")
    return values[0]


def bdf_pixels(record: list[str]) -> Bitmap:
    require(bdf_field(record, "DWIDTH") == "12 0", "expected a full-width glyph")
    width, height, x, y = map(int, bdf_field(record, "BBX").split())
    top = ASCENT - (y + height)
    require(0 <= x < x + width <= SIZE and 0 <= top < top + height <= SIZE,
            "BDF bounding box does not fit the native 12×12 cell")
    encoded_rows = record[record.index("BITMAP") + 1:record.index("ENDCHAR")]
    require(len(encoded_rows) == height, "wrong BDF bitmap row count")
    row_bytes = (width + 7) // 8
    canvas = [[False] * SIZE for _ in range(SIZE)]
    for row, encoded in enumerate(encoded_rows, top):
        require(re.fullmatch(rf"[0-9A-Fa-f]{{{2 * row_bytes}}}", encoded) is not None,
                "wrong BDF bitmap row width")
        word = int(encoded, 16)
        require(word & ((1 << (8 * row_bytes - width)) - 1) == 0, "nonzero BDF row padding")
        for bit in range(width):
            canvas[row][x + bit] = bool(word & (1 << (8 * row_bytes - 1 - bit)))
    return tuple(tuple(row) for row in canvas)


def read_bdf(bitmap: bytes, points: list[int]) -> dict[int, Bitmap]:
    metadata, *records = bitmap.decode("ascii").split("\nSTARTCHAR ")
    expected = {
        "FAMILY_NAME": '"Fusion Pixel 12px Mono zh_Hans"',
        "FONTBOUNDINGBOX": "12 12 0 -2",
        "PIXEL_SIZE": "12",
        "FONT_ASCENT": "10",
        "FONT_DESCENT": "2",
        "FONT_VERSION": f'"{RELEASE}"',
        "CHARSET_REGISTRY": '"ISO10646"',
    }
    headers = metadata.splitlines()
    for field, value in expected.items():
        require(bdf_field(headers, field) == value, f"incompatible upstream BDF {field}")
    require(len(records) == int(bdf_field(headers, "CHARS")), "BDF glyph count mismatch")
    wanted = set(points)
    glyphs = {}
    for record in records:
        lines = record.splitlines()
        point = int(bdf_field(lines, "ENCODING"))
        if point in wanted:
            require(point not in glyphs, f"duplicate BDF encoding U+{point:06X}")
            try:
                glyphs[point] = bdf_pixels(lines)
            except ValueError as exc:
                raise ValueError(f"U+{point:06X} {chr(point)}: {exc}") from exc
    return glyphs


def verify_ascii() -> None:
    raw = ASCII_MIF.read_bytes()
    require(sha256(raw) == ASCII_SHA256, "baseline ASCII font SHA-256 mismatch")
    mif = re.sub(r"%.*?%", "", raw.decode("ascii"), flags=re.S)
    for field in ("DEPTH = 2048;", "WIDTH = 8;", "ADDRESS_RADIX = HEX;", "DATA_RADIX = BIN;"):
        require(field in mif, f"ASCII ROM is missing {field}")
    records = re.findall(r"^\s*([0-9A-F]{3})\s*:\s*([01]{8})\s*;", mif, re.M)
    require([int(address, 16) for address, _ in records] == list(range(2048)),
            "ASCII ROM must have explicit addresses 0–2047")
    rows = [int(word, 2) for _, word in records]
    require(not any(rows[0x20 * 16:0x21 * 16]), "ASCII space is not blank")
    require(any(rows[0x3F * 16:0x40 * 16]), "ASCII fallback is blank")


def make_mapping(points: list[int]) -> bytes:
    rows = [(point, point) for point in range(0x20, 0x7F)]
    rows.extend((point, glyph_id) for glyph_id, point in enumerate(points, GLYPH_FIRST))
    text = "unicode,glyph_id\n" + "".join(f"U+{point:06X},0x{glyph_id:04X}\n" for point, glyph_id in rows)
    return text.encode("ascii")


def mapping_id(mapping: bytes) -> bytes:
    digest = hashlib.sha256(mapping).digest()[:16]
    require(any(digest), "all-zero mapping ID is reserved for ASCII-only operation")
    return digest


def pack_sram(points: list[int], glyphs: dict[int, Bitmap]) -> bytes:
    payload = bytearray()
    for point in points:
        rows = [int("".join("1" if pixel else "0" for pixel in row), 2) for row in glyphs[point]]
        payload.extend(struct.pack("<16H", *rows, 0, 0, 0, 0))
    require(0 < len(payload) <= SRAM_WORDS * 2, "SRAM word address exceeds 18-bit capacity")
    require(FLASH_HEADER_BYTES + len(payload) <= min(FLASH_PARTITION_BYTES, *FLASH_CAPACITIES),
            "Flash image exceeds the font allocation")
    return bytes(payload)


def build_flash(payload: bytes, count: int, identity: bytes) -> bytes:
    header = struct.pack("<8sHHHHI16sI20x", MAGIC, FORMAT_VERSION, FLASH_HEADER_BYTES,
                         count, 0, len(payload), identity, zlib.crc32(payload))
    return header + struct.pack("<I", zlib.crc32(header)) + payload


def build_mif(payload: bytes) -> bytes:
    out = [
        f"DEPTH = {SRAM_WORDS};", "WIDTH = 16;", "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;", "CONTENT BEGIN",
    ]
    for address, (word,) in enumerate(struct.iter_unpack("<H", payload)):
        out.append(f"    {address:05X} : {word:04X};")
    used_words = len(payload) // 2
    if used_words < SRAM_WORDS:
        out.append(f"    [{used_words:05X}..{SRAM_WORDS - 1:05X}] : 0000;")
    return ("\n".join(out) + "\nEND;\n").encode("ascii")


def decode_mif(raw: bytes) -> list[int]:
    lines = raw.decode("ascii").splitlines()
    require(lines[:5] == ["DEPTH = 262144;", "WIDTH = 16;", "ADDRESS_RADIX = HEX;",
                          "DATA_RADIX = HEX;", "CONTENT BEGIN"] and lines[-1:] == ["END;"],
            "invalid SRAM MIF geometry or framing")
    words = []
    for line in lines[5:-1]:
        entry = re.fullmatch(r"\s*([0-9A-F]{5}) : ([0-9A-F]{4});", line)
        if entry:
            address, value = (int(item, 16) for item in entry.groups())
            require(address == len(words) < SRAM_WORDS, "noncontiguous or out-of-range MIF address")
            words.append(value)
        else:
            tail = re.fullmatch(r"\s*\[([0-9A-F]{5})\.\.3FFFF\] : 0000;", line)
            require(tail is not None and int(tail[1], 16) == len(words) < SRAM_WORDS,
                    "invalid or noncontiguous MIF tail")
            words.extend([0] * (SRAM_WORDS - len(words)))
    require(len(words) == SRAM_WORDS, "SRAM MIF does not cover the address space")
    return words


def decode_glyph(words: list[int], glyph_id: int) -> Bitmap:
    slot = (glyph_id - GLYPH_FIRST) * STRIDE_WORDS
    return tuple(tuple(bool(word & (1 << (11 - x))) for x in range(SIZE))
                 for word in words[slot:slot + SIZE])


def build_sheet(words: list[int], ids: dict[int, int]) -> bytes:
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="992" height="340" viewBox="0 0 992 340">',
        '<rect width="992" height="340" fill="#f2f4f7"/>',
        '<text x="20" y="32" font-family="sans-serif" font-weight="bold" font-size="20">'
        'SUPERFACE Chinese glyphs decoded from the SRAM image</text>',
        '<g text-anchor="middle" font-family="monospace" font-size="12">',
    ]
    scale = 6
    for index, char in enumerate(SAMPLES):
        point = ord(char)
        glyph_id = ids.get(point)
        x, y = 20 + (index % 8) * 120, 48 + (index // 8) * 140
        out.append(f'<rect x="{x}" y="{y}" width="112" height="132" rx="5" fill="white"/>')
        label = "Absent" if glyph_id is None else f"ID 0x{glyph_id:04X}"
        if glyph_id is not None:
            out.append(f'<rect x="{x+20}" y="{y+10}" width="72" height="72" fill="#e5eaf0"/>')
            for row, pixels in enumerate(decode_glyph(words, glyph_id)):
                for col, on in enumerate(pixels):
                    if on:
                        out.append(f'<rect x="{x+20+scale*col}" y="{y+10+scale*row}" '
                                   f'width="{scale}" height="{scale}" fill="#15263a"/>')
        out.extend([
            f'<text x="{x+56}" y="{y+101}">U+{point:04X}</text>',
            f'<text x="{x+56}" y="{y+119}">{label}</text>',
        ])
    return ("\n".join(out + ["</g>", "</svg>"]) + "\n").encode("ascii")


def read_flash(raw: bytes, count: int, identity: bytes) -> bytes:
    # Parse byte offsets independently of the writer's struct layout.
    def number(start: int, size: int) -> int:
        return int.from_bytes(raw[start:start + size], "little")

    require(len(raw) >= 64 and raw[:8] == b"SFFONT1\0", "invalid Flash magic or truncated header")
    require(number(8, 2) == 1 and number(10, 2) == 64, "invalid Flash version or header size")
    require(number(12, 2) == count and not any(raw[14:16] + raw[40:60]), "invalid Flash count or reserved fields")
    require(raw[20:36] == identity, "Flash mapping ID differs from canonical CSV")
    require(number(60, 4) == zlib.crc32(raw[:60]), "Flash header CRC-32 mismatch")
    payload = raw[64:]
    require(number(16, 4) == len(payload) == 32 * count, "Flash payload length mismatch")
    require(number(36, 4) == zlib.crc32(payload), "Flash payload CRC-32 mismatch")
    require(len(raw) <= FLASH_PARTITION_BYTES, "Flash programmed range exceeds partition")
    return payload


def verify_payload(points: list[int], glyphs: dict[int, Bitmap], words: list[int], payload: bytes) -> None:
    used = STRIDE_WORDS * len(points)
    require(not any(words[used:]), "unallocated MIF words must be zero")
    for address, word in enumerate(words[:used]):
        require(word == int.from_bytes(payload[2 * address:2 * address + 2], "little"),
                f"MIF/Flash word mismatch at 0x{address:05X}")
        require(word <= 0xFFF and (address % STRIDE_WORDS < SIZE or word == 0),
                f"nonzero row or slot padding at SRAM word 0x{address:05X}")
    for index, point in enumerate(points):
        require(decode_glyph(words, GLYPH_FIRST + index) == glyphs[point],
                f"decoded SRAM bitmap differs from native source for U+{point:06X}")


def make_manifest(points: list[int], repertoire: bytes, missing: list[int],
                  outputs: dict[str, bytes], identity: bytes, payload: bytes) -> bytes:
    count = len(points)
    image_bytes = len(outputs[FLASH_NAME])
    manifest = {
        "format_version": FORMAT_VERSION,
        "source": {
            "repository": UPSTREAM, "commit": COMMIT, "release": RELEASE,
            "archive_url": ZIP_URL, "archive_sha256": ZIP_SHA256,
            "bitmap_member": BDF_MEMBER, "bitmap_sha256": BDF_SHA256,
            "variant": "12px-monospaced-zh_hans",
            "bitmap_license": "OFL-1.1", "redistributed_notices": LICENSE_MEMBERS,
        },
        "repertoire": {
            "input": REPERTOIRE_NAME, "sha256": sha256(repertoire),
            "policy": "All GB/T 2312-1980 Han Level 1 and all available Level 2 glyphs",
            "requested": {"han_total": 6763, "level_1": 3755, "level_2": 3008},
            "supported": {"han_total": count, "level_1": 3755, "level_2": count - 3755,
                          "listed_in": MAP_NAME},
            "missing": {"han_total": len(missing), "level_1": 0, "level_2": len(missing),
                        "report": MISSING_NAME, "fallback": "ASCII question mark plus same-color space for width two"},
            "missing_contact_sheet_examples": list(dict.fromkeys(char for char in SAMPLES if ord(char) not in points)),
        },
        "mapping": {
            "file": MAP_NAME, "ascii_count": 95, "chinese_count": count,
            "first_chinese_id": GLYPH_FIRST, "last_chinese_id": GLYPH_FIRST + count - 1,
            "continuation_id": 0xFFFF, "fallback_id": 0x003F, "space_id": 0x0020,
            "sha256": sha256(outputs[MAP_NAME]), "mapping_id_hex": identity.hex(),
        },
        "ascii_rom": {"file": "lab8_restored/ascii_8x16.mif", "sha256": ASCII_SHA256,
                      "depth": 2048, "word_bits": 8},
        "sram": {
            "file": MIF_NAME, "start_word": 0, "end_word_exclusive": count * STRIDE_WORDS,
            "depth_words": SRAM_WORDS, "word_bits": 16, "glyph_width": SIZE, "glyph_height": SIZE,
            "row_order": "top-to-bottom", "leftmost_pixel_bit": 11,
            "words_per_glyph": STRIDE_WORDS, "useful_bytes_per_glyph": 18, "slot_bytes": 32,
            "useful_bytes": 18 * count, "padding_bytes": 14 * count, "reserved_slot_bytes": 0,
            "allocated_bytes": len(payload), "free_bytes": 2 * SRAM_WORDS - len(payload),
        },
        "flash": {
            "file": FLASH_NAME, "start_byte": 0, "end_byte_exclusive": image_bytes,
            "partition_end_byte_exclusive": FLASH_PARTITION_BYTES,
            "free_partition_bytes": FLASH_PARTITION_BYTES - image_bytes,
            "free_device_bytes_by_capacity": {str(size): size - image_bytes for size in FLASH_CAPACITIES},
            "header_bytes": FLASH_HEADER_BYTES, "payload_offset": FLASH_HEADER_BYTES,
            "payload_bytes": len(payload), "payload_word_byte_order": "little",
            "image_bytes": image_bytes, "image_alignment_bytes": 0, "crc_algorithm": "CRC-32/ISO-HDLC",
            "payload_crc32_hex": f"{zlib.crc32(payload):08x}",
            "header_crc32_hex": f"{int.from_bytes(outputs[FLASH_NAME][60:64], 'little'):08x}",
        },
        "files": {path: {"bytes": len(data), "sha256": sha256(data)} for path, data in outputs.items()},
    }
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def run(mode: str, archive: Path, repertoire_path: Path, output: Path) -> None:
    verify_ascii()
    repertoire = repertoire_path.read_bytes()
    requested = read_repertoire(repertoire)
    level_one, level_two = gb2312_levels()
    require(requested == sorted(level_one + level_two),
            "production repertoire must request both complete GB/T 2312 Han levels")
    bitmap, notices = load_source(archive)
    glyphs = read_bdf(bitmap, requested)
    absent_required = [f"U+{point:06X} {chr(point)}" for point in level_one if point not in glyphs]
    require(not absent_required, "missing required Level 1 glyphs: " + ", ".join(absent_required))
    missing = [point for point in level_two if point not in glyphs]
    points = sorted(glyphs)
    missing_report = ("unicode,character,level\n" +
                      "".join(f"U+{point:06X},{chr(point)},2\n" for point in missing)).encode("utf-8")
    ids = {point: GLYPH_FIRST + index for index, point in enumerate(points)}
    expected_mapping = make_mapping(points)
    artifact_paths = (MAP_NAME, MIF_NAME, FLASH_NAME, SHEET_NAME, MISSING_NAME, *notices)

    if mode == "build":
        payload = pack_sram(points, glyphs)
        outputs = {
            MAP_NAME: expected_mapping,
            MISSING_NAME: missing_report,
            MIF_NAME: build_mif(payload),
            FLASH_NAME: build_flash(payload, len(points), mapping_id(expected_mapping)),
            **notices,
        }
        outputs[SHEET_NAME] = build_sheet(decode_mif(outputs[MIF_NAME]), ids)
    else:
        outputs = {path: (output / path).read_bytes() for path in artifact_paths}

    require(outputs[MAP_NAME] == expected_mapping, "noncanonical, duplicate or invalid Glyph ID mapping")
    require(outputs[MISSING_NAME] == missing_report, "missing-character report differs from source coverage")
    identity = mapping_id(outputs[MAP_NAME])
    payload = read_flash(outputs[FLASH_NAME], len(points), identity)
    words = decode_mif(outputs[MIF_NAME])
    verify_payload(points, glyphs, words, payload)
    require(outputs[SHEET_NAME] == build_sheet(words, ids), "contact sheet differs from decoded MIF")
    for name, data in notices.items():
        require(outputs[name] == data, f"{name}: license notice differs from upstream")
    manifest = make_manifest(points, repertoire, missing, outputs, identity, payload)

    if mode == "build":
        output.mkdir(parents=True, exist_ok=True)
        artifacts = {**outputs, MANIFEST_NAME: manifest}
        with tempfile.TemporaryDirectory(dir=output, prefix=".font-build-") as staging:
            for name, data in artifacts.items():
                temporary = Path(staging) / name
                temporary.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_bytes(data)
            # Publish the manifest last so it describes only a completed bundle.
            for name in artifacts:
                destination = output / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                (Path(staging) / name).replace(destination)
    else:
        require((output / MANIFEST_NAME).read_bytes() == manifest, "manifest differs from verified assets")

    print(f"{mode}: verified {len(points)} Chinese glyphs, {len(payload)} SRAM bytes, "
          f"{len(outputs[FLASH_NAME])} Flash bytes, mapping {identity.hex()}")
    print(f"Requested {len(requested)} glyphs. Absent Level 2 glyphs: {len(missing)} ({output / MISSING_NAME}).")
    absent_examples = [f"{char} (U+{ord(char):04X})" for char in dict.fromkeys(SAMPLES) if ord(char) not in ids]
    print("Absent contact-sheet examples: " + (", ".join(absent_examples) if absent_examples else "none"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("repertoire", help="print the requested GB/T 2312 Level 1 and 2 Han scalars")
    for mode in ("build", "check"):
        command = modes.add_parser(mode, help=f"{mode} generated font artifacts")
        command.add_argument("--archive", type=Path, required=True, help="pinned upstream release ZIP")
        command.add_argument("--repertoire", type=Path, default=ASSETS / REPERTOIRE_NAME)
        command.add_argument("--output", type=Path, default=ASSETS)
    args = parser.parse_args()
    try:
        if args.mode == "repertoire":
            level_one, level_two = gb2312_levels()
            sys.stdout.buffer.write("".join(f"U+{point:06X}\n" for point in sorted(level_one + level_two)).encode("ascii"))
        else:
            run(args.mode, args.archive, args.repertoire, args.output)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
