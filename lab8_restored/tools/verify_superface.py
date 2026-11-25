#!/usr/bin/env python3
"""Prepare Quartus II waveform stimuli and check the resulting VGA pin VCD."""

import argparse
from collections import Counter
from pathlib import Path
import re

DURATION_NS = 16_832_000
PIN_CLOCK = "CLOCK_50"
PIN_SYNC = ("VGA_HS", "VGA_VS")
PIN_RGB = tuple(f"VGA_{c}[{i}]" for c in "RGB" for i in range(4))
PIN_INPUTS = (
    "CLOCK_24[0]", "PS2_CLK", "PS2_DAT",
    *(f"SW[{i}]" for i in range(10)),
    *(f"KEY[{i}]" for i in range(4)),
)

# Each entry sets the panel switches, then presses one hardware-debounced KEY.
# Switching to 'B' with KEY0 held checks that a long press produces one write.
PANEL_ACTIONS = (
    (0, 0x41, 0, 55, 705),
    (350, 0x42, None, 0, 0),
    (1300, 0x4F, 1, 1555, 2005),
    (2250, 0x5A, 0, 2455, 2805),
    (3250, 0x50, 1, 3455, 3805),
    (4250, 0x3F, 0, 4455, 4805),
    (5250, 0x09, 2, 5455, 5805),
    (6250, 0x5F, 1, 6455, 6805),
    (7250, 0x23, 0, 7455, 7805),
    (8250, 0x60, 1, 8455, 8805),
    (9250, 0x58, 0, 9455, 9805),
)

# Expected writes at the falling 50 MHz edges, including cell 0 while read.
# The final press targets 2400 and must never assert the RAM write input.
WRITES = ((100, 0, 0x41), (2500, 79, 0x5A), (4500, 80, 0x3F), (7500, 2399, 0x23))
PANEL = "|LAB8|Panel_Write:Board_Controls|"
WRITE_ENABLE = PANEL + "Write_If_Valid"
ADDRESS_BITS = tuple(
    f"{PANEL}lpm_ff:Address_{'Low' if i < 8 else 'High'}|dffs[{i if i < 8 else i - 8}]"
    for i in range(12)
)
DATA_BITS = tuple(f"{PANEL}lpm_ff:Switch_Sync|dffs[{i}]" for i in range(8))
RAM_BITS = tuple(
    f"|LAB8|Text_Renderer:Screen_Text|altsyncram:Screen_RAM|altsyncram_uob1:auto_generated|q_b[{i}]"
    for i in range(8)
)
PANEL_PROBES = (WRITE_ENABLE,) + ADDRESS_BITS + DATA_BITS + RAM_BITS


def write_vwf(path, panel, probes):
    signals = {pin: [(0, int(pin.startswith("KEY")))] for pin in PIN_INPUTS}
    if panel:
        for switch_time, byte, button, press, release in PANEL_ACTIONS:
            for bit in range(8):
                signals[f"SW[{bit}]"].append((switch_time + 3 if switch_time else 0, byte >> bit & 1))
            if button is not None:
                signals[f"KEY[{button}]"].extend(((press, 0), (release, 1)))

    sources = {
        PIN_CLOCK: f"NODE {{ REPEAT = {DURATION_NS // 20}; LEVEL 0 FOR 10.0; LEVEL 1 FOR 10.0; }}"
    }
    for pin, events in signals.items():
        events = sorted(dict(events).items())
        next_times = [time for time, _ in events[1:]] + [DURATION_NS]
        sources[pin] = " ".join(
            f"LEVEL {value} FOR {end - start}.0;"
            for (start, value), end in zip(events, next_times)
        )
    items = [(name, "INPUT", source) for name, source in sources.items()]
    undefined = f"LEVEL U FOR {DURATION_NS}.0;"
    items += [(pin, "OUTPUT", undefined) for pin in PIN_SYNC + PIN_RGB]
    items += [(probe, "BURIED", undefined) for probe in probes]

    header = f"""HEADER
{{
    VERSION = 1;
    TIME_UNIT = ns;
    DATA_OFFSET = 0.0;
    DATA_DURATION = {DURATION_NS}.0;
    SIMULATION_TIME = 0.0;
    GRID_PHASE = 0.0;
    GRID_PERIOD = 10.0;
    GRID_DUTY_CYCLE = 50;
}}
"""
    names = [
        f'''SIGNAL("{name}")
{{
    VALUE_TYPE = NINE_LEVEL_BIT;
    SIGNAL_TYPE = SINGLE_BIT;
    WIDTH = 1;
    LSB_INDEX = -1;
    DIRECTION = {direction};
    PARENT = "";
}}
'''
        for name, direction, _ in items
    ]
    transitions = [
        f'TRANSITION_LIST("{name}") {{ NODE {{ REPEAT = 1; {source} }} }}\n'
        for name, _, source in items
    ]
    path.write_text(header + "".join(names + transitions), encoding="ascii")


