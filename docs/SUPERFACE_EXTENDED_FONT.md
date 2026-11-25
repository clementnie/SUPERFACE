# SUPERFACE v1.2.0 extended pixel font

The [coverage table](../assets/fonts/extended_coverage.md) counts mapped Unicode
scalars. The [manifest](../assets/fonts/font_manifest.json) records layout, CRCs
and digests, and the [additions CSV](../assets/fonts/extended_repertoire.csv)
records width, artwork and repertoire for each new scalar. This release
preserves all v1.1.0 mappings and the entire v1.1.0 SRAM payload prefix.

## Address and storage budget

| Item | Published v1.1.0 | v1.2.0 |
| --- | ---: | ---: |
| Printable ASCII in the dedicated ROM | 95 | 95 |
| Narrow SRAM glyphs | 652 | 5,242 |
| Wide SRAM glyphs | 6,844 | 11,142 |
| SRAM glyphs | 7,496 | 16,384 |
| Total mapped scalars | 7,591 | 16,479 |
| SRAM words used | 119,936 | 262,144 |
| SRAM bytes used | 239,872 | 524,288 |
| SRAM bytes free | 284,416 | 0 |
| Flash header and payload bytes | 239,936 | 524,352 |

Every SRAM slot occupies 16 little-endian 16-bit words, or 32 bytes. A narrow
slot uses bits 7–0 on all 16 rows. A wide slot uses bits 11–0 on 12 rows and
has four zero padding words. Useful bitmap storage is 16 bytes per narrow
glyph and 18 bytes per wide glyph. The renderer reads the low 14 ID bits and
appends a four-bit row index. The 18-bit SRAM word address therefore supports
16,384 slots. The final slot is ID `BFFF`, word addresses `3FFF0–3FFFF`.
The loader verifies all 16 words. The wide renderer displays rows 0–11.
The published v1.1.0 allocation ended at ID `9D47`, word `1D47F`.

The Glyph ID wire field is 16 bits and can encode `FFFF`. Only
`0020–007E` are printable ROM IDs. `007F` and `0080` are dedicated
one- and two-cell missing glyphs. `FFFF` marks the second cell of a
matching-color wide pair. The ranges `0000–001F`, `0081–7FFF`,
and `C000–FFFE` are unavailable as glyphs. Extended SRAM IDs are
wide in `8000–9ABB`, narrow in `9ABC–AF35`, and wide in
`AF36–BFFF`. No ID or address widening is needed.

The existing format stores a 16-bit count, a 32-bit payload size, and the
first 16 bytes of the canonical CSV SHA-256 in its 64-byte header. The
FPGA count signal is 15 bits and UART negotiation clamps the valid count
at 16,384. The 22-bit Flash byte address covers 4 MiB and the font
partition covers `000000–08FFFF`. The expanded image ends at byte
`08003F`, leaving 65,472 bytes in the partition. The new mapping ID is
`3b16b688374f2ca0af67d2836bc19b16`. Header CRC-32 is `91de5386` and
payload CRC-32 is `427c2cf6`.

## Startup and scanout

The 50 MHz loader spends 22 cycles per Flash byte, 11 cycles per SRAM
write and 12 cycles per readback word, plus 10,004 reset and control
cycles. This gives 160.942 ms in v1.1.0 and 351.501 ms in v1.2.0 from
reset release to ownership handoff. The full-image production bus
model reached completion at 351.501 ms. The 1-second watchdog has
about 648.5 ms of headroom. Runtime scanout still uses one SRAM fetch
slot per cell or pair and the same 1,520-cycle maximum source-line
budget before queue-control overhead.

## Artwork and repertoire

Fusion Pixel 12px remains the primary source. Han additions retain its
native 12 × 12 masks. The generator preserves 6-pixel Fusion letterforms
inside the 8-pixel cell, fits larger glyphs using integer pixel placement,
and uses hand-tuned eight-column suit masks to keep solid and outlined
forms distinct. GNU Unifont supplies missing symbol and language
artwork. Every new visible glyph uses either one 8 × 16 cell or a
two-cell 12 × 12 mask according to Unicode 16 East Asian Width, with
Ambiguous treated as one cell. Combining marks, controls, invisible
formatting and the halfwidth Hangul filler are excluded.

