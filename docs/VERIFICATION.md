# Verification for SUPERFACE 1.0

Measured on a Terasic DE1 EP2C20F484C7 and Orange Pi Zero 2W with a physical 3 Mbaud UART2 link. The archived build revision is `3e7a3daa1a28e74b76e1fa55694e47277c572d2b`. The public source is the same implementation with a cleaned history and release documentation.

| Check | Result | Evidence |
| --- | --- | --- |
| Quartus synthesis, fitting, assembly and timing | PASS | 5,189 of 18,752 LEs and 50 of 52 M4Ks. Board setup slack +2.012 ns at 50 MHz and +34.830 ns at 24 MHz. Worst board hold slack +0.215 ns across models. |
| Font image and verified U9 hardware | PASS | PFL identified Spansion S29AL032D Model 04 in x8 mode. Program and Verify passed. Independent 4,194,304-byte UART readback was byte-identical. |
| SRAM loader and font negotiation | PASS | Final FPGA accepted 7,496 SRAM glyphs, mapping `fa474ce2216d13d42cab9638c2541ab0`. The loader only reports an accepted mapping after the SRAM readback CRC passes. |
| UART recovery and duplicate handling | PASS | Physical CRC discard and duplicate ACK replay. PTY fault injection tested retries, recovery, snapshot restoration and crossed key traffic. An earlier build also exercised physical ASCII fallback after the loader rejected the font. |
| Unicode width and placeholders | PASS | Host and focused VHDL tests checked narrow versus wide rendering, ordinary question mark, and both placeholders. GHDL validated the complete loader, memory ownership and fallback cases. Operator observed mixed-language rendering and terminal graphics on VGA. |
| Display timing budget | PASS | Fixed 19 system clocks per group, yielding at most 1,520 of 1,600 clocks per scanline. The SRAM path reuses one bounded read slot per group. Visible-grid copy uses 4,800 clocks inside VBlank. |
| VGA applications and physical input | PASS | Operator accepted Bash, clear, neofetch, btop, cmatrix, vim and the local UTF-8 ELinks fixture. Physical checks included Colemak, display colors, glyphs and responsiveness. |
| Installed production service | PASS | Exact ARM64 executable, active and enabled, matched the frozen release. Temporary UART ACL removed. Operator verified physical PAM login. The baseline service also stopped with result `success`. |
| Independent absolute baud measurement | NOT RUN | Termios configuration, 48 MHz driver-reported reference, UART traffic, and error counters were checked. |
| Standalone cold boot | PASS | Both boards were cold-booted after verified EPCS4 programming and an extlinux default change. The operator confirmed the startup sequence, physical PAM login, Colemak and Chinese rendering without manual startup. |

## Bounded physical benchmark

| Workload | Original v1 | Phase 8 | Phase 8 host TX |
| --- | ---: | ---: | ---: |
| One changed cell | 16.80 ms | 16.79 ms | 47 bytes |
| Eight changed rows | 134.26 ms | 16.68 ms | 558 bytes |
| All 2,400 cells | 503.92 ms | 50.34 ms | 7,884 bytes |
| Clear all 2,400 cells | 503.91 ms | 50.29 ms | 7,884 bytes |
| Four sparse rows per update, 60 iterations | 14.88 updates/s | 59.53 updates/s | — |

These measurements run equal workloads through the direct-wire peer and end at the final visible-commit ACK. The sparse rate counts one complete four-row update. The serial bytes exclude FPGA replies. The benchmark exercises VGA frame scheduling, and the ACKs give a protocol-based visible-update rate. The operator's separate VGA check provides visual confirmation. Actual key latency and monitor response time were not instrumented. A historical service session recorded 8,762 span ACKs averaging 10.894 ms and 7,038 cursor ACKs with a 20.113 ms maximum.

The final ARM64 smoke run negotiated Chinese, committed its first snapshot in 61.4 ms after snapshot begin, and reported zero retries, CRC errors, framing errors and overruns. The status table distinguishes physical observations from simulated checks.

## Phase 8.1 verification

Quartus II 13.0 SP1 synthesized, fitted, assembled and timed the XGA build for the DE1 EP2C20F484C7. It used 5,197 of 18,752 logic elements, 50 of 52 M4Ks and one of four PLLs. The PLL derives 65 MHz from the board's 50 MHz oscillator. Slow-model setup slack is +4.362 ns in the pixel domain, +6.212 ns at 50 MHz and +30.633 ns at 24 MHz. Worst fast-model hold slack is +0.215 ns. The Gray-pointer routes met their 10 ns bounds. The legacy lab switch-clock warning for SW[0] remains. [DE1 hardware](https://www.terasic.com.tw/attachment/archive/83/DE1_UserManual_v1018.pdf) · [Cyclone II PLL](https://cdrdv2-public.intel.com/654376/cyc2_cii5v1.pdf) · [DMT timings](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/drm_edid.c)

The XGA RTL test checks every pixel of two frames with an 80-glyph external-SRAM schedule on every source line. It verifies sync, the black margins, 3:2 nearest-neighbor scaling, queue ordering, the cursor and the VBlank event. In the simulation, the latest source line was complete 57.9 µs before its admission check. A fitted fixture with the production BDF scanline builder and SRAM port completed all 80 external reads and wrote all 80 cache entries in 30.40 µs. The existing glyph and boot tests also pass. The host suite sends both layouts' Set 2 sequences through the actual executable using a PTY, including repeated Caps Lock make codes, release, normal Backspace and a crossed key during a staged frame.

The SOF was loaded through volatile JTAG and the existing Orange Pi service renegotiated Chinese mode with frame batching and acknowledged its first snapshot in 63.267 ms. The operator confirmed the monitor synchronized at 1024 × 768, the terminal retained its 80 × 30 geometry, and Colemak Caps Lock acted as Backspace. Chinese text, Unicode graphics and application responsiveness passed the physical check. The Phase 8 results above apply to the independent 640 × 480 rollback release.
