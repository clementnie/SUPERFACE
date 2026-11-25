# SUPERFACE Phase 3 display implementation

`LAB8` instantiates the 50 MHz [Terminal_Display](../lab8_restored/Terminal_Display.bdf) hierarchy and drives the DE1's RGB444 DAC and active-low sync pins. The old 2,400 × 8 renderer and panel writer remain as lab source files. The board top has disconnected them. The VGA block keeps running on reset release even when the screen is hidden. KEY3 resets the display through two 50 MHz flip-flops.

The board schematic parks the display command ingress, font-valid signal and SRAM ownership until the packet engine and loader are connected. It powers up to a black VGA raster with no SRAM strobes and no FPGA DQ drivers. A separate `Phase3_Probe` project keeps the whole display datapath live for fitting. A separate `Phase3_Sim` project connects a bitmap fixture and drives only test signals from VWF. Neither diagnostic project belongs in the board image.

## Command interface

All [Screen_Commit](../lab8_restored/Screen_Commit.bdf) ports run on rising `Clk` (50 MHz). The future packet engine must finish length and CRC validation before staging a command. Cross UART bytes through the asynchronous FIFOs in the [wire contract](SUPERFACE_PROTOCOL.md). The display interface accepts synchronous local signals.

| Input or result | Contract |
| --- | --- |
| `Ready`, `Cmd_Valid` | Drive metadata and pulse or hold `Cmd_Valid` until a rising edge with `Ready=1`. Remove it after that edge. One request may be outstanding. Busy is the inverse of Ready. |
| `Push_Ready`, `Push`, `Push_Cell[23..0]` | A rising edge with both staging signals high appends one packed cell. Cells arrive in column order, at most 80. Ready for pushing is inhibited while Cmd_Valid is asserted. Allow one edge after the final push before command admission. |
| `Op[2..0]`, `Row[4..0]`, `Col[6..0]`, `Count[6..0]`, `Cursor_On` | Metadata is captured on admission. Coordinates are already narrowed to the listed widths. The packet engine must range-check the incoming byte fields before narrowing. |
| `Done`, `Result[2..0]` | Done pulses for one clock after command completion. Held result codes are 0 OK, 1 bad fields or snapshot row order, 2 bad state, 3 invalid resulting cells, 4 cancelled. Codes 0–3 map directly to protocol ACK status. Code 4 applies when a session was invalidated and its request is discarded. |
| `Invalidate` | Synchronous request independent of Ready. Cancels pending work, clears staged payload ownership and closes the snapshot. If a request was outstanding it completes with local result 4. A visible frame stays displayed until vertical blanking. During blanking visibility clears without waiting for another raster. |
| `Shown` | Logical whole-screen visibility. VGA also requires a valid line tag. |

| Op | Operation | Admission and completion |
| ---: | --- | --- |
| 1 | Begin snapshot | Empty payload, no snapshot currently receiving. At vertical-blank entry hide the old image, clear cursor visibility and set expected row to 0. |
| 2 | Snapshot row | An open snapshot, next row 0–29, column 0, count 80 and exactly 80 staged cells. Validate all 80 before writing any. Complete after the last write and advance the expected row. |
| 3 | End snapshot | Empty payload, valid cursor fields and 30 successful rows. At vertical-blank entry publish the grid and cursor together. |
| 4 | Span | A visible grid, valid row and start column, count 1–80 and matching staged count. The full-precision end column must be at most 80. At vertical-blank entry validate the resulting row, then write the span. |
| 5 | Cursor | Empty payload, visible grid and valid coordinates. At vertical-blank entry update row, column and visibility together. |

Staging is owned by the current command from admission through completion or cancellation. Completion releases the entire staged payload even on semantic error. The controller tests fields, state and snapshot row order, then cell data. A bad row leaves the grid and the expected row intact. For spans, the scanner reads the full resulting row, substituting staged cells only in the patch range, so it checks both old neighbors. Each lead must have an immediate same-color continuation within that row. A continuation elsewhere, a reserved ID or an unavailable Chinese ID fails validation. The grid accepts no writes during validation. Once writes start, they finish in vertical blanking. If invalidation cancels partially written data in blanking, the display is hidden and the next session must supply all 30 rows.

[Screen_Store](../lab8_restored/Screen_Store.bdf) uses 15 512 × 8 simple dual-port memories, organized in five banks for each of the three lanes. One write request updates all three lanes at the same address and clock edge. Addresses above 2,399 are rejected. Each RAM registers its read address, and the bank select and validity flop sample with it. Consumers use the output at the following edge. During writes the physical read offset is the complement of the write offset, with read validity cleared. The RAM array has no screen initialization dependency. Reset clears admission, snapshot, cursor and visibility state. Only a complete snapshot makes memory renderable.

