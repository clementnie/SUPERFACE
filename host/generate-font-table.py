"""Verify the canonical map against its manifest and emit the host lookup table."""

import hashlib
import json
import re
import sys
from pathlib import Path

mapping, manifest, output = map(Path, sys.argv[1:])
raw = mapping.read_bytes()
meta = json.loads(manifest.read_text())["mapping"]
digest = hashlib.sha256(raw).hexdigest()
if (digest != meta["sha256"] or digest[:32] != meta["mapping_id_hex"]
        or digest[:32] == "0" * 32):
    raise SystemExit("glyph map digest differs from its manifest")

lines = raw.split(b"\n")
if lines[0] != b"unicode,glyph_id" or lines[-1]:
    raise SystemExit("invalid canonical glyph CSV")
entries = []
for line in lines[1:-1]:
    match = re.fullmatch(rb"U\+([0-9A-F]{6}),0x([0-9A-F]{4})", line)
    if not match:
        raise SystemExit("invalid canonical glyph record")
    entries.append(tuple(int(value, 16) for value in match.groups()))

ascii_entries = [(code, code) for code in range(0x20, 0x7f)]
chinese = entries[len(ascii_entries):]
narrow_first = 0x8000 + meta["chinese_count"]
narrow_limit = meta.get("narrow_id_limit", 0x8000 + len(chinese))
if (entries[:len(ascii_entries)] != ascii_entries
        or len(ascii_entries) != meta["ascii_count"]
        or not 1 <= len(chinese) == meta.get("sram_count", meta["chinese_count"]) <= 0x4000
        or meta["first_chinese_id"] != 0x8000
        or not 0x8000 < narrow_first <= narrow_limit <= 0x8000 + len(chinese)
        or max(g for _, g in chinese) != meta.get("last_sram_id", meta["last_chinese_id"])
        or any(a[0] >= b[0] for a, b in zip(entries, entries[1:]))
        or sorted(g for _, g in chinese) != list(range(0x8000, 0x8000 + len(chinese)))
        or any(not (code <= 0x10ffff and
               not 0xd800 <= code <= 0xdfff)
               for code, glyph in chinese)):
    raise SystemExit("glyph map violates the canonical ID allocation")

identity = ", ".join(f"0x{byte:02x}" for byte in bytes.fromhex(digest[:32]))
legacy = ", ".join(f"0x{byte:02x}" for byte in bytes.fromhex(
    meta.get("punctuation_mapping_hex", meta["mapping_id_hex"])))
output.write_text(
    f"#define LEGACY_WIDE_COUNT {meta['chinese_count']}\n"
    f"#define NARROW_FIRST 0x{narrow_first:04x}\n"
    f"#define NARROW_LIMIT 0x{narrow_limit:04x}\n"
    f"const uint8_t sf_legacy_mapping[16] = {{ {legacy} }};\n"
    f"const uint8_t sf_mapping[16] = {{ {identity} }};\n"
    "static const uint32_t chinese_scalars[] = {\n"
    + "".join(f"    0x{code:06x},\n" for code, _ in chinese)
    + "};\n"
)

with output.open("a") as table:
    table.write("static const uint16_t chinese_glyph_ids[] = {\n" + "".join(f"    0x{glyph:04x},\n" for _, glyph in chinese) + "};\n")
    table.write("static const uint32_t scalars_by_glyph[] = {\n" + "".join(f"    0x{code:06x},\n" for code, _ in sorted(chinese, key=lambda x: x[1])) + "};\n")
