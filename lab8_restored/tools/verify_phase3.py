#!/usr/bin/env python3
"""Exercise the Quartus Phase3_Sim schematic using VWF stimuli and check its VCD."""

import argparse
from collections import Counter, defaultdict
from itertools import cycle
from pathlib import Path
import re

LINE_NS = 32_000
FIRST_PIXEL = 130
FULL_Y = tuple(range(525))
IDLE_NS = 100_000
# The focused post-fit run skips unrelated vertical lines by forcing the exported
# Y-counter net. It still runs the original horizontal raster and line builder.
FOCUS_JUMPS = {0: 479, 15: 479, 16: 523, 35: 30, 40: 468,
               53: 479, 54: 12, 58: 479, 59: 523, 64: 479}
# Physical simulation line to (screen version, VGA raster y). Lines that contain
# a force, or that could use a cache from before the jump, are omitted.
FOCUS_VISIBLE = {14: (0, 493),
                 **{line: (2, line - 18) for line in range(18, 35)},
                 **{line: (2, line - 5) for line in range(37, 40)},
                 **{line: (2, line + 428) for line in range(42, 52)},
                 56: (4, 14), 57: (4, 15),
                 **{line: (5, line - 61) for line in range(61, 64)},
                 66: (6, 481)}

PALETTE = (0x000, 0xA00, 0x0A0, 0xA50, 0x00A, 0xA0A, 0x0AA, 0xAAA,
           0x555, 0xF55, 0x5F5, 0xFF5, 0x55F, 0xF5F, 0x5FF, 0xFFF)
INPUT_PORTS = (
    ("Reset", 1), ("Font_Valid", 1), ("Runtime_Owner", 1), ("Font_Count", 15),
    ("Cmd_Valid", 1), ("Op", 3), ("Row", 5), ("Col", 7), ("Count", 7),
    ("Cursor_On", 1), ("Invalidate", 1), ("Push", 1), ("Push_Cell", 24),
)
RGB = [f"RGB[{i}]" for i in range(12)]
RESULT = [f"Result[{i}]" for i in range(3)]
PROBES = [*RGB, "VGA_HS", "VGA_VS", "Shown", "Done", *RESULT,
          "Build_Busy", "Build_Complete", "Build_Valid", "CE_N", "OE_N", "WE_N"]
ASSET_ROOT = Path(__file__).resolve().parents[2] / "assets" / "fonts"


def cell(glyph, fg=7, bg=0):
    return bg << 20 | fg << 16 | glyph


def contents():
    grid = [[cell(0x20)] * 80 for _ in range(30)]
    grid[0][:16] = [cell(0x41, fg, 15 - fg) for fg in range(16)]
    grid[0][16:20] = [cell(0x8000, 14, 2), cell(0xffff, 14, 2), cell(0x9a46, 12, 1), cell(0xffff, 12, 1)]
    grid[0][78:] = [cell(0x8005, 9, 4), cell(0xffff, 9, 4)]
    grid[1] = [cell(0x41 + i % 26, 1 + i % 15, 0) for i in range(80)]
    grid[2] = [cell(0x8000 if i % 2 == 0 else 0xffff, 11, 3) for i in range(80)]
    grid[29][79] = cell(0x5a, 10, 13)
    return grid


