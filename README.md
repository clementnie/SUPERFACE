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

SUPERFACE 1.1 was verified on a physical VGA monitor at 1024 × 768 at 60 Hz. Its 65 MHz Cyclone II PLL drives only VGA. The horizontal timing is 1024 active, 24 front porch, 136 sync and 160 back porch, for 1344 total. The vertical timing is 768 active, 3 front porch, 6 sync and 29 back porch, for 806 total. Both syncs are negative. The Phase 8 rollback release runs at 640 × 480. [Phase 8 rollback release](https://github.com/clementnie/SUPERFACE/releases/tag/v1.0.0)

The centered 960 × 720 terminal has 32-pixel side margins, 24-pixel top and bottom margins, and 12 × 24 output pixels per cell. Each output coordinate maps to `floor(2 × offset / 3)` on its bitmap axis. It preserves the original 8 × 16 ASCII and terminal graphics, 12 × 12 Chinese bitmaps and two-cell Chinese layout, punctuation, and missing glyphs. The same nearest-neighbor sampling scales the cursor and boot screen. The Phase 8 U9 font image is compatible.

A negotiated extension stages changed spans against a shadow grid. One VBlank operation publishes the entire staged image and cursor. Each staged row is validated and acknowledged promptly, and keyboard packets have their own reliable sequence space. The original protocol profile stays available for legacy firmware.

| Physical UART workload | Original v1 | Phase 8 |
| --- | ---: | ---: |
| One changed cell | 16.80 ms | 16.79 ms |
| Eight short spans on separate rows | 134.26 ms | 16.68 ms |
| Full 2,400-cell update | 503.92 ms | 50.34 ms |
| Full clear | 503.91 ms | 50.29 ms |
| Four-row sparse animation | 14.88 updates/s | 59.53 updates/s |

The historical Phase 8 measurements use a deterministic direct-wire peer and time the last visible-commit ACK for each workload. They include serial transfer, staging and VBlank. They exclude application execution and monitor response. A raw 7,200-byte screen takes at least 24 ms to serialize at 3 Mbaud. Run `python3 host/uart/benchmark.py --batch` with the service stopped and the development user granted temporary UART access. [Verification record](docs/VERIFICATION.md)

## Character coverage

The canonical map covers 95 printable ASCII characters, 6,727 Simplified Chinese Han characters, 117 wide punctuation and full-width characters, and 652 single-cell terminal symbols. It includes Box Drawing, Block Elements, Braille Patterns, Arrows, most printable Latin-1 characters, and selected geometric, mathematical and typographic characters. The negotiated profile preserves character width for missing symbols and draws an outlined placeholder with the current colors. The two placeholders live in FPGA logic and work in ASCII fallback. The manifest lists exact code points and the font image identity. [Font assets](docs/SUPERFACE_FONT_ASSETS.md) · [Manifest](assets/fonts/font_manifest.json)

## Build and run

1. Use Quartus II 13.0 SP1 with Cyclone II support. Put `quartus_sh` on `PATH`, then run `sh lab8_restored/tools/build_phase5.sh /tmp/sf-board`. The script builds in a clean copy and produces `LAB8.sof`. Load it via the USB-Blaster in JTAG mode.
2. On a fresh DE1, preserve the complete U9 Flash contents and program the matching font image using the [PFL procedure](host/flash/README.md). Existing Phase 8 installations can reuse their verified U9 font image. The host and FPGA require the same mapping identity. They negotiate ASCII fallback if the font is unavailable or mismatched.
3. On the Orange Pi, run `sh host/deps/build-libvterm.sh`, then `make -C host check`. The dependency is pinned and built statically. Use the [service installation instructions](host/service/README.md) to install the checked executables, terminfo, systemd unit, and restricted UART udev rule.
4. With the service enabled and the DE1 configured, log in on VGA with the PS/2 keyboard. See the keyboard layout commands below.
5. Run `sh host/service/verify-display` for a mixed-language, color and glyph check. Run `sh host/service/verify-display web` for the local UTF-8 ELinks fixture.

Phase 8 passed a cold boot using EPCS4 on the DE1 and the 48 MHz UART2 boot default on the Orange Pi. The local terminal service starts and reconnects independently of SSH or Wi-Fi. The release includes the verified EPCS4 programming file and the [standalone setup and rollback instructions](host/service/README.md#standalone-boot). See the [verification record](docs/VERIFICATION.md) for the actual deployment status. The terminal has a fixed palette and character-cell graphics. Text shaping, bidirectional layout, emoji collections, and Chinese composition input are outside its scope.

### Keyboard layout

The production service uses standard Colemak for the physical login prompt and shell. Physical Caps Lock sends Backspace and repeats when held. The physical Backspace key works in both layouts. QWERTY uses conventional Caps Lock.

Run these commands on the Orange Pi. The layout applies to the physical login prompt and shell and persists across boots.

```sh
sudo superface-layout colemak
sudo superface-layout qwerty
superface-layout status
```

Each layout change restarts `superface.service` and **terminates the current physical login session**. Use SSH or the UART0 console when you need the command session to stay open.

## Licensing

Original SUPERFACE code and documentation use the [MIT License](LICENSE). Quartus-generated IP collateral retains its vendor notices, and contributed lab assets retain their original terms. The released ARM64 executable includes [libvterm under MIT](host/deps/libvterm-LICENSE.txt). The converted Fusion Pixel artwork and upstream font notices are under their [respective font licenses](assets/fonts/LICENSES).