The scan and write sequencers each use one request edge and one consume/write edge per cell. A full scan plus 80 writes takes 320 clocks (6.4 µs) after launch. A visible command receives the one `VBlank_Entry` pulse per frame. Snapshot rows can finish while hidden. Line 524 is reserved for prefetch rather than a visible update.

## Font and SRAM handoff

The existing [Font_ROM](../lab8_restored/Font_ROM.bsf) reads the unmodified `ascii_8x16.mif`. The address is `{glyph_id[6:0], local_y[3:0]}`, MSB left. Chinese lead range is `0x8000–0x9A46`. The [manifest](../assets/fonts/font_manifest.json) supplies count 6,727 and the mapping identity. The display enables Chinese admission and requests when `Font_Valid=1`, `Runtime_Owner=1` and `Font_Count=6727`. The future startup owner must compare the manifest mapping ID and validate the payload and SRAM readback before asserting these signals. The packet engine can leave Chinese disabled for an ASCII-only session. If font availability is lost during a session, invalidate the screen before the next session and relinquish SRAM when idle.

The builder issues `Req` when `Ready` is high and consumes the single `Rsp_Valid` pulse and `Rsp_Data[15..0]`. [SRAM_Read_Port](../lab8_restored/SRAM_Read_Port.bdf) accepts a request only with `Owner` high and `Idle` high. The address is held from acceptance through turnaround. On acceptance edge 0 the registered address is stable after FPGA output delay, CE# and both byte enables assert, and OE# stays high. OE# asserts after edge 1. Edge 8 captures DQ and disables strobes, giving nominal launch-to-capture budgets of 160 ns from address/CE and 140 ns from OE. One full 20 ns turnaround follows before Ready returns. WE# is high throughout. Top-level DQ is input-only in this phase.

The next loader must mux SRAM address and controls with mutually exclusive startup and runtime owners. It may drive DQ only under startup ownership during a write and must release it with inactive strobes before handing ownership over. Take ownership away from the runtime port only after Idle, including turnaround. Verify device access and release times at the installed speed grade and account for FPGA and board delays. The Probe constrains internal clocked paths. External SRAM read timing remains a board verification item.

## Scanout pipeline

[Raster_Timing](../lab8_restored/Raster_Timing.bdf) advances a pixel every two rising 50 MHz edges. It wraps x at 799, advances y there, and wraps y at 524. Active video is 640 × 480. HS# is low over x=659–755 and VS# over y=493–494, inclusive. RGB and both syncs are registered together for the coordinates sampled on the pixel-enable edge. In the intermediate system edge the line RAM registers the new cell address, so a cell boundary has a full 50 MHz cycle for the data to settle before the next pixel edge.

[Scanline_Builder](../lab8_restored/Scanline_Builder.bdf) reconstructs y+1 while line y displays, with line 0 built during line 524. It writes [two line buffers](../lab8_restored/Scanline_Cache.bdf), each with 80 used 16-bit entries. The high byte is color and the low byte is the glyph mask. Even and odd lines use separate banks. Scanout accepts only a complete buffer whose tag equals the next visible line at x wrap. A late or failed line forces black. When Chinese is disabled, the defensive renderer shows a fallback on a structural lead and background on the continuation. Orphan continuations always produce background.

| Group edge | Circuit action |
| ---: | --- |
| Start | Save target line tag and row base, initialize column and group phase. |
| 0 | Request current cell from the grid. |
| 1 | Capture cell and request its neighbor if in range. |
| 2 | Capture neighbor. |
| 3 | Latch lead/continuation classification and sample ASCII ROM address using the preserved glyph row nibble. |
| 4 | Capture ASCII ROM data or launch the bounded Chinese SRAM read for local y=2–13. |
| 12 | SRAM controller captures the requested word, eight clocks from launch. |
| 13 | Builder captures response bits 11–0 or marks the line invalid if an expected response did not arrive. |
| 14 | Write left cache entry. |
| 15 | Write right cache entry for a wide pair. |
| 18 | Advance one or two columns. Publish completion after the last group if no fault occurred. |

Chinese word address concatenates `glyph_id[13:0]` with `local_y − 2`, equivalent to `((glyph_id − 0x8000) << 4) | (local_y − 2)` for the guarded range. The wide mask is two zero bits, 12 glyph bits and two zero bits. It is fully zero during the top and bottom margin rows. A continuation uses the right half written by its lead. A row of 80 single cells takes (80 × 19 = 1,520) system clocks, leaving 80 clocks before the 1,600-clock line edge. Forty wide pairs take 760 clocks, including their SRAM reads. The separate [Pixel_Output](../lab8_restored/Pixel_Output.bdf) selects foreground or background from the mask, XORs the selector under the steady cursor at local y=14–15 and maps to the exact ANSI-order palette. The board drives VGA red from `RGB[11..8]`, green from `RGB[7..4]` and blue from `RGB[3..0]`.