def scenario(lines, focused=False):
    frame_ns = len(lines) * LINE_NS
    blank = LINE_NS if focused else lines.index(480) * LINE_NS
    reset_again = 67 * LINE_NS + 20_000 if focused else 6 * frame_ns + 200_000
    events = {name: {0: 0} for name, _ in INPUT_PORTS}
    results = []
    events["Reset"].update({0: 1, 100: 0, reset_again: 1})
    events["Runtime_Owner"][0] = 1
    events["Font_Count"][0] = 6727
    events["Font_Valid"][blank + 50_000] = 1

    def operation(time, op, result, row=0, col=0, data=(), visible=0):
        if data:
            events["Push"].update({time: 1, time + 20 * len(data): 0})
            for i, value in enumerate(data):
                events["Push_Cell"][time + 20 * i] = value
        time += 20 * len(data) + 40
        for name, value in (("Op", op), ("Row", row), ("Col", col),
                            ("Count", len(data)), ("Cursor_On", visible)):
            events[name][time] = value
        events["Cmd_Valid"].update({time: 1, time + 20: 0})
        results.append((time, result))

    grid = contents()
    operation(1_000, 1, 0)
    operation(blank + 10_000, 2, 3, data=grid[0])  # Font unavailable.
    operation(blank + 34_000, 3, 2)  # Snapshot incomplete.
    for i, (col, item) in enumerate(((0, cell(0xffff)), (79, cell(0x8000)),
                                      (79, cell(0xffff, 10, 4)), (18, cell(0x9a47)))):
        row = grid[0].copy()
        row[col] = item
        operation(blank + 65_000 + i * 14_000, 2, 3, data=row)
    operation(blank + 121_000, 2, 1, row=1, data=grid[1])  # Wrong snapshot row order.
    for row_number, row in enumerate(grid):
        operation(blank + 137_000 + row_number * 10_000, 2, 0, row=row_number, data=row)
    operation(blank + 450_000, 3, 0, row=0, col=78, visible=1)
    commands = ([1_300_000, 1_680_000, 1_840_000, 2_020_000] if focused else
                [2 * frame_ns + 400_000, 3 * frame_ns + 600_000,
                 4 * frame_ns + 800_000, 5 * frame_ns + 1_000_000])
    operation(commands[0], 4, 3, col=79, data=[cell(0x58, 1, 15)])  # Breaks an unchanged lead.
    operation(commands[1], 5, 0, row=0, col=79, visible=1)
    operation(commands[2], 4, 0, col=78, data=[cell(0x51, 1, 10), cell(0x20, 6, 11)])
    events["Invalidate"].update({commands[3]: 1, commands[3] + 20: 0})
    return events, results, reset_again


def bit_names(name, width):
    return [name] if width == 1 else [f"{name}[{i}]" for i in range(width)]


def write_vector(path, idle):
    if idle:
        events = {name: {0: 0} for name, _ in INPUT_PORTS}
        events["Reset"] = {0: 1, 100: 0}
        duration = IDLE_NS
    else:
        events, _, reset_again = scenario(FULL_Y)
        duration = reset_again + 100_000
    waves = [("Clk", "INPUT", f"NODE {{ REPEAT = {duration // 20}; LEVEL 0 FOR 10.0; LEVEL 1 FOR 10.0; }}")]
    for name, width in INPUT_PORTS:
        points = sorted(events[name].items())
        for bit, pin in enumerate(bit_names(name, width)):
            bit_edges = []
            for time, word in points:
                value = (word >> bit) & 1
                if not bit_edges or value != bit_edges[-1][1]:
                    bit_edges.append((time, value))
            segments = [
                f"LEVEL {value} FOR {end - start}.0;"
                for (start, value), (end, _) in zip(bit_edges, bit_edges[1:] + [(duration, 0)])
            ]
            waves.append((pin, "INPUT", " ".join(segments)))
    waves += [(pin, "OUTPUT", f"LEVEL U FOR {duration}.0;") for pin in PROBES]
    header = (f"HEADER {{ VERSION = 1; TIME_UNIT = ns; DATA_OFFSET = 0.0;"
              f" DATA_DURATION = {duration}.0; SIMULATION_TIME = 0.0;"
              " GRID_PHASE = 0.0; GRID_PERIOD = 10.0; GRID_DUTY_CYCLE = 50; }\n")
    with path.open("w", encoding="ascii") as stream:
        stream.write(header)
        for pin, direction, _ in waves:
            stream.write(f'SIGNAL("{pin}") {{ VALUE_TYPE = NINE_LEVEL_BIT; SIGNAL_TYPE = SINGLE_BIT; '
                         f'WIDTH = 1; LSB_INDEX = -1; DIRECTION = {direction}; PARENT = ""; }}\n')
        for pin, _, wave in waves:
            stream.write(f'TRANSITION_LIST("{pin}") {{ NODE {{ REPEAT = 1; {wave} }} }}\n')