def load_memories(screen_path, font_path):
    screen = {
        int(address, 16): int(byte, 16)
        for address, byte in re.findall(r"^\s*([\dA-F]{3})\s*:\s*([\dA-F]{2});", screen_path.read_text(), re.M)
    }
    font = {
        int(address, 16): int(bits, 2)
        for address, bits in re.findall(r"^([\dA-F]{3})\s*:\s*([01]{8})\s*;", font_path.read_text(), re.M)
    }
    if set(screen) != set(range(2400)) or set(font) != set(range(2048)):
        raise ValueError("Expected exactly 2400 screen bytes and 2048 font bytes.")
    return screen, font


class Raster:
    def __init__(self, screen, font, writes):
        self.screen = screen
        self.font = font
        self.writes = iter(writes)
        self.upcoming_write = next(self.writes, None)
        self.x = self.y = 0
        self.green = self.hs = self.vs = 0
        self.address = None
        self.character = None
        self.coverage = Counter()
        self.samples = 0

    def advance(self, time_ns):
        """Return this edge's pin values, then prepare the next pixel."""
        expected = (self.green, self.hs, self.vs)
        self.samples += 1
        self.hs = int(not 659 <= self.x <= 755)
        self.vs = int(not 493 <= self.y <= 494)
        active = self.x < 640 and self.y < 480
        self.coverage["active" if active else "blanked"] += 1
        self.address = self.y // 16 * 80 + self.x // 8 if active else None
        self.green = 0
        self.character = None
        # The character lookup for this pixel is 10 ns after its launch.
        # A same-address write on that edge exposes the previous byte.
        while self.upcoming_write and self.upcoming_write[0] < time_ns + 10:
            _, address, data = self.upcoming_write
            self.screen[address] = data
            self.upcoming_write = next(self.writes, None)
        if active:
            self.character = self.screen[self.address]
            glyph_row = self.font[self.character * 16 + self.y % 16]
            self.green = glyph_row >> (7 - self.x % 8) & 1
        if self.y == 524 and self.x >= 699:
            self.y = 0
            self.coverage["frame_wrap"] += 1
        elif self.x == 699:
            self.y += 1
        self.x = (self.x + 1) % 800
        return expected