The selection first covers games and terminal interfaces, then
technical and common-language text. `tty-solitaire` v1.4.1 uses
U+2666, U+2660, U+2665 and U+2663. The csol default and compact themes
use the same suits. The pack also covers U+2660–U+2667, U+2654–U+265F
and U+2680–U+2685. [tty-solitaire rendering source](https://github.com/mpereira/tty-solitaire/blob/v1.4.1/src/gui.c) · [csol themes](https://github.com/nielssp/csol/tree/b3bd1938e20d890b5eafe9d620d74621aef1bf80/themes)

Remaining slots go to available Fusion Han from GB/T 2312, GB 8105 and
Taiwan MOE's 4,808 common characters, followed by Big5 frequent and
secondary repertoire tiers. GB 8105 level 1 precedes Taiwan's common
list. Level 2 and Big5 frequent precede level 3 and Big5 secondary.
GB 8105 uses official table numbering and Big5 uses encoding order
within each tier. The Taiwan spreadsheet's A02149 character column
shows U+6C68 and is used in place of the U+6C69 listed in its code
column. Existing Han retain their original Simplified forms.
New Taiwanese repertoire glyphs use the Traditional variant.
[Taiwan MOE table](https://language.moe.gov.tw/material/info?m=9fe3ff5a-5a8c-4817-9e60-6337dd55a509) · [GB 8105 standard](https://www.unicode.org/L2/L2014/14082-n4508-china.pdf) · [Unicode 16 Unihan](https://www.unicode.org/Public/16.0.0/ucd/Unihan.zip)

## Reproduce the bundle

Use Python 3.14 or another Python build with Unicode data 16.0.0. Keep
the following downloads outside the source workspace. Extract the
v1.1.0 source into a separate directory. The tool pins the published
mapping, manifest and image by SHA-256 and checks the ASCII MIF.

| Input | Source |
| --- | --- |
| v1.1.0 baseline | [Published source and checksums](https://github.com/clementnie/SUPERFACE/releases/tag/v1.1.0) |
| Fusion Pixel 12px mono BDF archive | [Pinned 2026.11.10 archive](https://github.com/TakWolf/fusion-pixel-font/releases/download/2026.11.10/fusion-pixel-font-12px-monospaced-bdf-v2026.11.10.zip) |
| Unifont 16.0.04 source | [Pinned Unifont source archive](https://www.unifoundry.com/pub/unifont/unifont-16.0.04/unifont-16.0.04.tar.gz) |
| Unihan 16.0.0 | [Pinned Unihan archive](https://www.unicode.org/Public/16.0.0/ucd/Unihan.zip) |
| Taiwan Ministry of Education common characters | [Pinned 4,808-character ODS](https://language.moe.gov.tw/uploads/files/17694982751710.ods) |
| Unicode data notice | [Unicode data license](https://www.unicode.org/license.txt) |

```sh
python3 tools/extend_pixel_font.py \
  --baseline /tmp/superface-v1.1.0/assets/fonts \
  --fusion /tmp/fusion-pixel.zip --unifont /tmp/unifont.tar.gz \
  --unihan /tmp/Unihan.zip --taiwan /tmp/tw.ods \
  --unicode-license /tmp/unicode-license.txt
```

Add `--verify` to check the regenerated mapping, Flash image, MIF,
notices, manifest and FPGA constants against the checked-in outputs.
Run the host build to regenerate its lookup table from the same
mapping. The [Flash and rollback procedure](../host/flash/README.md)
applies to the matching host, SOF, EPCS4 and font image.

Run `python3 host/flash/demo-extended.py` from an authenticated VGA
shell to display the glyph matrix, including both placeholders and
U+794C at ID `BFFF`. The command and script use ASCII.
