# SUPERFACE architecture

The Quartus II 13.0 SP1 project targets the Terasic DE1's Cyclone II EP2C20F484C7. The top-level `LAB8.bdf` shows the display, Flash/SRAM ownership, keyboard receiver, UART PHY and clocks. The original lab circuits remain in the project source. VHDL implements protocol and control internals. Matching BSF symbols expose those blocks in the schematics. Quartus-generated ROM and FIFO sources are vendor IP collateral.

## Linux host

The Orange Pi Zero 2W runs a C backend using a POSIX PTY and libvterm. The host translates terminal state into 80 × 30 three-byte cells, quantizes colors to the fixed ANSI palette, tracks damage, and sends PS/2 Set 2 input into the PTY with the selected keyboard layout. The privileged systemd launcher delegates authentication to Linux login and PAM, then the renderer runs as the dedicated service account. Local terminal operation requires UART2 and the FPGA.

## UART clock domains

`UART_PHY.bdf` places 3 Mbaud 8N1 sampling and serialization in the 24 MHz domain. Two dual-clock FIFOs connect it to the 50 MHz parser and serializer in `UART_Link.bdf`. The reliable host and key directions use separate sequence spaces. A CRC-16 protects each frame. Session renewal discards interrupted staging and restores the visible state with a fresh snapshot. See the [protocol](SUPERFACE_PROTOCOL.md) for the wire formats and timing.

## Display and font access

- `Xga_Display.bdf` connects the 50 MHz command and font paths to the 65 MHz raster and RGB444 output. `LAB8.bdf` shows the ALTPLL and pixel reset and status synchronizers. `Terminal_Display.bdf` retains the original 640 × 480 architecture for the restored lab revisions.
- `Grid_Commit.vhd` validates candidate rows, writes a bounded 2,400 × 24 shadow grid, and copies it to the visible store in at most 4,800 system clocks from VBlank entry. The snapshot staging RAM holds one row. The same VBlank installs the cursor. The visible store is a separate schematic with its own banked M4K RAM.
- `Scanline_Builder.bdf` uses 19 system clocks per single cell or wide pair. Both SRAM font paths launch at phase 4 and consume the result at phase 13. The existing 160 ns address-to-capture window and 20 ns FPGA I/O budgets apply. An 80-cell external-SRAM line takes 1,520 system clocks plus two queue-control clocks. A physical line lasts 20.677 µs. Nearest-neighbor scaling consumes two logical lines per three physical lines, giving 3,101.5 system clocks per pair against a worst-case 3,044. A four-slot, 16-bit dual-clock line RAM absorbs the alternating one- and two-line spacing. Gray pointers publish and release whole slots, and each slot holds the original 80 cell masks and colors.
- A synchronized VBlank trigger admits atomic commits. The 38 blank lines provide approximately 786 µs for the 4,800-clock (96 µs) visible grid copy. The producer starts after VBlank and has the 24-line top margin (496 µs) to fill the initial slots. The pixel pipeline delays the coordinates and sync alongside the RAM read.
- `Font_Startup.bdf` controls the 8-bit U9 NOR read port, the startup loader and external SRAM ownership. The loader validates the header, mapping, payload CRC and SRAM readback CRC before handing the 512 KiB SRAM to scanout. During runtime the owner deasserts WE# and releases the FPGA data drivers. ASCII and missing-glyph bitmaps remain internal. The v1.2.0 font uses all 262,144 SRAM words. The 14 low Glyph ID bits select a 16-word slot and the four low address bits select its row. The glyph decoder selects the width from the two wide ID ranges and the intervening narrow range.

PS/2 is receive-only Set 2, validated and translated on the host. The VGA raster, 50 MHz display, 24 MHz UART PHY and memory ownership remain independent of the Linux application's output rate.