def write_external_stimulus(path, lines, focused):
    """Emit only timed test input assignments for a Quartus-exported simulation netlist."""
    events, _, reset_again = scenario(lines, focused)
    scalar_probes = [pin for pin in PROBES if "[" not in pin]
    source = ["`timescale 1ps/1ps", "module bench;", "reg Clk = 0;", "always #10000 Clk = ~Clk;"]
    for name, width in INPUT_PORTS:
        dimensions = f"[{width - 1}:0] " if width > 1 else ""
        source.append(f"reg {dimensions}{name};")
    source.extend(f"wire {pin};" for pin in scalar_probes)
    source.extend(("wire [11:0] rgb_p;", "wire [2:0] result_p;"))
    for pins, vector in ((RGB, "rgb_p"), (RESULT, "result_p")):
        for index, name in enumerate(pins):
            source.append(f"wire \\{name} = {vector}[{index}];")
    ports = [f".{name}({name})" for name in ["Clk", *(name for name, _ in INPUT_PORTS), *scalar_probes]]
    source.append("Phase3_Sim dut(" + ", ".join([*ports, ".RGB(rgb_p)", ".Result(result_p)"]) + ");")
    for name, points in events.items():
        source.append("initial begin")
        previous = 0
        for time, value in sorted(points.items()):
            delay = f"#{(time - previous) * 1000} " if time > previous else ""
            source.append(f"    {delay}{name} = {value};")
            previous = time
        source.append("end")
    source.extend(("initial begin", '    $dumpfile("Phase3_external.vcd");'))
    for pin in PROBES:
        identifier = f"\\{pin} " if "[" in pin else pin
        source.append(f"    $dumpvars(0, {identifier});")
    source.extend((f"    #{(reset_again + 100_000) * 1000} $finish;", "end"))
    if focused:
        counter = r"dut.\U_Terminal|U_Raster|U_V|dffs "
        for line, y in FOCUS_JUMPS.items():
            start = (line * LINE_NS + 2_000) * 1_000
            hold = (LINE_NS - 2_000 + 110) * 1_000
            source.append(f"initial begin #{start} force {counter}=10'd{y};"
                          f" #{hold} release {counter}; end")
    source.append("endmodule")
    path.write_text("\n".join(source) + "\n", encoding="ascii")


def read_font(path, digits, radix):
    word = "[01]{8}" if radix == 2 else "[0-9A-F]{4}"
    return {int(address, 16): int(data, radix) for address, data in
            re.findall(rf"^\s*([0-9A-F]{{{digits}}})\s*:\s*({word})\s*;",
                       path.read_text(encoding="ascii"), flags=re.M)}


def write_fixture(path, source):
    words = read_font(source, 5, 16)
    contracted = [0] * 256
    used = set()
    for glyph in (0x8000, 0x8005, 0x9a46):
        base = (glyph - 0x8000) * 16
        for row in range(16):
            address = (base + row) & 255
            if address in used:
                raise ValueError("test fixture address alias")
            used.add(address)
            contracted[address] = words[base + row]
    lines = ["DEPTH = 256;", "WIDTH = 16;", "ADDRESS_RADIX = HEX;", "DATA_RADIX = HEX;", "CONTENT BEGIN"]
    lines.extend(f"{i:02X} : {w:04X};" for i, w in enumerate(contracted))
    path.write_text("\n".join([*lines, "END;"]) + "\n", encoding="ascii")


