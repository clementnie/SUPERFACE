# SUPERFACE architecture

The Quartus II 13.0 SP1 project targets the Terasic DE1's Cyclone II EP2C20F484C7. The top-level `LAB8.bdf` shows the display, Flash/SRAM ownership, keyboard receiver, UART PHY and clocks. The original lab circuits remain in the project source. VHDL implements protocol and control internals. Matching BSF symbols expose those blocks in the schematics. Quartus-generated ROM and FIFO sources are vendor IP collateral.

## Linux host

The Orange Pi Zero 2W runs a C backend using a POSIX PTY and libvterm. The host translates terminal state into 80 × 30 three-byte cells, quantizes colors to the fixed ANSI palette, tracks damage, and sends PS/2 Set 2 input into the PTY with the selected keyboard layout. The privileged systemd launcher delegates authentication to Linux login and PAM, then the renderer runs as the dedicated service account. Local terminal operation requires UART2 and the FPGA.

## UART clock domains

`UART_PHY.bdf` places 3 Mbaud 8N1 sampling and serialization in the 24 MHz domain. Two dual-clock FIFOs connect it to the 50 MHz parser and serializer in `UART_Link.bdf`. The reliable host and key directions use separate sequence spaces. A CRC-16 protects each frame. Session renewal discards interrupted staging and restores the visible state with a fresh snapshot. See the [protocol](SUPERFACE_PROTOCOL.md) for the wire formats and timing.

## Display and font access

- `Terminal_Display.bdf` connects raster timing, command control, the visible grid, the scanline builder, the paired line cache and RGB444 output. VGA runs at 640 × 480 with 25 MHz pixel enable on the 50 MHz system clock.
- `Grid_Commit.vhd` validates candidate rows, writes a bounded 2,400 × 24 shadow grid, and copies it to the visible store in at most 4,800 system clocks from VBlank entry. The snapshot staging RAM holds one row. The same VBlank installs the cursor. The visible store is a separate schematic with its own banked M4K RAM.
- `Scanline_Builder.bdf` uses a fixed 19-clock group per single cell or wide pair. An all-single scanline requires 1,520 of 1,600 clocks. The narrow and wide font paths use the same SRAM transaction slot, launched at phase 4 and consumed at phase 13. The final two stages write the left entry and optional continuation entry. The builder creates line zero during raster line 524.
- `Font_Startup.bdf` controls the 8-bit U9 NOR read port, the startup loader and external SRAM ownership. The loader validates the header, mapping, payload CRC and SRAM readback CRC before handing the 512 KiB SRAM to scanout. During runtime the owner deasserts WE# and releases the FPGA data drivers. ASCII and missing-glyph bitmaps remain internal.

PS/2 is receive-only Set 2, validated and translated on the host. The VGA raster, 50 MHz display, 24 MHz UART PHY and memory ownership remain independent of the Linux application's output rate.
