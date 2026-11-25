# SUPERFACE UART protocol v1

## Negotiated frame batching and terminal glyphs

The v1 profile below continues to use its original message types and rules. An extended host initiates with type `03 EXT_HELLO`, sequence zero and the same 18-byte payload as `HELLO`. A legacy peer ignores it, and the host can retry with an ordinary `HELLO` using a fresh session ID. The extended response uses `HELLO_ACK` with capability bits 3 (batch updates) and 4 (extended glyphs). That produces capability byte `1F`. Plain `HELLO` still receives `07`.

| Type | Payload | ACK meaning |
| --- | --- | --- |
| `16 STAGE_SPAN` | Identical to `WRITE_SPAN` | The complete resulting row was validated, and the span was applied to the shadow grid. |
| `17 FRAME_COMMIT` | Identical to `CURSOR` | The staged grid and cursor were published together during VBlank. |
| `18 EXT_SNAP_BEGIN` | Empty | The snapshot starts with the extended cell rules enabled. |

Multiple staged spans can build a single visible update. The stage ACK does not wait for vertical blank. The FPGA copies the bounded 2,400-cell shadow grid into the existing visible screen store at VBlank entry in at most 4,800 system clocks, around 96 µs at 50 MHz, before line-zero prefetch. A cursor-only commit skips the copy. The host freezes a desired grid per transaction and compares the latest terminal state after each commit. Legacy spans and cursor commands require no staged frame to be pending. A host can drop the transaction by starting a new session and publishing a fresh snapshot.

CRC, ACK status, retry, sequence exhaustion, duplicate suppression and full-duplex keyboard scheduling use the existing rules. Each successful stage is acknowledged before the next command. A repeated identical commit sequence replays its result without a second visible update.

For the extended cell profile, `007F` is an internal single-width placeholder and `0080` is an internal double-width placeholder followed by a matching `FFFF` cell. The placeholders do not depend on the external font. In a validated font session, IDs `8000–9ABB` retain their wide semantics. IDs `9ABC–9D47` are one cell wide and use 16 SRAM rows with masks in bits 7–0. The manifest defines the exact allocation and mapping identity. The host preserves printable `003F` and uses the dedicated placeholders for unsupported characters under the extended profile.

The Orange Pi initiates sessions and sends display state. The DE1 returns command results and PS/2 data. The [architecture](SUPERFACE_ARCHITECTURE.md) defines cells, rendering and font assets.

## Physical link

The operational link is fixed at **3,000,000 baud**, full duplex, **8N1** (eight data bits, no parity, one stop bit), LSB first, idle-high and non-inverted at **3.3 V logic levels**. There is no automatic rate fallback, RTS/CTS or software flow control. Cross TX and RX and share ground. Use short wires with a nearby ground return and independently powered boards.

| Source | Destination |
| --- | --- |
| Orange Pi Zero 2W UART2_TX (PI5, physical pin 15) | DE1 GPIO_0[1] (JP1 pin 2, FPGA B13) |
| DE1 GPIO_0[2] (JP1 pin 3, FPGA A14) | Orange Pi Zero 2W UART2_RX (PI6, physical pin 22) |
| Orange Pi pin 14 GND | DE1 JP1 pin 12 GND |