def check_vcd(vcd, screen, font, panel, panel_probes):
    initial_cell_zero = screen[0]
    raster = Raster(screen, font, WRITES if panel else ())
    names = {}
    values = {}
    wanted = set(PIN_SYNC + PIN_RGB)
    if panel_probes:
        wanted.update(PANEL_PROBES)
    time_ps = 0
    write_edges = []
    previous_cell = None
    ram_samples = 0
    collisions = []

    def word(bits):
        return sum(int(values[names[name]]) << index for index, name in enumerate(bits))

    def check_timestamp():
        nonlocal previous_cell, ram_samples
        for name in wanted - names.keys():
            raise ValueError(f"VCD missing {name}")
        if not time_ps:
            return
        if panel_probes and time_ps % 40_000 == 20_000 and raster.character is not None:
            read_byte = word(RAM_BITS)
            if read_byte != raster.character:
                raise ValueError(f"{time_ps} ps, RAM cell {raster.address}: expected {raster.character:02x}, got {read_byte:02x}")
            ram_samples += 1
            if write_edges and write_edges[-1][0] == time_ps // 1000:
                if write_edges[-1][1] == raster.address:
                    collisions.append((time_ps // 1000, raster.address, read_byte))
        if panel_probes and time_ps % 20_000 == 10_000 and values.get(names[WRITE_ENABLE]) == "1":
            # The enable is asserted after this rising edge and is sampled
            # by the RAM at the following falling edge.
            write_edges.append((time_ps // 1000 + 10, word(ADDRESS_BITS), word(DATA_BITS)))
        if time_ps % 40_000 != 10_000:
            return
        green, hs, vs = raster.advance(time_ps // 1000)
        expected = (hs, vs) + (0,) * 4 + (green,) * 4 + (0,) * 4
        for pin, level in zip(PIN_SYNC + PIN_RGB, expected):
            actual = values.get(names[pin])
            if actual != str(level):
                raise ValueError(f"{time_ps} ps, cell {previous_cell}: {pin} expected {level}, got {actual}")
        previous_cell = raster.address

    with vcd.open() as stream:
        for line in stream:
            line = line.strip()
            if line.startswith("$var "):
                _, _, _, identifier, name, *_ = line.split()
                name = name.lstrip("\\")
                if name in wanted:
                    names[name] = identifier
            elif line.startswith("#"):
                check_timestamp()
                time_ps = int(line[1:])
            elif line and line[0] in "01xXzZ":
                values[line[1:]] = line[0]
    check_timestamp()
    if raster.samples != DURATION_NS // 40 or raster.coverage["frame_wrap"] != 1:
        raise ValueError(f"Incomplete frame: {raster.samples} samples, {raster.coverage['frame_wrap']} frame wraps")
    if panel_probes and write_edges != (list(WRITES) if panel else []):
        raise ValueError(f"Unexpected write strobe edges: {write_edges}")
    print(f"PASS {raster.samples:,} RGB/HS/VS samples including startup, "
          f"{raster.coverage['active']:,} predicted active intervals, "
          f"{raster.coverage['blanked']:,} blanked intervals, one frame wrap")
    if panel_probes:
        if panel and collisions != [(100, 0, initial_cell_zero)]:
            raise ValueError(f"Expected the cell-0 collision to return its old byte: {collisions}")
        print(f"PASS {ram_samples:,} RAM read bytes, writes (ns, address, byte) {write_edges}, "
              f"same-address reads (ns, address, old byte) {collisions}")


def write_reference(output, screen, font):
    """Make an independent 640 by 480 PGM of the initialized display."""
    pixels = bytearray()
    for y in range(480):
        for x in range(640):
            ascii_code = screen[y // 16 * 80 + x // 8]
            glyph_row = font[ascii_code * 16 + y % 16]
            pixels.append(255 if glyph_row & (0x80 >> (x % 8)) else 0)
    output.write_bytes(b"P5\n640 480\n255\n" + pixels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    vector = commands.add_parser("vector")
    vector.add_argument("output", type=Path)
    vector.add_argument("--panel", action="store_true")
    vector.add_argument("--panel-probes", action="store_true",
                        help="Observe Quartus 13.0 functional-netlist RAM and panel nodes.")
    check = commands.add_parser("check")
    check.add_argument("vcd", type=Path)
    reference = commands.add_parser("reference")
    reference.add_argument("output", type=Path)
    for command in (check, reference):
        command.add_argument("--screen", type=Path, default=Path("superface_screen.mif"))
        command.add_argument("--font", type=Path, default=Path("ascii_8x16.mif"))
    check.add_argument("--panel", action="store_true")
    check.add_argument("--panel-probes", action="store_true")
    args = parser.parse_args()
    if args.command == "vector":
        write_vwf(args.output, args.panel, PANEL_PROBES if args.panel_probes else ())
    else:
        screen, font = load_memories(args.screen, args.font)
        if args.command == "reference":
            write_reference(args.output, screen, font)
        else:
            check_vcd(args.vcd, screen, font, args.panel, args.panel_probes)


if __name__ == "__main__":
    main()
