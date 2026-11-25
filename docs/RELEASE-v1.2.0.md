# SUPERFACE v1.2.0 verification

The Extended Pixel Font Pack adds **8,888** mapped glyphs, bringing the
total from **7,591 to 16,479**. The 16,384 external glyphs occupy all
524,288 bytes of SRAM, up from 239,872 bytes. The 95 printable ASCII
glyphs remain in their dedicated ROM. See the [exact coverage table](../assets/fonts/extended_coverage.md),
[manifest](../assets/fonts/font_manifest.json) and [font budget](SUPERFACE_EXTENDED_FONT.md).

## Fit, timing and physical UART performance

The Quartus II 13.0 SP1 Cyclone II fit uses 5,203 of 18,752 logic
elements, 2,669 registers, 50 of 52 M4Ks, 148,128 of 239,616 memory
bits, 155 of 315 pins and one of four PLLs. Slow-model setup slack is
+4.445 ns at 65 MHz, +4.353 ns at 50 MHz and +33.757 ns at 24 MHz.
The worst fast-model hold slack is +0.215 ns. Gray-pointer routes meet
their 10 ns constraints. TimeQuest still reports the inherited SW[0]
lab clock warning. The production bus model loads and validates the
full font in 351.501 ms against a 1-second watchdog.

| Physical 3 Mbaud workload | v1.1.0 | v1.2.0 |
| --- | ---: | ---: |
| Single-cell visible ACK | 16.66 ms | 16.66 ms |
| Eight-row visible ACK | 16.48 ms | 16.54 ms |
| Full-screen visible ACK | 49.92 ms | 49.92 ms |
| Clear-screen visible ACK | 49.88 ms | 49.93 ms |
| Four-row sparse coherent updates | 60.01 Hz | 60.01 Hz |

## Acceptance

- Font regeneration matched the published v1.1.0 ID and bitmap prefix
  and reproduced the v1.2.0 font, CRCs, mapping and generated notices.
  The width audit checked all 8,888 additions against libc and patched
  libvterm. The host protocol tests exercised the highest ID, ordinary
  one- and two-cell glyphs, and both missing-glyph widths.
- Quartus built and timed the complete BDF project. SRAM bus-model
  verification reached and read back word `3FFFF` and rejected malformed
  headers and corrupt payloads.
- Two independent 4 MiB U9 backups matched and contained the exact
  published v1.1.0 font. Quartus identified the S29AL032D Model 04 in
  x8 mode and verified the rollback image before programming. Program
  + Verify passed. Independent 4,194,304-byte UART readback matched the
  full-device candidate byte for byte. The matching FPGA and ARM64
  host negotiated the expanded font with frame batching.
- The operator accepted the physical VGA demo, suits, chess, math,
  Simplified and Traditional Chinese, alignment, and missing-glyph
  masks. `ttysolitaire`, `btop`, `neofetch` and `cmatrix` passed
  on the physical terminal. The operator saw no performance regression.

- EPCS4 Program + Verify and a separate device Verify passed. The
  device matched the released v1.1.0 POF before programming. A separate
  read of the prior EPCS4 contents was also verified and retained privately.
- Both boards passed physical standalone cold boot. The operator
  confirmed VGA, PAM login, Chinese and all suits after power cycling.
  The Orange Pi boot ID changed. The enabled service started with
  Colemak, loaded the expected ARM64 binaries, negotiated the expanded
  font, and acknowledged the first snapshot in 67.343 ms. The temporary
  UART ACL had been removed.

The final ARM64 executable hashes are

```text
a1830cb0a76d52fa9741c6f4ef453209977f33138be7e8b9c6edb44eb4f97b6f  host/build/superface
59afa3e4f340d7f839c65092a03fe4e1ce1c49d3933e97c5e062c23530f9f0ed  host/build/superface-uart
```

## Rollback

[v1.1.0](https://github.com/clementnie/SUPERFACE/releases/tag/v1.1.0)
remains the independent XGA rollback release. Its published U9 image,
EPCS4 POF, SOF and ARM64 package carry their original checksums.
[v1.0.0](https://github.com/clementnie/SUPERFACE/releases/tag/v1.0.0)
remains the independently verified 640 × 480 release. To restore the
same hardware, follow the [U9 programming and recovery procedure](../host/flash/README.md)
and [standalone service rollback instructions](../host/service/README.md#standalone-boot)
using a matching set. Complete board-specific backups are retained
privately.
