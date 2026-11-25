# SUPERFACE

SUPERFACE is a physical Linux terminal built from an Orange Pi Zero 2W and a Terasic DE1 FPGA board. It gives an ordinary Linux shell a VGA monitor and a PS/2 keyboard while keeping terminal emulation, applications, and authentication on Linux. The FPGA drives an 80 × 30 text screen at 640 × 480, with 8 × 16 character cells and independently selectable ANSI 16-color foregrounds and backgrounds.

```mermaid
flowchart LR
    App["Linux applications and PAM login"] <-->|PTY| Host["Orange Pi • C and libvterm"]
    Host <-->|"UART2 • 3 Mbaud • 8N1"| Link["Cyclone II • packet and key engine"]
    Key["PS/2 keyboard"] --> Link
    Link --> Grid["Staged grid • VBlank commit"]
    Grid --> VGA["50 MHz scanout • RGB444 VGA"]
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

A negotiated extension stages changed spans against a shadow grid. One VBlank operation publishes the entire staged image and cursor. Each staged row is validated and acknowledged promptly, and keyboard packets have their own reliable sequence space. The original protocol profile stays available for legacy firmware.

| Physical UART workload | Original v1 | Phase 8 |
| --- | ---: | ---: |
| One changed cell | 16.80 ms | 16.79 ms |
| Eight short spans on separate rows | 134.26 ms | 16.68 ms |
| Full 2,400-cell update | 503.92 ms | 50.34 ms |
| Full clear | 503.91 ms | 50.29 ms |
| Four-row sparse animation | 14.88 updates/s | 59.53 updates/s |

The measurements use a deterministic direct-wire peer and time the last visible-commit ACK for each workload. They include serial transfer, staging and VBlank. They exclude application execution and monitor response. A raw 7,200-byte screen takes at least 24 ms to serialize at 3 Mbaud. Run `python3 host/uart/benchmark.py --batch` with the service stopped and the development user granted temporary UART access. [Verification record](docs/VERIFICATION.md)

## Character coverage

The canonical map covers 95 printable ASCII characters, 6,727 Simplified Chinese Han characters, 117 wide punctuation and full-width characters, and 652 single-cell terminal symbols. It includes Box Drawing, Block Elements, Braille Patterns, Arrows, most printable Latin-1 characters, and selected geometric, mathematical and typographic characters. The negotiated profile preserves character width for missing symbols and draws an outlined placeholder with the current colors. The two placeholders live in FPGA logic and work in ASCII fallback. The manifest lists exact code points and the font image identity. [Font assets](docs/SUPERFACE_FONT_ASSETS.md) · [Manifest](assets/fonts/font_manifest.json)

## Build and run

1. Use Quartus II 13.0 SP1 with Cyclone II support. Put `quartus_sh` on `PATH`, then run `sh lab8_restored/tools/build_phase5.sh /tmp/sf-board`. The script builds in a clean copy and produces `LAB8.sof`. Load it via the USB-Blaster in JTAG mode.
2. Preserve the current complete U9 Flash contents and program the matching font image using the [PFL procedure](host/flash/README.md). The host and FPGA require the same mapping identity. They negotiate ASCII fallback if the font is unavailable or mismatched.
3. On the Orange Pi, run `sh host/deps/build-libvterm.sh`, then `make -C host check`. The dependency is pinned and built statically. Use the [service installation instructions](host/service/README.md) to install the checked executables, terminfo, systemd unit, and restricted UART udev rule.
4. With the service enabled and the DE1 configured, log in on VGA with the PS/2 keyboard. The installed unit selects standard Colemak for physical input, including the login and password prompts. Edit the unit with `systemctl edit superface.service` and replace the `ExecStart` line with one using `--keyboard qwerty` to switch layouts. The development executable defaults to QWERTY.
5. Run `sh host/service/verify-display` for a mixed-language, color and glyph check. Run `sh host/service/verify-display web` for the local UTF-8 ELinks fixture.

The production system passed a cold boot using EPCS4 on the DE1 and the 48 MHz UART2 boot default on the Orange Pi. The local terminal service starts and reconnects independently of SSH or Wi-Fi. The release includes the verified EPCS4 programming file and the [standalone setup and rollback instructions](host/service/README.md#standalone-boot). See the [verification record](docs/VERIFICATION.md) for the actual deployment status. The terminal has a fixed palette and character-cell graphics. Text shaping, bidirectional layout, emoji collections, and Chinese composition input are outside its scope.

## Licensing and authorship

Original SUPERFACE code and documentation use the [MIT License](LICENSE). Quartus-generated IP collateral retains its vendor notices, and contributed lab assets retain their original terms. The released ARM64 executable includes [libvterm under MIT](host/deps/libvterm-LICENSE.txt). The converted Fusion Pixel artwork and upstream font notices are under their [respective font licenses](assets/fonts/LICENSES).

The human creator directed the project, established its goals and requirements, performed physical integration and acceptance, and used OpenAI Codex extensively for implementation, testing, and debugging.