## Build and validation

Use Quartus II 13.0 SP1 in a clean source-only copy of `lab8_restored`. The commands below assume its executables are on PATH and `repo` names the original workspace with the Phase 2 assets.

```sh
export QUARTUS_64BIT=1
quartus_sh --64bit --flow compile LAB8
quartus_sh --64bit --flow compile Phase3_Probe
python3 tools/verify_phase3.py fixture Phase3_Sim_Font.mif \
  --chinese "$repo/assets/fonts/chinese_sram.mif"
quartus_map --64bit Phase3_Sim --generate_functional_sim_netlist
python3 tools/verify_phase3.py vector --idle Phase3_Idle.vwf
quartus_sim --64bit Phase3_Sim --mode=functional --vector_source=Phase3_Idle.vwf \
  --check_outputs=off --simulation_results_format=VCD --write_settings_files=off
python3 tools/verify_phase3.py check --idle db/Phase3_Sim.sim.vcd
python3 tools/verify_phase3.py vector Phase3.vwf
quartus_sim --64bit Phase3_Sim --mode=functional --vector_source=Phase3.vwf \
  --check_outputs=off --simulation_results_format=VCD --write_settings_files=off
python3 tools/verify_phase3.py check db/Phase3_Sim.sim.vcd \
  --chinese "$repo/assets/fonts/chinese_sram.mif"
```

The simulation fixture extracts three glyph slots from the Phase 2 SRAM MIF, including its last assigned ID. It maps those fixtures into a diagnostic ROM addressed by the low eight bits of the real SRAM address. The fixture supplies simulated SRAM data, and the same font license notices apply to its glyphs. [Font licenses](../assets/fonts/LICENSES)

Probe uses automatic fitter locations and is for resource and internal timing measurement only. Use the pin-assigned `LAB8` build for the board.

For a shorter functional run through the fitted Cyclone II netlist, use Icarus Verilog and the Quartus vendor cell models. Set `quartus_dir` to the Quartus installation directory.

```sh
quartus_sh --64bit --flow compile Phase3_Sim
quartus_eda --64bit Phase3_Sim --simulation=on --tool=modelsim --format=verilog \
  --functional=on --output_directory=phase3_eda
python3 tools/verify_phase3.py stimulus --focused Phase3_Stimulus.v
iverilog -g2012 -s bench -o phase3_sim.out Phase3_Stimulus.v \
  phase3_eda/Phase3_Sim.vo "$quartus_dir/eda/sim_lib/cycloneii_atoms.v"
vvp phase3_sim.out
python3 tools/verify_phase3.py check --focused Phase3_external.vcd \
  --chinese "$repo/assets/fonts/chinese_sram.mif"
```

The generated testbench uses simulator force and release on the exported vertical counter to skip intervening lines. It checks selected intact scanlines with the fitted pixel pipeline, SRAM port, caches and command logic. Omit `--focused` from stimulus generation and checking for the full raster sequence. The Quartus vector above also runs the full raster.

The Probe fit uses **751 LEs, 257 registers and 22 of 52 M4Ks**. This is 15 grid M4Ks, two scanline buffers, one staging RAM and four classic ASCII ROM blocks. Board50 worst setup and hold slacks are +4.783 ns and +0.215 ns across slow and fast models. The board release build uses 149 LEs and 72 registers. It reports zero M4Ks while its unconnected ingress is parked because the fitter prunes the inactive datapath. Both full compiles pass. Quartus warns about unassigned Probe pins, one-bit LPM port notation, unused upper staging RAM bits and the legacy `SW[0]` clock assignment. Availability and timing of physical SRAM and the future 24 MHz UART remain separate verification items.

The 100 µs Quartus functional slice passed reset, horizontal sync, black RGB and inactive SRAM strobes. The focused post-fit run passed **29,600 pixel and sync samples, 42 command results, 43 complete scanline builds and 162 SRAM reads**. It matched the source font data, including the last screen cell, wide glyph margins and all 16 palette indices. It verified snapshot reveal, rejected writes covering invalid wide pairs, both cursor positions, atomic span commit, invalidation and reset. The measured worst build took **1,520 of 1,600 clocks**. The full unshortened raster regression did not finish during this phase. The bench results cover digital behavior. Board verification remains pending.

### First board check

Build a fresh `LAB8.sof` in the source copy, configure the DE1 over JTAG with RUN selected, and connect a VGA monitor and a scope. Confirm the blank image locks, HS repeats every 32 µs with an approximately 3.88 µs low pulse, VS repeats every 16.8 ms with two low lines, RGB is zero, and SRAM CE#, OE# and WE# stay high. Release KEY3 and repeat the check. The next visible hardware test requires a real synchronous command source. The Chinese hardware test also requires the Flash loader and validated SRAM handoff.