def expected_colors(ascii_rows, chinese, lines, reset_again, focused):
    grid = contents()
    patched = False
    for raster_line, normal_y in enumerate(cycle(lines)):
        time = FIRST_PIXEL + raster_line * LINE_NS
        if time >= reset_again:
            return
        if focused:
            if raster_line not in FOCUS_VISIBLE:
                continue
            frame, y = FOCUS_VISIBLE[raster_line]
        else:
            frame, y = raster_line // len(lines), normal_y
        if frame == 5 and not patched:
            grid[0][78:] = [cell(0x51, 1, 10), cell(0x20, 6, 11)]
            patched = True
        for x in range(800):
            if time >= reset_again:
                return
            color = 0
            if 2 <= frame <= 5 and x < 640 and y < 480:
                column = x // 8
                row = grid[y // 16]
                record = row[column]
                glyph = record & 0xffff
                lx, ly = x % 8, y % 16
                if glyph == 0xffff:
                    glyph = row[column - 1] & 0xffff
                    lx += 8
                if glyph < 0x80:
                    pixel = bool(ascii_rows[glyph * 16 + ly] & (0x80 >> lx))
                else:
                    pixel = (2 <= ly < 14 and 2 <= lx < 14 and
                             bool(chinese[(glyph - 0x8000) * 16 + ly - 2] & (0x800 >> (lx - 2))))
                cursor_column = 78 if frame in (2, 3) else 79
                pixel ^= y in (14, 15) and column == cursor_column
                color = PALETTE[(record >> (16 if pixel else 20)) & 15]
            yield time, (color, int(not 659 <= x <= 755), int(not 493 <= y <= 494)), frame, x, y
            time += 40


def read_changes(path):
    """Yield timestamp groups with the output levels that change in the VCD."""
    names = defaultdict(list)
    changes = {}
    time_ps = 0
    with path.open() as stream:
        for raw in stream:
            line = raw.strip()
            if line.startswith("$var"):
                _, _, _, identifier, name, *_ = line.split()
                name = name.lstrip("\\")
                if name in PROBES:
                    names[identifier].append(name)
            elif line.startswith("#"):
                if changes:
                    yield time_ps // 1_000, changes
                time_ps = int(line[1:])
                changes = {}
            elif line and line[0] in "01xXzZ" and line[1:] in names:
                changes.update(dict.fromkeys(names[line[1:]], line[0]))
        yield time_ps // 1_000, changes
    missing = set(PROBES).difference(*(names.values()))
    if missing:
        raise ValueError(f"VCD missing {missing}")


def check_idle(path):
    values = {}
    pins = [*RGB, "VGA_HS", "VGA_VS", "Shown", "CE_N", "OE_N", "WE_N"]
    changes = iter(read_changes(path))
    transition_time, transition = next(changes)
    for time in range(FIRST_PIXEL, IDLE_NS, 40):
        while transition_time <= time:
            values.update(transition)
            transition_time, transition = next(changes, (float("inf"), {}))
        x = ((time - FIRST_PIXEL) // 40) % 800
        expected = "0" * 12 + ("0" if 659 <= x <= 755 else "1") + "10111"
        observed = "".join(values.get(pin, "x") for pin in pins)
        if expected != observed:
            raise ValueError(f"{time} ns, x={x}: expected {expected}, got {observed}")
    if transition_time < IDLE_NS - 40 or transition_time == float("inf"):
        raise ValueError("idle VCD ended early")
    print("PASS reset and 100 us of idle VGA sync, black RGB and inactive SRAM strobes")


def check(path, ascii_path, chinese_path, lines, focused):
    frame_ns = len(lines) * LINE_NS
    blank = lines.index(480) * LINE_NS
    _, schedule, reset_again = scenario(lines, focused)
    transitions = iter(read_changes(path))
    expected = iter(expected_colors(read_font(ascii_path, 3, 2), read_font(chinese_path, 5, 16),
                                    lines, reset_again, focused))
    current = next(expected, None)
    values = {}
    busy_start = None
    longest = 0
    builds = 0
    done = []
    show_changes = []
    coverage = Counter()
    read_count = 0
    selected_at = None
    released_at = 0
    actual = None
    first_read = (17 * LINE_NS if focused else 2 * frame_ns - LINE_NS)

    def number(bits):
        return sum(int(values[p]) << bit for bit, p in enumerate(bits))

    for time, changes in transitions:
        while current is not None and current[0] < time:
            _, color, frame, x, y = current
            if color != actual:
                raise ValueError(f"{current[0]} ns, frame {frame} ({x},{y}): expected {color}, got {actual}")
            coverage[frame] += 1
            current = next(expected, None)
        values.update(changes)
        pins = RGB + ["VGA_HS", "VGA_VS"]
        if any(pin in changes for pin in pins) and all(values.get(pin) in ("0", "1") for pin in pins):
            actual = (number(RGB), int(values["VGA_HS"]), int(values["VGA_VS"]))
        if changes.get("Done") == "1":
            done.append((time, number(RESULT)))
        if "Shown" in changes:
            show_changes.append((time, changes["Shown"]))
        if time >= FIRST_PIXEL and values.get("WE_N") != "1":
            raise ValueError("runtime SRAM write was enabled")
        if changes.get("CE_N") == "0":
            if selected_at is not None or time < released_at + 20:
                raise ValueError(f"SRAM turnaround violation at {time} ns")
            selected_at = time
        if changes.get("OE_N") == "0":
            if selected_at != time - 20 or time < first_read:
                raise ValueError(f"SRAM output enable without address setup at {time} ns")
            read_count += 1
        if changes.get("CE_N") == "1" and selected_at is not None:
            if time != selected_at + 160 or changes.get("OE_N") != "1":
                raise ValueError(f"SRAM capture window violation at {time} ns")
            selected_at = None
            released_at = time
        if changes.get("Build_Busy") == "1":
            busy_start = time
        elif changes.get("Build_Busy") == "0" and busy_start is not None:
            builds += 1
            longest = max(longest, (time - busy_start) // 20)
            if values.get("Build_Complete") != "1":
                raise ValueError(f"line build did not complete at {time} ns")
            busy_start = None

    if current is not None:
        raise ValueError(f"VCD ended before {current[0]} ns")
    if time < reset_again + 90_000 or values.get("Shown") != "0" or number(RGB):
        raise ValueError("VCD did not reach the final reset with the display hidden")
    if [code for _, code in done] != [code for _, code in schedule]:
        raise ValueError(f"unexpected command results: {done}")
    for (ack, _), (issued, _) in zip(done, schedule, strict=True):
        if not issued < ack < issued + frame_ns + 8_000:
            raise ValueError(f"command timing outside bound: {issued}, {ack}")
    shown = [change for change in show_changes if change[0] > FIRST_PIXEL]
    expected_shown = ([(16 * LINE_NS + 90, "1"), (65 * LINE_NS + 90, "0")] if focused else
                      [(frame_ns + blank + 90, "1"), (5 * frame_ns + blank + 90, "0")])
    if shown != expected_shown:
        raise ValueError(f"unexpected frame-boundary visibility: {shown}")
    if longest != 1520 or read_count == 0 or (not focused and builds != 4 * sum(y < 480 for y in lines)):
        raise ValueError(f"scanline coverage: {longest} clocks, {builds} builds, {read_count} SRAM reads")
    print(f"PASS {sum(coverage.values()):,} VGA pixel/sync samples, {len(done)} command results, "
          f"{builds} complete scanlines, {read_count} SRAM reads, worst build {longest} clocks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    vector = commands.add_parser("vector")
    vector.add_argument("output", type=Path)
    vector.add_argument("--idle", action="store_true")
    stimulus = commands.add_parser("stimulus")
    stimulus.add_argument("output", type=Path)
    stimulus.add_argument("--focused", action="store_true")
    fixture = commands.add_parser("fixture")
    fixture.add_argument("output", type=Path)
    fixture.add_argument("--chinese", type=Path, default=ASSET_ROOT / "chinese_sram.mif")
    check_command = commands.add_parser("check")
    check_command.add_argument("vcd", type=Path)
    profile = check_command.add_mutually_exclusive_group()
    profile.add_argument("--idle", action="store_true")
    profile.add_argument("--focused", action="store_true")
    check_command.add_argument("--ascii", type=Path, default=Path("ascii_8x16.mif"))
    check_command.add_argument("--chinese", type=Path, default=ASSET_ROOT / "chinese_sram.mif")
    args = parser.parse_args()
    if args.command == "vector":
        write_vector(args.output, args.idle)
    elif args.command == "stimulus":
        write_external_stimulus(args.output, FULL_Y, args.focused)
    elif args.command == "fixture":
        write_fixture(args.output, args.chinese)
    elif args.idle:
        check_idle(args.vcd)
    else:
        check(args.vcd, args.ascii, args.chinese, FULL_Y, args.focused)


if __name__ == "__main__":
    main()
