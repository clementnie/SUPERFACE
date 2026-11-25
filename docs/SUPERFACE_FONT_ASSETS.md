# SUPERFACE font assets

The font bundle includes **6,727 Chinese glyphs** from a requested repertoire of **6,763 Han scalars**. It is ready for offline use by the Orange Pi and for integration into the DE1 Flash-to-SRAM startup design. The [architecture](SUPERFACE_ARCHITECTURE.md) specifies the display and storage contracts. The [UART protocol](SUPERFACE_PROTOCOL.md) defines compatibility negotiation at 3,000,000 baud.

## Repertoire and source

| GB/T 2312 Han level | Requested | Supported | Missing upstream |
| --- | ---: | ---: | ---: |
| Level 1 | 3,755 | 3,755 | 0 |
| Level 2 | 3,008 | 2,972 | 36 |
| Total | 6,763 | 6,727 | 36 |

The requested input is the full Han portion of GB/T 2312-1980. `repertoire` derives it from the Python `gb2312` codec by decoding the EUC byte forms of rows 16–55 (`B0–D7`) and 56–87 (`D8–F7`), with trails `A1–FE` and the five unassigned positions `D7FA–D7FE` excluded. The checked-in list is sorted by scalar, with one six-digit `U+` entry per LF-terminated line. The generator fails if a Level 1 glyph is absent. It includes each Level 2 glyph present in the pinned bitmap and reports every absent Level 2 scalar with its literal character in [missing_zh_hans.csv](../assets/fonts/missing_zh_hans.csv). Those 36 scalars have no Chinese Glyph ID or SRAM slot. The host applies the existing fallback, which is ASCII `?` followed by a same-color space for width-two characters. [GB/T 2312-1980 standard record](https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=5664A728BD9D523DE3B99BC37AC7A2CC), [Chinese standards authority on the 6,763 Han positions](https://www.sac.gov.cn/jdbnhbz/bzgs/art/2021/art_5e8ba919bec34784b55960ea23175ad3.html)

The repertoire covers the full first Han level and most of the second. Non-Han GB/T 2312 rows, further Unicode Han coverage and other scripts are outside the Chinese asset. Unified Han code points can be shared across languages. The `zh_hans` source selects Simplified Chinese glyph shapes for the requested scalars. Printable ASCII retains its original separate artwork and IDs.

### Pinned native bitmap

Use [Fusion Pixel Font release 2026.11.10](https://github.com/TakWolf/fusion-pixel-font/releases/tag/2026.11.10), source commit [`a38a5de9cc099ce28da3cab9f9411aa83cc7a3e9`](https://github.com/TakWolf/fusion-pixel-font/tree/a38a5de9cc099ce28da3cab9f9411aa83cc7a3e9). The exact artwork input is `fusion-pixel-12px-monospaced-zh_hans.bdf` in `fusion-pixel-font-12px-monospaced-bdf-v2026.11.10.zip`. The converter verifies both hashes pinned in the [manifest](../assets/fonts/font_manifest.json).

Upstream's [font build](https://github.com/TakWolf/fusion-pixel-font/blob/a38a5de9cc099ce28da3cab9f9411aa83cc7a3e9/tools/font/context.py) combines base Ark Pixel artwork, fallback sources, Fusion Pixel PNG patches and flavor mappings before producing each language variant. The published BDF is an X11 Bitmap Distribution Format file containing the resolved native bitmap. Its global box is `12 12 0 -2`, with ascent 10 and descent 2. Each selected glyph has an advance of `12 0`. The BDF `BBX` records trimmed width, height and lower-left offsets. Restore each box at column `x_offset` and row `10 − (y_offset + height)` in the native 12 × 12 cell. Copy each row top to bottom and its occupied pixels left to right, skipping X11 byte padding. The converter rejects any selected box that exceeds the cell, unexpected advances, malformed rows and nonzero X11 byte padding. This preserves the artwork with its original placement and requires neither a scalable font rasterizer nor a rebuild of upstream. The upstream bitmap BDF is separate from Quartus schematic `.bdf` files. [Upstream documentation](https://github.com/TakWolf/fusion-pixel-font/blob/a38a5de9cc099ce28da3cab9f9411aa83cc7a3e9/README.md), [12-pixel layout configuration](https://github.com/TakWolf/fusion-pixel-font/blob/a38a5de9cc099ce28da3cab9f9411aa83cc7a3e9/assets/configs/fonts/12px.yaml)

Redistribute the converted font data under SIL Open Font License 1.1 with the [Fusion Pixel notice](../assets/fonts/LICENSES/fusion-pixel/OFL.txt) and bundled [Ark Pixel](../assets/fonts/LICENSES/ark-pixel/OFL.txt), [Cubic 11](../assets/fonts/LICENSES/cubic-11/OFL.txt) and [Galmuri](../assets/fonts/LICENSES/galmuri/LICENSE.txt) notices. The converter copies those four exact license members from the release archive. The project uses the SUPERFACE name for the derived font bundle. Upstream build tooling has a separate MIT license and is not redistributed here. [Upstream license terms](https://github.com/TakWolf/fusion-pixel-font/blob/a38a5de9cc099ce28da3cab9f9411aa83cc7a3e9/LICENSE-OFL)

## Regenerate and check

From the repository root, use Python 3.11+ with its standard library. Keep the upstream archive outside the repository. The generator uses the checked-in repertoire by default.

```sh
archive=/tmp/sf-fusion-12px-bdf.zip
curl --fail --location \
  https://github.com/TakWolf/fusion-pixel-font/releases/download/2026.11.10/fusion-pixel-font-12px-monospaced-bdf-v2026.11.10.zip \
  --output "$archive"
python3 tools/generate_superface_font.py build --archive "$archive"
python3 tools/generate_superface_font.py check --archive "$archive"
```

Reproduce the repertoire and verify a separate build byte for byte.

```sh
copy=$(mktemp -d)
python3 tools/generate_superface_font.py repertoire > "$copy/required_zh_hans.txt"
cmp assets/fonts/required_zh_hans.txt "$copy/required_zh_hans.txt"
python3 tools/generate_superface_font.py build --archive "$archive" --output "$copy"
diff -r assets/fonts "$copy"
```

The workspace carries the requested list, generated bundle and notices so integration can use them immediately. Update them together on any deliberate change of repertoire or source.

| Artifact | Purpose |
| --- | --- |
| [required_zh_hans.txt](../assets/fonts/required_zh_hans.txt) | All 6,763 requested Han scalars. |
| [glyph_map.csv](../assets/fonts/glyph_map.csv) | Canonical mapping and host input. It has 95 printable ASCII entries and 6,727 supported Han entries. |
| [missing_zh_hans.csv](../assets/fonts/missing_zh_hans.csv) | Code point, character and level for each of the 36 unavailable requests. |
| [chinese_sram.mif](../assets/fonts/chinese_sram.mif) | Full 262,144-word, 16-bit SRAM model image. Used font words are explicit and the unused tail is zero-filled for simulation. |
| [superface_font.bin](../assets/fonts/superface_font.bin) | Raw binary to program into the parallel user Flash at byte zero. |
| [font_manifest.json](../assets/fonts/font_manifest.json) | Provenance, repertoire counts, format version, compatibility identity, CRCs, address bounds, file sizes and hashes. |
| [font_contact_sheet.svg](../assets/fonts/font_contact_sheet.svg) | Labeled preview generated from the decoded SRAM MIF. It includes every requested example. |

The classic [ascii_8x16.mif](../lab8_restored/ascii_8x16.mif) is unchanged. Its SHA-256 is `dac189ba1fe8eb46c94341b90f4e7a2f6b3e9e8d61c073b05d75b6b103b1d554`. Verification checks its 2,048 explicit binary data bytes at hexadecimal addresses, the blank space and the nonblank `?`. The existing [Font_ROM symbol](../lab8_restored/Font_ROM.bsf) and [vendor ROM IP](../lab8_restored/Font_ROM.qip) already load that file as a registered-address, unregistered-output 2,048 × 8 ROM. Keep the address `(glyph_id << 4) | local_y` for printable ASCII and select its MSB for the left pixel. The source `font_8x16.c` remains absent from the restored project. [Existing ROM implementation](../lab8_restored/Font_ROM.vhd), [existing renderer](../lab8_restored/Text_Renderer.bdf)

## Storage and identity

All ranges in the tables use byte addresses for Flash and 16-bit word addresses for SRAM. The end address in an inclusive range is the last byte or word of the slot.

| Scalar | Glyph ID | SRAM word range | Flash range |
| --- | --- | --- | --- |
| U+4E00 一 | `0x8000` | `00000–0000F` | `00040–0005F` |
| U+4E2D 中 | `0x8020` | `00200–0020F` | `00440–0045F` |
| U+4F60 你 | `0x80C8` | `00C80–00C8F` | `01940–0195F` |
| U+9FA0 龠 | `0x9A46` | `1A460–1A46F` | `34900–3491F` |

Each slot starts at `(glyph_id − 0x8000) << 4`. Row 0 is the top, bit 11 the leftmost pixel, bits 15–12 zero, and words 12–15 zero. For example, 一 has its 11 on-pixels at native row 6, producing `0x0FFE` at SRAM word `0x00006` and bytes `FE 0F` at Flash offsets `0x004C–0x004D`. IDs `0x9A47–0xBFFF` are unallocated in this mapping. Reserved IDs, including continuation `0xFFFF`, have no independent SRAM slots.

| Quantity | Actual |
| --- | ---: |
| Useful bitmap bytes per glyph | 18 (144 bits) |
| Physical SRAM bytes per glyph | 32 (16 words) |
| Packed useful bitmap bytes | 121,086 (118.25 KiB) |
| Row and slot padding | 94,178 bytes (14 per glyph) |
| Reserved slot bytes | 0 |
| Total allocated SRAM and Flash payload | 215,264 bytes (210.22 KiB) |
| SRAM words used / available | 107,632 / 262,144 |
| SRAM remaining | 309,024 bytes (301.78 KiB) |
| Flash header / extra image alignment | 64 / 0 bytes |
| Total Flash image | 215,328 bytes (210.28 KiB) |
| Logical Flash font partition | `[0x000000, 0x090000)` |
| Actual programmed Flash byte range | `[0x000000, 0x034920)` |
| Unprogrammed bytes in that partition | 374,496 bytes |
| Capacity outside this image on documented 1 MiB / 4 MiB parts | 833,248 / 3,978,976 bytes |
| Textual SRAM MIF file | 1,937,489 bytes |

The earlier approximately 131.4 KiB figure was provisional. The current image follows the verified 6,727-glyph count and pays the full 32-byte slot cost instead of the 18 useful bitmap bytes. The logical Flash partition covers even a 16,384-glyph v1 image and fits both documented Flash capacities. Treat physical erase boundaries and the installed part size as board-specific. The project uses this partition in parallel user Flash. The EPCS4 configuration device is separate.

[The v1 header](SUPERFACE_ARCHITECTURE.md#chinese-bitmap-and-flash-image) occupies bytes 0–63. For this image it contains count `6727` (`0x1A47`), payload length `0x000348E0`, payload CRC-32 `0x04CA07AE` and header CRC-32 `0x6ACC1C1B`. The mapping ID is `552fa5cca77302d2b922d50ae444f2db`, the first 16 SHA-256 digest bytes of the exact LF-terminated canonical CSV. The host, Flash header and FPGA compare these 16 bytes in digest order. CRCs check the image. An artwork-only change can keep the same map identity if the entire CSV stays identical.

## Offline verification

An independent parser matched all 6,727 decoded SRAM bitmaps to the native BDF pixels, including offsets, row and pixel order, slot addresses and zero padding. It compared every allocated MIF word against the little-endian Flash payload and checked the header, reserved bytes and truncated CSV digest. A separate bitwise CRC matched both CRCs. A clean directory rebuild reproduced the bundle byte for byte. Corrupted archive, repertoire, mapping, missing report, CRC and MIF cases failed verification. The [decoded contact sheet](../assets/fonts/font_contact_sheet.svg) was inspected with all 16 sample positions present, including both occurrences of 民.

## Next schematic integration

1. Verify the installed DE1 Flash and SRAM parts. Use the [documented parallel Flash programming path](SUPERFACE_ARCHITECTURE.md#programming-and-startup), including preserving existing contents where applicable and reading back the exact binary after programming. The MIF is for simulation and inspection. It does not initialize physical external SRAM.
2. In the future `Font_Startup.bdf` and `Parallel_Flash_Read.bdf`, bind Flash byte address 0, SRAM word address 0, the format version, and the manifest's exact count and mapping ID. Read the 64-byte header, check format, identity, reserved bytes, CRC and length, then copy exactly 107,632 words low byte first and CRC the payload. CRC the same range after reading SRAM back. Reject an incorrect image and expose the existing fault result without enabling Chinese reads. Stop writes after validation and hand SRAM ownership to the Phase 3 runtime read port. [Runtime SRAM interface](SUPERFACE_PHASE3_DISPLAY.md#font-and-sram-handoff) The current payload budgets about 138 ms of Flash reads, SRAM writes and readback using the provisional architecture timings, within the one-second watchdog.
3. In the renderer, require `0x8000 ≤ glyph_id < 0x9A47` and a valid load before indexing SRAM. Within local y=2–13, OR `local_y − 2` into the four low row-address bits and place bits 11–0 at offsets 2–13 of the two-cell rectangle. Preserve the existing ASCII ROM and host fallback. Use the manifest count and map ID for the unchanged UART handshake.

Keep system structure, memory and I/O visible in Quartus BDF. VHDL may implement control internals with matching BSF symbols for BDF integration. Offline checks establish source coverage, bitmaps, artifact integrity and reproducibility. Flash programming, startup loading and VGA rendering still require hardware verification.

## Appended punctuation extension

The independently frozen `superface-phase7-bilingual-6727` release retains the
original Han-only bundle. The punctuation development bundle appends117 pinned,
width-two punctuation/full-width symbols, producing6844 glyphs. Existing Han
IDs0x8000–0x9A46 and all their bitmap bytes remain unchanged; new glyphs start
at0x9A47. The CSV remains sorted by Unicode, while glyph IDs preserve the original
allocation and append the explicit list in assets/fonts/required_punctuation.txt.
The host now uses explicit forward IDs and an ID-ordered reverse table.

Run tools/extend_superface_font.py --archive /tmp/sf-fusion-12px-bdf.zip
from this checkout to regenerate the mapping, image, MIF, preview, manifest and
license notices together. The original generator still reproduces the historical
Han-only bundle. Extension mapping79e2e483b4f5bcb6fa6b8eb7e8722338; image219072
bytes. Width-one ambiguous punctuation is outside this extension so the existing
libvterm width contract stays unchanged. Physical punctuation acceptance is pending.

## Current release extension

After the original glyphs are generated, run these append-only steps with the same pinned ZIP outside the source tree.

```sh
python3 tools/extend_superface_font.py --archive "$archive"
python3 tools/extend_terminal_symbols.py --archive "$archive"
```

The terminal extension preserves the 6,844 existing wide glyph IDs and the exact SRAM payload prefix. It appends 652 narrow glyphs in 32-byte slots. Wide masks retain the 12 × 12 layout. Narrow masks use all 16 scanline rows and the low eight bits of each 16-bit word. Box Drawing, Block Elements and Braille are generated algorithmically. Other masks use the pinned Fusion Pixel asset or small authored bitmaps. Each regeneration refreshes the manifest, mapping digest, image CRCs, and upstream notices.
