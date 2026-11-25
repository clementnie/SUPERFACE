#!/usr/bin/env python3
"""Build UART bench vectors with an independent Python v1 reference."""
import argparse
import binascii
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
PALETTE = (0x000, 0xA00, 0x0A0, 0xA50, 0x00A, 0xA0A, 0x0AA, 0xAAA,
           0x555, 0xF55, 0x5F5, 0xFF5, 0x55F, 0xF5F, 0x5FF, 0xFFF)


def frame(kind, session, seq, payload=b""):
    body = struct.pack("<BBQIB", 1, kind, session, seq, len(payload)) + payload
    body += struct.pack("<H", binascii.crc_hqx(body, 0xffff))
    return b"\x7e" + body.replace(b"\x7d", b"\x7d\x5d").replace(b"\x7e", b"\x7d\x5e") + b"\x7e"


def sv_bytes(data):
    return f'"{data.hex()}"'


def pixels(cells, y, cursor=None):
    atlas = dict((int(address, 16), int(mask, 2)) for address, mask in
                 re.findall(r"^([0-9A-F]+)\s*:\s*([01]{8})", (ROOT / "ascii_8x16.mif").read_text(), re.M))
    output = bytearray()
    for i, (glyph, _, color) in enumerate(cells):
        mask = atlas[16 * glyph + y]
        if cursor == i and y >= 14:
            mask ^= 255
        for x in range(8):
            rgb = PALETTE[color & 15 if mask & (128 >> x) else color >> 4]
            output.extend(rgb.to_bytes(2, "big"))
    return sv_bytes(output)


def vectors(synthetic):
    output = []

    def send(wire):
        output.append(f"send({sv_bytes(wire)});")

    def expect(wire, description, wait="19ms"):
        output.append(f'expect_frame({sv_bytes(wire)}, "{description}", {wait});')

    def request(kind, seq, payload=b"", status=0, description="command", wait="19ms"):
        send(frame(kind, session, seq, payload))
        expect(frame(0x7f, session, seq, bytes([kind, status])), description, wait)

    def hello(sid, wanted, status):
        send(frame(1, sid, 0, wanted))
        expect(frame(2, sid, 0, bytes([status, 2, 80, 30, 3, 243, 7]) + bytes(18)), "offer", "2ms")

    assert binascii.crc_hqx(b"123456789", 0xffff) == 0x29b1
    session = 0x7D7E070605040302
    output.extend(("reset_board();", "rx_bit = 327000;",
                   "serial_rx = 0; #(rx_bit/4); serial_rx = 1; #(rx_bit);"))
    hello(0x0807060504030201, bytes.fromhex("471a552fa5cca77302d2b922d50ae444f2db"), 2)
    output.append("rx_bit = 339000;")
    hello(session, bytes(18), 0)
    hello(session, bytes(18), 0)
    output.append('$display("Checked three HELLO_ACK frames at %0t ps", $time);')

    # Abort an escaped candidate, then a stop error immediately before valid frames.
    send(b"\x7e\x01\x7d\x11\x7e\x01")
    output.extend(("send_byte(8'h00, 0);", "serial_rx = 1; #(rx_bit);", "rx_bit = 333333;"))
    send(frame(0x15, session ^ 1, 1) + frame(0x15, session, 2))
    request(0x15, 1, description="ping after malformed frames and missing sequence")
    changed_hello = frame(1, session, 0, bytes([1, 0, 1]) + bytes(15))
    send(changed_hello)
    request(0x15, 1, description="duplicate ping through replay cache")
    output.append("transaction_start = $time;")
    request(0x10, 2, description="snapshot begin and blank", wait="36ms")
    request(0x11, 3, bytes([1]) + b" \x00\x07" * 80, 1, "out-of-order snapshot row")
    request(0x12, 4, bytes(3), 2, "premature snapshot end")
    request(0x10, 5, status=2, description="second begin")
    cells = [(0x41, 0, 0x49), (0x20, 0, 0x27)]
    cells += [(0x41, 0, (15 - color) << 4 | color) for color in range(16)]
    cells += [(0x20, 0, 0x07)] * (80 - len(cells))
    for row in range(30):
        data = b"".join(bytes(cell) for cell in cells) if row == 0 else b" \x00\x07" * 80
        request(0x11, row + 6, bytes([row]) + data, description=f"snapshot row {row}")
    request(0x12, 36, bytes(3), description="snapshot end after completed writes")
    output.append('$display("Snapshot exchange with injected command errors: %0t ps", $time - transaction_start);')
    output.append(f"check_strip(2, {pixels(cells[:18], 2)});")
    # Worst legal payload uses escapable glyph and color bytes in every cell.
    span = bytes([0, 0, 80]) + b"\x7e\x00\x7d" * 80
    good = frame(0x13, session, 37, span)
    damaged = bytearray(good)
    damaged[-2] ^= 1
    output.append("transaction_start = $time;")
    send(bytes(damaged) + good)
    expect(frame(0x7f, session, 37, bytes([0x13, 0])), "max stuffed span after CRC corruption")
    output.append('$display("Corrupt frame and successful maximum span: %0t ps", $time - transaction_start);')
    # Retry must replay the same completion; changed bytes with the old seq are ignored.
    send(frame(0x13, session, 37, bytes([0, 0, 1, 0x41, 0, 0x49])) + good)
    expect(frame(0x7f, session, 37, bytes([0x13, 0])), "duplicate max span")
    request(0x13, 38, bytes([0, 0, 1, 0xff, 0xff, 0x49]), 3, "orphan continuation rejected")
    request(0x13, 39, bytes([0, 79, 2, 0x41, 0, 0x49, 0x20, 0, 0x49]), 1, "span bounds")
    request(0x14, 40, bytes([0, 1, 1]), description="cursor visible commit")
    patch = [(0x7e, 0, 0x7d)] * 2
    output.append(f"check_strip(14, {pixels(patch, 14, cursor=1)});")
    if synthetic:
        output.append("synthetic_key(8'h1c);")
        send(frame(0x15, session, 41))
        expect(frame(0x20, session, 1, b"\x00\x1c"), "synthetic Set 2 make")
        expect(frame(0x7f, session, 41, b"\x15\x00"), "crossed display ACK")
        send(frame(0x7f, session, 1, b"\x20\x00"))
        output.append("synthetic_key(8'hf0);")
        expect(frame(0x20, session, 2, b"\x00\xf0"), "next Set 2 byte")
        send(frame(0x7f, session, 2, b"\x20\x00"))
    output.append("reset_board();")
    send(frame(0x15, session, 42))
    output.append("quiet(100_000_000);")
    session ^= 0xCAFE
    hello(session, bytes(18), 0)
    request(0x15, 1, description="fresh sequence after board reset")
    return "\n".join(output) + "\n"


def synthetic_input(path):
    text = path.read_text()
    for y, source in ((2096, "SW[8]"), (2120, "SW[9]"),
                      (2144, "SW[7..0]"), (2168, "Font_Ready")):
        pattern = rf'\(connector \(text "Phase6_[^"]+"([^\n]+)\(pt 1560 {y}\)'
        text, count = re.subn(pattern, rf'(connector (text "{source}"\1(pt 1560 {y})', text)
        if count != 1:
            raise ValueError(f"Expected one Phase 6 connector at {y}, found {count}")
    path.write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("vectors", type=Path)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--patch-synthetic-bdf", type=Path)
    args = parser.parse_args()
    args.vectors.write_text(vectors(args.synthetic))
    if args.patch_synthetic_bdf:
        synthetic_input(args.patch_synthetic_bdf)


if __name__ == "__main__":
    main()
