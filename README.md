# SUPERFACE

SUPERFACE is a physical Linux terminal built from an Orange Pi Zero 2W and a Terasic DE1 FPGA board. It gives an ordinary Linux shell a VGA monitor and a PS/2 keyboard while keeping terminal emulation, applications, and authentication on Linux. The FPGA drives a fixed 80 × 30 character terminal with independently selectable ANSI 16-color foregrounds and backgrounds.

```mermaid
flowchart LR
    App["Linux applications and PAM login"] <-->|PTY| Host["Orange Pi • C and libvterm"]
    Host <-->|"UART2 • 3 Mbaud • 8N1"| Link["Cyclone II • packet and key engine"]
    Key["PS/2 keyboard"] --> Link
    Link --> Grid["Staged grid • VBlank commit"]
    Grid --> VGA["65 MHz pixel scanout • RGB444 VGA"]
    ROM["ASCII ROM"] --> VGA
    Flash["U9 parallel NOR Flash"] -->|Boot load and CRC| SRAM["External SRAM font"]
    SRAM --> VGA
```

## Wiring

Connect the boards with short 3.3 V logic leads and keep their power supplies independent. Set the DE1 RUN/PROG switch to RUN for volatile JTAG configuration.

| Orange Pi Zero 2W header | DE1 JP1 / GPIO_0 |
| --- | --- |
| Pin 15, PI5 TX | Pin 2, GPIO_0[1], B13 RX |
| Pin 22, PI6 RX | Pin 3, GPIO_0[2], A14 TX |
| Pin 14, GND | Pin 12, GND |

UART2 uses `/dev/ttyS2`, a 48 MHz reference, 3,000,000 baud, 8N1, idle-high signaling, and no flow control. The FPGA UART PHY runs at 24 MHz and crosses into the 50 MHz system through dual-clock FIFOs. Use the GPIO pins directly. The DE1 DB-9 carries RS-232 voltage levels. [Orange Pi UART2 setup](docs/SUPERFACE_UART2.md) · [Wire protocol](docs/SUPERFACE_PROTOCOL.md)

## Display and performance