The expansion header carries the selected 3.3 V signals and both pins are unused by the existing schematic. Connect this cable after loading a build that explicitly assigns the new RX/TX pins. Use only the listed GPIO pins for the FPGA UART. F14/G12, the DE1 DB-9 and its onboard RS-232 transceiver are excluded. Leave both boards’ supply pins disconnected from the link. Bias disconnected RX inputs high on their local sides. Verify thresholds, pin orientation and the effect of either board being unpowered. Physical live insertion/removal requires an interconnect qualified for it, including power-off isolation where necessary. Here **hot plug** means software recovery when valid UART traffic returns after a disconnect or endpoint restart. UART itself supplies no cable-presence signal. [Board pin assignments](../lab8_restored/LAB8.qsf), [DE1 manual figs. 4.10, 4.16](https://www.terasic.com.tw/attachment/archive/83/DE1_UserManual_v1018.pdf), [Orange Pi UART2 guide](SUPERFACE_UART2.md)

### Orange Pi UART2 setup

Use the [UART2 recovery and validation procedure](SUPERFACE_UART2.md) to stage the Manjaro DTB and select the PI5/PI6 pin group. Resolve the Linux tty through sysfs to `serial@5000800` at MMIO `0x05000800`. Reserve UART0 and its CH340 console, and keep the link tty free of consoles and gettys. Open the verified tty exclusively. Apply raw termios at `B3000000` with `CS8 | CREAD | CLOCAL`, clearing parity, extra stop bits and both hardware and software flow control. Read back both speeds and framing.

The H616 UART uses an integer 16× divisor from the APB2 reference. A 24 MHz reference tops out at 1.5 Mbaud. 48 MHz would yield 3 Mbaud with divisor 1. APB2 and its parents have shared consumers. Review the running clock tree before changing rates. Use a calibrated scope or logic analyzer on PI5 to verify the nominal 333.333 ns bit period using the diagnostic `0x55` stream. Kernel readback and self-loopback provide separate evidence from measured wire timing. [Linux 6.9 H616 clock tree](https://github.com/torvalds/linux/blob/v6.9/drivers/clk/sunxi-ng/ccu-sun50i-h616.c), [Allwinner H616 UART driver evidence](https://lkml.iu.edu/hypermail/linux/kernel/2611.0/03985.html)

See the [FPGA clocking and sampling design](SUPERFACE_ARCHITECTURE.md#uart-clock-domains) for the 24 MHz PHY and clock-domain crossings. Qualification requires each endpoint’s average wire baud to be within ±1% of 3,000,000 (2.970–3.030 Mbaud) and the two measured bit periods to differ by at most 2% in either ratio. These are acceptance limits for real clocks, cabling and driver behavior.

## Frame encoding

Send a leading `7E`, the escaped body, and a trailing `7E`. In the body, replace `7E` with `7D 5E` and `7D` with `7D 5D`. This applies to the CRC too. The table gives unescaped offsets. `u16`, `u32` and `u64` use little-endian byte order. Byte arrays retain their listed order. All payload lengths below count unescaped bytes.

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 1 | Version `01` |
| 1 | 1 | Packet type |
| 2 | 8 | Nonzero host-selected session ID, u64 |
| 10 | 4 | Sequence, u32 |
| 14 | 1 | Payload length `L`, 0–243 |
| 15 | `L` | Payload |
| `15 + L` | 2 | CRC-16 in little-endian byte order |

CRC-16/CCITT-FALSE (CRC-16/IBM-3740) has width 16, polynomial `0x1021`, initial `0xFFFF`, non-reflected input and output, and final XOR `0x0000`. Cover unescaped bytes 0 through `14 + L`, in order. ASCII `123456789` yields `0x29B1`. The largest body is 260 decoded bytes and at most 522 wire bytes including delimiters. Each frame has 19 bytes of fixed overhead before escaping.

After reset, hunt for `7E`. Every delimiter finishes the current candidate and arms the next. Ignore empty candidates, including repeated delimiters. A delimiter while awaiting an escape suffix aborts the candidate and arms the next. Reject an invalid escape suffix, oversized declared length, excess bytes, UART framing error, reported tty overrun or truncation. Drop partial candidates after 100 ms without receiving a byte while building one. The FPGA places a stop-bit error marker in the receive FIFO in stream order so the parser invalidates the affected frame. After an error or timeout, discard through the next delimiter. Store only the bounded payload and header, incrementally update the CRC, and wait for the closing delimiter and exact body length before dispatch. Corrupt frames, wrong version, zero session, wrong direction, unknown types and packets outside the selected session are silently dropped. Traffic may go back-to-back. No inter-frame delay or Linux userspace byte timing is required. A subsequent intact framed packet can resynchronize the parser.

## Packets

In the table, H is the Orange Pi and F is the FPGA. A cursor payload is `row:u8, col:u8, visible:u8`. Row is 0–29, column is 0–79, visibility is 0 or 1. Hidden cursors also carry in-range coordinates. Cell records use the three bytes specified in the [architecture](SUPERFACE_ARCHITECTURE.md#glyph-ids-and-cell-storage).

| Type | Direction | Sequence | Payload in order |
| --- | --- | --- | --- |
| `01 HELLO` | H→F | 0 | `wanted_count:u16, wanted_mapping:16 bytes` (18) |
| `02 HELLO_ACK` | F→H | 0 | `result:u8, font_status:u8, columns:u8, rows:u8, cell_bytes:u8, max_payload:u8, capabilities:u8, loaded_count:u16, loaded_mapping:16 bytes` (25) |
| `10 SNAP_BEGIN` | H→F | Reliable | Empty |
| `11 SNAP_ROW` | H→F | Reliable | `row:u8`, followed by 80 cells (241) |
| `12 SNAP_END` | H→F | Reliable | Cursor (3) |
| `13 WRITE_SPAN` | H→F | Reliable | `row:u8, start_col:u8, count:u8` followed by `count` cells (`3 + 3 × count`, up to 243) |
| `14 CURSOR` | H→F | Reliable | Cursor (3) |
| `15 PING` | H→F | Reliable | Empty |
| `20 KEY_EVENT` | F→H | Reliable | `kind:u8`, then 1–16 raw PS/2 bytes for kind 0, or no more bytes for kind 1 |
| `7F ACK` | Both | Echoed | `request_type:u8, status:u8` (2) |

### Handshake and capabilities

The host chooses a fresh random nonzero 64-bit session ID using the OS random source for each connection attempt, never intentionally reusing one. Flush the tty’s pending queues on open/reopen. A fresh handshake requests an exact Chinese mapping using a count of 1–16,384 and nonzero 16-byte ID, or ASCII-only using count 0 and sixteen zero bytes. Ignore a malformed HELLO, including mixed zero/nonzero count and mapping or the wrong sequence. The FPGA listens for HELLO once the font startup attempt has completed. A new well-formed session ID supersedes any previous session, including during an interrupted snapshot. It cancels pending commands, clears the sequence and key state and schedules black at the next vertical blank. It may finish the single frame already submitted to the PHY. The host filters by session ID.

The FPGA responds with `HELLO_ACK` using the candidate session ID. Capabilities must be `0x07` in protocol v1. Bit 0 is PS/2 Set 2 byte forwarding, bit 1 is vertical-blank span commit, and bit 2 is Chinese loading support. All other bits are zero. Columns, rows, cell bytes and max payload are 80, 30, 3 and 243. The host checks all these fields.

| HELLO_ACK result | Meaning |
| --- | --- |
| 0 | ASCII-only accepted. Use only printable ASCII cells. |
| 1 | Chinese accepted. A validated font is loaded and its count and mapping equal the request. |
| 2 | Mapping unavailable or mismatched. The candidate is rejected. Reconnect with a new ID and the ASCII-only request. |

| Font status | Meaning |
| --- | --- |
| 0 | Image loaded and validated. Report its actual count and mapping whether or not Chinese was requested. |
| 1 | Missing (all-`FF` header). |
| 2 | Incompatible format or firmware mapping. |
| 3 | Corrupt header, padding, payload or SRAM readback. |
| 4 | Startup watchdog expired. |

Report zero count and zero mapping for font status 1–4. A Chinese session requires the host to verify result 1, status 0, and its exact count/ID. An ASCII request accepts only result 0 and consistent status/count fields. Result 2 permits the defined ASCII retry only for a Chinese request. Unexpected values or incompatible geometry/capability fields cause the host to discard that connection attempt. A HELLO retry with identical contents and the same current candidate ID replays the original HELLO_ACK without resetting state. A changed HELLO for that same ID is ignored. A rejected offer holds no command state. The host retries HELLO with the same candidate every 250 ms up to eight total sends, then chooses a fresh ID and resumes probing. Allow one outstanding HELLO per candidate.

### Display command semantics

- In **Await snapshot**, admit `SNAP_BEGIN`. In **Active**, it starts a new replacement snapshot. At the next vertical blank after acceptance, hide output and reset the expected snapshot row to 0. ACK after the transition.
- In **Receiving snapshot**, `SNAP_ROW` must equal the next expected row. Validate all 80 cells before writing that row. ACK after the write and increment the expected row. Partial snapshots are hidden. An invalid row leaves the expected row and screen storage unchanged. An early `SNAP_END` fails.
- In **Receiving snapshot** after 30 successful rows, `SNAP_END` commits the new grid and its cursor together at the next vertical blank and enters **Active**. ACK after commit, before the new frame has necessarily reached the monitor.
- In **Active**, `WRITE_SPAN` replaces `count` consecutive cells in one row. Require row and start column in range, `1 ≤ count ≤ 80`, exact payload length and `start_col + count ≤ 80` without arithmetic wrap. In the resulting row, every lead must have an immediate same-color continuation and every continuation must have a matching lead. Use the unchanged neighbors when checking both patch edges. Every ID must be valid for the negotiated repertoire. Reject the whole command on failure. Stage the packet and, within the chosen vertical blank, validate the candidate row and apply all writes before the line-0 prefetch. ACK after commit or rejection.
- In **Active**, `CURSOR` changes only the cursor and ACKs after vertical-blank commit. `PING` is valid in all three accepted session states and ACKs immediately.
- Other valid command types received in the wrong display state return `BAD_STATE`. A second `SNAP_BEGIN` during **Receiving snapshot** returns `BAD_STATE`. A duplicate with the original sequence remains subject to the replay rule below. The host uses a fresh handshake to recover after an error and resends a complete snapshot.

The host captures a coherent grid and cursor from its terminal state at snapshot start. It continues serving its PTY and queues or coalesces later changes until the snapshot ACK. Those changes use normal incremental commands. The FPGA presents either black or a complete snapshot. Within each visible frame a span and its wide pairs are consistent. Multi-command updates can appear in successive frames.

### Delivery, flow control and connection loss

Each accepted session starts two independent reliable sequence spaces at 1, one initiated by each endpoint. Each initiator keeps at most one outstanding reliable request, sending the next only after its own matching ACK. `ACK` is outside both sequence spaces, carries the acknowledged sequence and is never acknowledged. Control replies may cross a reliable request in flight. Send queued control replies before starting new reliable transmissions. The serializer finishes one complete frame before starting the next, and ACK handling never waits for the opposite endpoint’s outstanding transaction to complete. Each endpoint’s transmit path may have at most one frame queued to the physical serializer and must give a newly pending control reply priority at the next frame boundary. The FPGA retains one pending ordinary ACK descriptor and one pending HELLO_ACK descriptor. Coalesce a duplicate reply with one already pending or transmitting. On admitting the next reliable sequence, drop any unsent replay ACK for the preceding sequence. The next request proves the preceding ACK was received. A fresh HELLO replaces the candidate and clears older pending replies. The sender waits for command ACKs even while its UART can accept more bytes.

For a recognized reliable type, process only the next expected sequence. For that sequence, semantic validation yields one of the ACK statuses below. An error produces no requested side effect and consumes the sequence. Cache the last completed sequence, type, request CRC and ACK status. While its side effects are pending, ignore a duplicate. After completion, resend the cached ACK for a retry with matching sequence, type and CRC without reapplying it. Silently drop all other sequences. A sender always retransmits the same bytes after a timeout. A receiver accepts only defined statuses from an ACK with the current session, sequence and outstanding request type. Reserve sequence zero for handshake and renew the session before using a reliable sequence after `0xFFFFFFFF`. Either endpoint can drop the session at sequence exhaustion so the host can renew it.

| ACK status | Meaning |
| --- | --- |
| `00 OK` | Command completed or keyboard payload accepted. |
| `01 BAD_PAYLOAD` | Wrong type-specific length, bounds, cursor field, keyboard kind, or snapshot row order. |
| `02 BAD_STATE` | Command is incompatible with the current endpoint state. |
| `03 BAD_CELLS` | Invalid Glyph ID, unsupported repertoire, or invalid wide pair in the resulting row. |

Check type-specific length and field/range rules first, then state, then cell data. A retry uses a 100 ms ACK deadline measured from the end of that transmission, with three retransmissions maximum. A valid matching ACK ends the retry. A semantic error triggers a fresh handshake at the host, or drops the session at the FPGA for an FPGA-originated request. After retry exhaustion, abandon the session. Any accepted session also expires after two seconds without an admitted reliable request, matching duplicate request, or matching ACK from the peer. Identical replayed HELLOs do not refresh that timer. The host sends a reliable PING if it has initiated no reliable request for 500 ms and has none pending. Either endpoint drops the session on I/O failure. On expiry the FPGA cancels pending state, stops key delivery and hides the screen/cursor by the next frame boundary. The host clears its keyboard decode state, keeps its logical terminal screen while running, and reopens or reprobes with a fresh ID. An FPGA that resets while the host stays running will ignore the old session. The host’s retry or heartbeat discovers the reset and performs a fresh snapshot. If the Linux process itself restarts, the new host process sends the complete screen from its newly available terminal state.

| Endpoint | State progression |
| --- | --- |
| Host | **Probe** sends HELLO until accepted. **Snapshot** sends begin, rows and end, waiting for each ACK. **Active** sends spans/cursor and services keys. Timeout, incompatible offer or semantic error returns to **Probe**, with ASCII fallback on result 2. |
| FPGA | **Boot** runs the font attempt. **Listen** answers HELLO. An accepted HELLO enters **Await snapshot**. An accepted begin enters **Receiving snapshot**, and end enters **Active**. A fresh HELLO from any post-boot state replaces the candidate. Session loss returns to **Listen**. KEY3 reset returns to **Boot**. |

### Keyboard stream

The existing PS/2 pins and Set 2 codes carry forward. The terminal receiver is a receive-only module on the 50 MHz clock, with its interfaces visible in BDF. Synchronize clock/data, sample aligned data on PS/2 falling edges, and validate an 11-bit frame with start 0, eight data bits LSB first, odd parity and stop 1. Time out a partial PS/2 frame 2 ms after its last edge. Use a keyboard that powers up in Set 2. This version sends no keyboard commands and leaves keyboard LEDs under the keyboard’s own behavior. [Existing keyboard](../lab8_restored/Keyboard_7_Segment.vhd), [IBM PS/2 hardware interface reference](https://bitsavers.org/pdf/ibm/pc/ps2/Personal_System_2_Hardware_Interface_Technical_Reference_May88.pdf)

In **Active**, kind 0 carries raw validated bytes in order. A message can end between prefix and code. The host persists prefix and held-key state between packets, decodes ordinary makes, `F0` releases, `E0` extended keys and break sequences, and the special Pause (`E1`) and Print Screen sequences. For example A sends `1C` on make and `F0 1C` on release. Left/right Shift, Ctrl and Alt are individual Set 2 keys (Shift `12`/`59`, Ctrl `14`/`E0 14`, Alt `11`/`E0 11`). The host updates modifiers, locks and repeat from the ordered stream and handles scan-code mapping, layout and terminal key translations. Typematic makes for a held key repeat without toggling a lock again. A release for an untracked key is ignored. Treat BAT `AA` as a decoder reset. Discard invalid or unfinished prefix sequences after 250 ms from the last delivered scan byte.

The FPGA queues 32 validated bytes plus up to 16 bytes held separately for retry. When the reliable transmit slot is free, send up to 16 bytes from the queue immediately. A framing/parity error, PS/2 partial-frame timeout or FIFO overflow leaves any already in-flight request intact, flushes the queued bytes and schedules one reliable kind-1 stream reset after the in-flight ACK. Discard incoming bytes while the reset is pending or in flight. Resume capture on a new PS/2 frame after both reset ACK and at least 2 ms with clock and data high. The host clears prefix, held keys, modifiers and lock state on kind 1 and session loss, and ACKs a kind-1 message the same way as kind 0. It applies each delivered event once per session. The FPGA discards PS/2 data while the display is inactive and uses the same idle qualification before re-enabling capture after snapshot commit. Keystrokes while disconnected, during a snapshot or after an overflow can be lost. The host clears keyboard state when sending `SNAP_BEGIN` and ignores any pre-snapshot events while synchronizing, acknowledging their valid frames to release the transmit slot. The FPGA also flushes queued bytes when entering the snapshot and finishes any already in-flight key transaction before acknowledging `SNAP_END`.

## Bandwidth and storage

8N1 uses ten wire bits per byte, yielding 300,000 wire bytes/s per direction at nominal rate. A byte takes 3.333 µs, or 80 cycles at 24 MHz and about 166.67 cycles at 50 MHz. The following serialization sums both directions for one stop-and-wait exchange. Counts include delimiters and CRC and exclude escapes except where specified.

| Exchange | Request bytes | Reply bytes | Nominal serialization | Conservative stuffed bound |
| --- | ---: | ---: | ---: | ---: |
| HELLO and HELLO_ACK | 37 | 44 | 270.0 µs | 526.7 µs |
| One Latin cell | 25 | 21 | 153.3 µs | 293.3 µs |
| One Chinese pair | 28 | 21 | 163.3 µs | 313.3 µs |
| 16-cell span | 70 | 21 | 303.3 µs | 593.3 µs |
| 80-cell span | 262 | 21 | 943.3 µs | 1.873 ms |
| Cursor | 22 | 21 | 143.3 µs | 273.3 µs |
| Keyboard stream reset | 20 (FPGA) | 21 (host) | 136.7 µs | 260.0 µs |
| Keyboard, one raw byte | 21 (FPGA) | 21 (host) | 140.0 µs | 266.7 µs |
| Keyboard, 16 raw bytes | 36 (FPGA) | 21 (host) | 190.0 µs | 366.7 µs |
| Full snapshot, already connected | `19 + 30 × 260 + 22 = 7,841` | `32 × 21 = 672` | 28.377 ms | 56.327 ms |

An escape adds one wire byte for each body byte equal to `7D` or `7E`. For an unescaped frame of `U` bytes, `2U − 2` is a conservative bound because the two delimiters never expand. For maximum-length frames this budgets 260 decoded body bytes and 522 wire bytes, up to 1.740 ms. A v1 maximum-length span is bounded more tightly by 519 wire bytes because version, type and length cannot expand. The conservative full-snapshot bound is 16,898 wire bytes. Before escaping the 32 ACKs account for 672 bytes or 2.240 ms of serialization. The verified blank snapshot below contains zero stuffed bytes.

Serialization excludes FIFO crossing, validation, ACK formation, foreground process scheduling, and VGA. For an accepted visible span or cursor, add up to one 16.8 ms frame period waiting for the vertical-blank slot and the short commit operation before ACK. A snapshot has two such waits, for begin and end. Its nominal wire calculation plus worst frame phase is 61.98 ms for the reference snapshot and 89.93 ms using the conservative escaping bound, before processing and host scheduling. Snapshot rows commit while hidden and do not each incur a frame wait. The display starts scanning the committed screen after blanking. An old keyboard event still awaiting its ACK can also delay snapshot completion. Cursor and span updates can use at most one visible commit per frame (about 59.5/s). The keyboard uses its separate reliable request slot. A control reply can be delayed by the one frame already being transmitted and by OS scheduling. For example, a host keyboard ACK can be queued behind up to 1.740 ms of display frame on the host TX wire. The 190 µs ideal batch exchange corresponds to roughly 84,200 scan bytes/s before escaping, independent of the physical PS/2 rate and subject to ACK scheduling.

### Parser, staging and backpressure

- Use the separate 16-entry PHY RX and TX asynchronous FIFOs defined in the [architecture](SUPERFACE_ARCHITECTURE.md#uart-clock-domains). Budget one RX parser token per 16 clocks at 50 MHz, including dequeue, de-escape/length handling, up to eight serial CRC steps and a synchronous byte write. Keep that path independent of TX encoding and live display reads/writes.
- The parser writes up to 243 payload bytes to its own scratch RAM. After a valid row/patch candidate closes, use a synchronous read pipeline to copy its cell bytes into the separate 80 × 24 staging RAM, packing three bytes into each cell. Allow up to 256 system clocks (5.12 µs), including dispatch and copy. Holding the parser for that short interval while it owns scratch fits in 16 FIFO entries. Include FIFO flag/read latency and byte phase in the budget. At the fastest allowed wire rate, fewer than four entries are needed for the pause and pipeline latency when the FIFO was already draining. The parser catches up at one token per 16 clocks, at least ten times the allowed wire arrival rate at the nominal system clock. The 16-entry FIFO provides about 53 µs of buffering from empty at nominal wire rate. ACK and HELLO handling need no full payload copy and dispatch using bounded header and payload fields.
- After staging, release scratch for further frames even if a display command is still waiting for vertical blanking. A pending span remains in staging until validated and committed. A hidden snapshot row validates from staging and then writes the grid. Drive the screen work with a separate state machine. It must never block draining the PHY FIFO during the vertical-blank wait, a keyboard ACK, or reply transmission. While a command is pending, its sender waits for the matching ACK. The receiver consumes crossed keyboard ACKs, drops pending duplicates after parsing and can supersede the command on a valid fresh HELLO. It never writes staging for an unadmitted request.
- TX encodes a frame into its 16-entry FIFO no slower than one wire byte per 16 system clocks while it has space. It can compute the outgoing CRC as it encodes. Prefill before starting the UART shifter and refill concurrently without waiting for receive or display work. Hold a reply descriptor until it can be encoded. The one-request window and priority for replies bound the command and reply storage. The host drains its tty independently of the PTY and snapshot work, assembles frames incrementally with the same bounds and handles incoming control and key frames while its own command awaits ACK.
- RX FIFO full and TX starvation within a frame are link faults. Record them, discard the affected stream state and recover as described in the [architecture](SUPERFACE_ARCHITECTURE.md#uart-clock-domains). A legal transfer, including crossed ACKs and retries, must leave these counters unchanged. The PS/2 queue remains 32 raw bytes plus up to 16 in flight. A prolonged host delay can still trigger the existing keyboard stream reset.

### Timer rationale and reconnect latency

Retain the 100 ms incomplete-frame idle timeout and 100 ms command ACK deadline, with three retransmissions. A maximum frame takes at most 1.740 ms at nominal rate. The ACK deadline covers a full VGA commit wait, one transmit frame ahead of a control reply, FPGA work and reasonable host scheduling stalls. Begin the retry deadline at the last stop bit of each request. The FPGA uses the PHY completion indication. On the host, account for kernel/driver output queuing by using a transmit drain/completion indication before starting the deadline, while keeping receive processing available. A sender may recover sooner on an I/O error.

Retain the 500 ms host idle PING, two-second peer inactivity expiry and 250 ms HELLO retry interval (eight sends per candidate). An idle host detects an unresponsive FPGA after up to 500 ms to its first PING and about 400 ms for four ACK deadlines, plus transmission and scheduling. The FPGA independently hides the screen by the next frame boundary after session expiry. When a peer returns, a ready FPGA can answer the first valid HELLO. If the first probe misses readiness, allow up to one 250 ms interval to the next probe during probing, plus HELLO serialization, the new snapshot and host scheduling. An FPGA reset also repeats font startup under the one-second watchdog. This startup, link detection, and probe scheduling can overlap. The rate change does not shorten the VGA or startup timers.

## Bench validation

These tests are acceptance criteria for the installed hardware and Linux image. They have yet to be run.

1. **Pins and clocks.** Confirm DE1 revision, B12 as `CLOCK_24[0]`, both GPIO assignments and Orange Pi UART2 PI5/PI6 pinmux. Check the 24 MHz source at power-up with the USB-Blaster cable disconnected, including the planned power and reset states. Confirm clock and CDC constraints in the Quartus fit. Verify logic levels and header orientation before connecting the signals. Use short 3.3 V wiring with a ground return close to the signal pair.
2. **Endpoint loopback.** Loop TX to RX on each board in isolation (DE1 using an FPGA UART diagnostic build and the Orange Pi using the configured tty). Send `00`, `FF`, `55`, `AA` and a repeatable byte stream with byte-for-byte verification. Require the correct tty readback and zero unexpected framing, parity or overrun errors and zero mismatches. Record Linux `TIOCGICOUNT` deltas if supported. With unsupported counters, use a diagnostic path that reports driver errors plus an independent analyzer capture. A same-clock loopback checks function but cannot establish the absolute baud. [Linux tty counters](https://www.kernel.org/doc/html/v7.0-rc2/driver-api/tty/tty_driver.html)
3. **Connected waveform.** With both endpoints and a common ground, scope `55` and patterns with long high/low runs from each TX, at the receiving pins. Measure bit period, amplitude and threshold crossing quality. Pass the ±1% absolute and 2% relative timing limits specified above in the intended power states and during normal CPU load. Verify idle high, one stop bit and no ringing that recrosses the receiver threshold. Record the measured rates and equipment/sample resolution.
4. **Sustained full duplex.** Use a diagnostic mode at both ends to exchange independent repeatable streams with byte counts and CRCs, continuously in both directions for at least 60 seconds. For this diagnostic, provide a continuous data source and sink at each endpoint through the same UART PHY and FIFOs. Use runs of consecutive 8N1 characters at wire rate and log the longest gaps and receive FIFO high-water levels. Pass with identical TX/RX counts and CRCs, zero unexpected framing errors, integrity failures, FIFO overruns or TX starvation, and occupancy below full in the simultaneous stream. Instrument FPGA error and FIFO flags and host driver/decoder counters so drops are observable.
5. **Framing limits.** Send maximum-length legal spans using tilde IDs with `7D` and `7E` color bytes. Drive the parser with a CRC-correct 243-byte test payload dominated by escape bytes, including session/sequence bytes requiring escaping. Check the full sizing bound with back-to-back frames and no inter-frame gap. A transport-valid but semantically invalid body must be rejected without a screen write. Deliberately inject bad CRC, truncated escape, a low stop bit and an overlong frame. Return RX to idle high, then send intact traffic. Pass with the expected discards and recovery at the next intact frame, no silent data corruption and no FIFO overflow during the legal stream.
6. **Combined operation.** Resynchronize a full screen, then update spans and cursor while typing and repeating keys. Compare the published snapshot counts and measured wire time with the captured traffic. Check complete snapshot reveal, atomic span commits, command ACK order, and exactly-once delivery across induced retransmissions. Log command-to-ACK and first visible frame separately. Pass with correct display and keys, no unexpected integrity/framing errors or overruns, and FPGA display commits within the specified vertical-blank schedule.
7. **Recover.** Reset each endpoint in turn with the wires attached. Interrupt a snapshot and disconnect/reconnect the data path using the qualified wiring. Verify parser recovery, recorded link-loss and handshake times, fresh session, no accepted stale frames, and restoration from a complete snapshot. Confirm the screen hides on FPGA expiry and keyboard state clears. Expected errors during deliberate fault injection must be distinguishable from errors after recovery.

## Byte-level examples

The examples use session `0x0807060504030201` and an ASCII-only offer on a board with erased user Flash. Each line is one complete frame in hexadecimal, including delimiters. The incremental update follows an implicit successful full snapshot using host sequences 1–32. The keyboard event is the first reliable FPGA request in that session.

| Frame | Payload bytes | Wire bytes | CRC value |
| --- | ---: | ---: | --- |
| HELLO | 18 | 37 | `0x0D65` |
| HELLO_ACK | 25 | 44 | `0x73E9` |
| WRITE_SPAN (row 0, col 0, bright red A on blue) | 6 | 25 | `0xF15A` |
| ACK for WRITE_SPAN | 2 | 21 | `0x667A` |
| KEY_EVENT (A make and release) | 4 | 23 | `0x6AF7` |
| ACK for KEY_EVENT | 2 | 21 | `0x584A` |
| WRITE_SPAN (row 0, col 1, tilde with default colors) | 6 | 26 | `0x636F` |

```text
7E 01 01 01 02 03 04 05 06 07 08 00 00 00 00 12 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 65 0D 7E
7E 01 02 01 02 03 04 05 06 07 08 00 00 00 00 19 00 01 50 1E 03 F3 07 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 E9 73 7E
7E 01 13 01 02 03 04 05 06 07 08 21 00 00 00 06 00 00 01 41 00 49 5A F1 7E
7E 01 7F 01 02 03 04 05 06 07 08 21 00 00 00 02 13 00 7A 66 7E
7E 01 20 01 02 03 04 05 06 07 08 01 00 00 00 04 00 1C F0 1C F7 6A 7E
7E 01 7F 01 02 03 04 05 06 07 08 01 00 00 00 02 20 00 4A 58 7E
7E 01 13 01 02 03 04 05 06 07 08 22 00 00 00 06 00 01 01 7D 5E 00 07 6F 63 7E
```

A temporary check encoded each frame, decoded it back to the stated fields and compared a bitwise CRC implementation with Python’s `binascii.crc_hqx`. It also encoded all 64 frames of a snapshot containing 2,400 default spaces and a hidden cursor at (0, 0), using the same session. That encoded transfer contained 7,841 host bytes and 672 FPGA bytes after escaping, giving 28.377 ms of serialization at the specified nominal rate.