SUPERFACE was verified on a physical VGA monitor at 1024 × 768 at nominal 60 Hz. Its 65 MHz Cyclone II PLL drives only VGA. The horizontal timing is 1024 active, 24 front porch, 136 sync and 160 back porch, for 1344 total. The vertical timing is 768 active, 3 front porch, 6 sync and 29 back porch, for 806 total. Both syncs are negative. The Phase 8 rollback release runs at 640 × 480. [Phase 8 rollback release](https://github.com/clementnie/SUPERFACE/releases/tag/v1.0.0)

The centered 960 × 720 terminal has 32-pixel side margins, 24-pixel top and bottom margins, and 12 × 24 output pixels per cell. Each output coordinate maps to `floor(2 × offset / 3)` on its bitmap axis. It preserves the original 8 × 16 ASCII and terminal graphics, 12 × 12 Chinese bitmaps and two-cell Chinese layout, punctuation, and missing glyphs. The same nearest-neighbor sampling scales the cursor and boot screen. Use the matching font image for each release.

A negotiated extension stages changed spans against a shadow grid. One VBlank operation publishes the entire staged image and cursor. Each staged row is validated and acknowledged promptly, and keyboard packets have their own reliable sequence space. The original protocol profile stays available for legacy firmware.

| Benchmark | Result |
| --- | ---: |
| Single-cell visible ACK | 16.66 ms |
| Multiline visible ACK | 16.54 ms |
| Full-screen visible ACK | 49.92 ms |
| Clear-screen visible ACK | 49.93 ms |
| Sparse coherent updates | 60.01 Hz |
| Original full-screen baseline | Approximately 504 ms |

The physical 3 Mbaud measurements time the final visible-commit ACK, including serial transfer, staging and VBlank. Multiline means eight short spans on separate rows; sparse means four changed rows per update. **60.01 Hz is the sparse update frequency, not an arbitrary full-screen frame rate.** A raw 7,200-byte screen alone takes at least 24 ms to serialize. Application execution and monitor response are excluded. [v1.2.0 verification](docs/RELEASE-v1.2.0.md)

The v1.2.0 Cyclone II EP2C20F484C7 fit uses 5,203 / 18,752 logic elements (28%), 2,669 registers, 50 / 52 M4Ks, 148,128 / 239,616 memory bits (62%), 155 / 315 pins and 1 / 4 PLLs. Slow-model setup slack is +4.445 ns at 65 MHz, +4.353 ns at 50 MHz and +33.757 ns at 24 MHz; worst fast-model hold slack is +0.215 ns. Gray-pointer routes meet their 10 ns bounds. The inherited SW[0] lab clock warning remains. [Fit and timing evidence](docs/RELEASE-v1.2.0.md)

## Character coverage

The v1.2.0 font maps **16,479 Unicode scalars**, including 95 printable ASCII characters and 16,384 external-SRAM glyphs. The pack uses all 524,288 SRAM bytes, up from 239,872 in v1.1.0. Startup font loading and SRAM CRC readback take 351.501 ms in the production bus model. It adds all eight card suits, chess pieces, dice, expanded graphics and mathematical notation, Latin and IPA, Greek, Cyrillic, kana, Bopomofo, and 3,860 Han characters. It preserves the v1.1.0 bitmaps, IDs, complete Box Drawing, Block Elements and Braille sets, and the single- and double-cell missing-glyph masks. [Coverage by category](assets/fonts/extended_coverage.md) · [Exact code points and Glyph IDs](assets/fonts/glyph_map.csv) · [Manifest](assets/fonts/font_manifest.json) · [Font generation](docs/SUPERFACE_FONT_ASSETS.md)

## Build and run

1. Use Quartus II 13.0 SP1 with Cyclone II support. Put `quartus_sh` on `PATH`, then run `sh lab8_restored/tools/build_phase5.sh /tmp/sf-board`. The script builds in a clean copy and produces `LAB8.sof`. Load it via the USB-Blaster in JTAG mode.
2. On a fresh DE1, preserve the complete U9 Flash contents and program the matching font image using the [PFL procedure](host/flash/README.md). The v1.2.0 host, FPGA and U9 image must use the same mapping identity. They negotiate ASCII fallback if the font is unavailable or mismatched.
3. On the Orange Pi, run `sh host/deps/build-libvterm.sh`, then `make -C host check`. The dependency is pinned and built statically. Use the [service installation instructions](host/service/README.md) to install the checked executables, terminfo, systemd unit, and restricted UART udev rule.
4. With the service enabled and the DE1 configured, log in on VGA with the PS/2 keyboard. See the keyboard layout commands below.
5. Run `python3 host/flash/demo-extended.py` on VGA to check the font without Unicode input.

v1.2.0 passed standalone cold boot on both boards using EPCS4 and the existing Orange Pi UART2 setup. The local terminal service starts and reconnects independently of SSH or Wi-Fi. The operator verified VGA, PAM login, Chinese and playing-card suits after power cycling. The renderer supports individual glyphs and fixed-width cells. Text shaping, bidirectional layout, emoji collections, and Chinese composition input are outside its scope. [Standalone setup and rollback](host/service/README.md#standalone-boot) · [Physical verification](docs/RELEASE-v1.2.0.md)

### Keyboard layout

The production service uses standard Colemak for the physical login prompt and shell. Physical Caps Lock sends Backspace and repeats when held. The physical Backspace key works in both layouts. QWERTY uses conventional Caps Lock.

Run these commands on the Orange Pi. The layout applies to the physical login prompt and shell and persists across boots.

```sh
sudo superface-layout colemak
sudo superface-layout qwerty
superface-layout status
```

Each layout change restarts `superface.service` and **terminates the current physical login session**. Use SSH or the UART0 console when you need the command session to stay open.

## Release and licensing

Download the matching SOF, EPCS4 image, ARM64 package, U9 font image and mapping from [v1.2.0](https://github.com/clementnie/SUPERFACE/releases/tag/v1.2.0). Verify `SHA256SUMS` before installing. [v1.1.0](https://github.com/clementnie/SUPERFACE/releases/tag/v1.1.0) remains the independent XGA rollback release. [v1.0.0](https://github.com/clementnie/SUPERFACE/releases/tag/v1.0.0) remains the independently verified 640 × 480 rollback release.

Original project code and documentation use [GPL-2.0-only](LICENSE). Prior MIT grants, vendor IP terms, libvterm's MIT notice and all upstream font licenses remain intact. See [licensing scope and third-party notices](LICENSING.md).
